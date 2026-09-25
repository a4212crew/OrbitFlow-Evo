"""Cisco interface collection command and parser."""

from __future__ import annotations

from contextlib import closing
import re

from orbitflow.transport import DeviceSession
from orbitflow.vendors.interface_types import InterfaceCollection, InterfaceObservation

from .ios import CiscoIOSCLI, extract_ios_hostname

_ROW = re.compile(
    r"^(?P<port>\S+)\s{2,}(?P<status>.+?)\s{2,}(?P<protocol>\S+)"
    r"(?:\s{2,}(?P<description>.*))?$"
)
_REJECTED = re.compile(
    r"%\s*(?:Invalid input|Unknown command|Unrecognized command|Incomplete command)",
    re.IGNORECASE,
)
_IOS_XR_TIMESTAMP = re.compile(
    r"^(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun) "
    r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) "
    r"\d{1,2} \d{2}:\d{2}:\d{2}\.\d{3} [A-Z][A-Z0-9+-]*$"
)


class CiscoXRCLI(CiscoIOSCLI):
    """IOS-XR shell kept distinct while using its approved Cisco interaction."""


def extract_ios_xr_hostname(prompt: str) -> str:
    """Extract an IOS-XR hostname from an ``RP/...:hostname#`` prompt."""
    match = re.fullmatch(r"RP/[^:\r\n]+:(?P<hostname>[^:#>\s]+)#", prompt.strip())
    if match is None:
        raise ValueError(f"unrecognized IOS-XR prompt: {prompt!r}")
    return match.group("hostname")


def _state(value: str) -> str:
    normalized = value.strip().lower().replace("-", " ")
    if normalized in {"up", "down"}:
        return normalized
    if normalized in {"admin down", "administratively down"}:
        return "down"
    return normalized


def _is_admin_down(value: str) -> bool:
    return value.strip().lower().replace("-", " ") in {
        "admin down",
        "administratively down",
    }


def parse_interfaces_description(output: str) -> list[InterfaceObservation]:
    """Parse IOS-family ``show interfaces description`` output."""
    if not output.strip():
        return []
    records = []
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line or line.lower().startswith("interface") or set(line) <= {"-", " "}:
            continue
        match = _ROW.match(line)
        if match is None:
            raise ValueError(f"unrecognized Cisco interface row: {line!r}")
        status = match.group("status")
        records.append(
            InterfaceObservation(
                port_name=match.group("port"),
                port_description=(match.group("description") or "").strip(),
                admin_status="down" if _is_admin_down(status) else "up",
                oper_status=_state(match.group("protocol")),
            )
        )
    if not records:
        raise ValueError("Cisco interface output contained no parseable records")
    return records


def parse_ios_xr_interfaces_description(output: str) -> list[InterfaceObservation]:
    """Parse IOS-XR output, allowing its timestamp before the table header."""
    lines = output.splitlines()
    table_started = False
    filtered_lines = []
    for raw_line in lines:
        line = raw_line.strip()
        if line.lower().startswith("interface"):
            table_started = True
        if not table_started and _IOS_XR_TIMESTAMP.fullmatch(line):
            continue
        filtered_lines.append(raw_line)
    return parse_interfaces_description("\n".join(filtered_lines))


class CiscoInterfaceAdapter:
    """Collect interfaces for an explicitly selected Cisco platform."""

    def __init__(self, session: DeviceSession, *, timeout: float = 10.0) -> None:
        self._session = session
        self._timeout = timeout

    def collect(self) -> InterfaceCollection:
        with closing(self.cli_type(self._session, timeout=self._timeout)) as cli:
            output = cli.run_command("show interfaces description", timeout=self._timeout)
            if _REJECTED.search(output):
                raise ValueError(
                    "Cisco rejected approved command 'show interfaces description'"
                )
            return InterfaceCollection(
                device_name=self.extract_hostname(cli.prompt),
                observations=self.parse_output(output),
            )

    cli_type = CiscoIOSCLI
    extract_hostname = staticmethod(extract_ios_hostname)
    parse_output = staticmethod(parse_interfaces_description)


class CiscoXRInterfaceAdapter(CiscoInterfaceAdapter):
    """IOS-XR-specific adapter, independently selectable by the service."""

    cli_type = CiscoXRCLI
    extract_hostname = staticmethod(extract_ios_xr_hostname)
    parse_output = staticmethod(parse_ios_xr_interfaces_description)
