"""Identification orchestration over an already-established DeviceSession."""

from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
from typing import Callable, Protocol

from orbitflow.models import DeviceContext
from orbitflow.transport import DeviceSession
from orbitflow.vendors.common import PromptCLI
from orbitflow.vendors.cisco.identification import parse_cisco_identity
from orbitflow.vendors.huawei.identification import parse_huawei_identity
from orbitflow.vendors.huawei.interfaces import extract_huawei_hostname
from orbitflow.vendors.ubiquiti.identification import parse_edgeswitch_identity
from orbitflow.vendors.ubiquiti.interfaces import extract_edgeswitch_hostname

from .store import JsonInventoryStore


class DeviceInventoryError(Exception):
    """A device could not be identified with sufficient evidence."""


class _Runner(Protocol):
    prompt: str

    def run_command(self, command: str, timeout: float = 10.0) -> str: ...

    def close(self) -> None: ...


class DeviceInventoryResolver:
    """Collect stable identity without reconnecting or owning the session."""

    _SUPPORTED = {"cisco_ios", "cisco_xe", "cisco_xr", "huawei_vrp", "ubiquiti_edgeswitch"}

    def __init__(self, store: JsonInventoryStore, *, clock: Callable[[], datetime] | None = None,
                 timeout: float = 10.0, runner_factory: Callable[[DeviceSession], _Runner] | None = None) -> None:
        self.store = store
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._timeout = timeout
        self._runner_factory = runner_factory or self._new_runner
        self.last_events: tuple[str, ...] = ()

    def resolve(self, session: DeviceSession, *, management_ip: str,
                platform_override: str | None = None) -> DeviceContext:
        attempted_at = self._clock()
        try:
            if platform_override and platform_override not in self._SUPPORTED:
                raise DeviceInventoryError(f"unsupported platform override: {platform_override}")
            with closing(self._runner_factory(session)) as runner:
                show_version = runner.run_command("show version", timeout=self._timeout)
                display_version = ""
                show_identified = sum(
                    parser(show_version, "") is not None
                    for parser in (parse_cisco_identity, parse_edgeswitch_identity)
                ) == 1
                if (not show_identified and
                        platform_override not in {"cisco_ios", "cisco_xe", "cisco_xr", "ubiquiti_edgeswitch"}):
                    runner.run_command("screen-length 0 temporary", timeout=self._timeout)
                    display_version = runner.run_command("display version", timeout=self._timeout)
                facts, detected_group = self._detect(show_version, display_version, platform_override)
                if detected_group == "cisco":
                    command = "show chassis" if facts.get("platform") == "cisco_xr" else "show inventory"
                    details = runner.run_command(command, timeout=self._timeout)
                    facts = parse_cisco_identity(show_version, details) or facts
                elif detected_group == "huawei":
                    details = runner.run_command("display esn", timeout=self._timeout)
                    facts = parse_huawei_identity(display_version, details) or facts
                    facts["hostname"] = extract_huawei_hostname(runner.prompt)
                else:
                    facts["hostname"] = extract_edgeswitch_hostname(runner.prompt)
                if platform_override and facts.get("device_family") != "ME3600X":
                    facts["platform"] = platform_override
                if not facts.get("hostname"):
                    raise DeviceInventoryError("identification output did not contain a hostname")
                context = DeviceContext(device_id="", management_ip=management_ip,
                                        observed_management_ips=(management_ip,),
                                        last_successful_collection=attempted_at,
                                        last_collection_attempt=attempted_at, **facts)  # type: ignore[arg-type]
                context, self.last_events = self.store.reconcile(context)
                return context
        except Exception as exc:
            safe_error = f"identification failed ({type(exc).__name__})"
            self.store.record_failure(management_ip, attempted_at, safe_error)
            if isinstance(exc, DeviceInventoryError):
                raise
            raise DeviceInventoryError(safe_error) from exc

    def _detect(self, show: str, display: str, override: str | None) -> tuple[dict[str, object], str]:
        candidates: list[tuple[dict[str, object], str]] = []
        cisco = parse_cisco_identity(show, "")
        huawei = parse_huawei_identity(display, "")
        edge = parse_edgeswitch_identity(show, "")
        if cisco: candidates.append((cisco, "cisco"))
        if huawei: candidates.append((huawei, "huawei"))
        if edge: candidates.append((edge, "edge"))
        if override:
            group = "huawei" if override == "huawei_vrp" else "edge" if override == "ubiquiti_edgeswitch" else "cisco"
            selected = next((item for item in candidates if item[1] == group), None)
            if selected:
                return selected
            raise DeviceInventoryError("platform override conflicts with identification output")
        if len(candidates) != 1:
            raise DeviceInventoryError("platform identification was unknown or ambiguous")
        return candidates[0]

    def _new_runner(self, session: DeviceSession) -> _Runner:
        # The generic probe deliberately does not reject the paging command: Huawei
        # safely rejects it, after which its small version probe remains usable.
        return PromptCLI(session, paging_command="terminal length 0",
                         prompt_pattern=r"(?m)^(.+(?:#|>|\]))[ \t]*$",
                         rejected=lambda _: False, platform_name="identification",
                         timeout=self._timeout)
