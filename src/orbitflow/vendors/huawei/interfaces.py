"""Huawei VRP interface collection command and parser."""

from __future__ import annotations

import re

from orbitflow.transport import DeviceSession
from orbitflow.vendors.common import DeviceCLI, open_prompt_cli
from orbitflow.vendors.interface_types import InterfaceCollection, InterfaceObservation

_REJECTED = re.compile(
    r"(?:Error:|Unrecognized command|Wrong parameter|Too many parameters|Incomplete command)",
    re.IGNORECASE,
)
_DESCRIPTION_STATUS_ROW = re.compile(
    r"^(?P<port>\S+)\s+(?P<phy>\*?(?:up|down))\s+(?P<protocol>up|down)(?:\s+(?P<description>.*))?$",
    re.IGNORECASE,
)
_DESCRIPTION_ONLY_ROW = re.compile(r"^(?P<port>\S+)(?:\s{2,}(?P<description>.*))?$")
_BRIEF_ROW = re.compile(
    r"^(?P<port>\S+)\s+(?P<phy>\*?(?:up|down))\s+"
    r"(?P<protocol>(?:up|down)(?:\([A-Za-z]\))?)\s+"
    r"(?P<in_util>--|\d+(?:\.\d+)?%)\s+(?P<out_util>--|\d+(?:\.\d+)?%)\s+"
    r"(?P<in_errors>\d+)\s+(?P<out_errors>\d+)$",
    re.IGNORECASE,
)
_DESCRIPTION_STATUS_HEADER = re.compile(
    r"^Interface\s+PHY\s+Protocol\s+Description$", re.IGNORECASE
)
_DESCRIPTION_ONLY_HEADER = re.compile(r"^Interface\s+Description$", re.IGNORECASE)
_BRIEF_HEADER = re.compile(
    r"^Interface\s+PHY\s+Protocol\s+InUti\s+OutUti\s+inErrors\s+outErrors$",
    re.IGNORECASE,
)
_BRIEF_LEGENDS = frozenset(
    {
        "PHY: Physical",
        "*down: administratively down",
        "(l): loopback",
        "(s): spoofing",
        "(b): BFD down",
        "(B): Bit-error-detection down",
        "(e): ETHOAM down",
        "(d): Dampening Suppressed",
        "InUti/OutUti: input utility/output utility",
    }
)
_CANONICAL_INTERFACE_NAME = re.compile(
    r"^(?P<prefix>GigabitEthernet|Ethernet|LoopBack|Tunnel|Loop|Tun|GE|Eth)(?P<suffix>\d.*)$",
    re.IGNORECASE,
)
_CANONICAL_INTERFACE_PREFIXES = {
    "eth": "Ethernet",
    "ethernet": "Ethernet",
    "ge": "GigabitEthernet",
    "gigabitethernet": "GigabitEthernet",
    "loop": "LoopBack",
    "loopback": "LoopBack",
    "tun": "Tunnel",
    "tunnel": "Tunnel",
}


def extract_huawei_hostname(prompt: str) -> str:
    """Extract the hostname from a VRP user or system-view prompt."""
    match = re.fullmatch(
        r"(?:<(?P<user>[^<>]+)>|\[(?P<system>[^\[\]]+)\])", prompt.strip()
    )
    if match is None:
        raise ValueError(f"unrecognized Huawei VRP prompt: {prompt!r}")
    return match.group("user") or match.group("system")


def parse_interface_description(output: str) -> list[InterfaceObservation]:
    """Parse either approved VRP interface-description table shape."""
    if not output.strip():
        return []
    table_format = None
    records = []
    for raw_line in output.splitlines():
        line = raw_line.strip()
        lower = line.lower()
        if (
            not line
            or lower.startswith(("physical", "*down:"))
            or set(line) <= {"-", " "}
        ):
            continue
        if _DESCRIPTION_STATUS_HEADER.fullmatch(line):
            if table_format is not None:
                raise ValueError("duplicate Huawei interface description header")
            table_format = "status"
            continue
        if _DESCRIPTION_ONLY_HEADER.fullmatch(line):
            if table_format is not None:
                raise ValueError("duplicate Huawei interface description header")
            table_format = "description"
            continue
        if table_format is None:
            raise ValueError(f"unrecognized Huawei interface row: {line!r}")
        row_pattern = (
            _DESCRIPTION_STATUS_ROW
            if table_format == "status"
            else _DESCRIPTION_ONLY_ROW
        )
        match = row_pattern.fullmatch(line)
        if match is None:
            raise ValueError(f"unrecognized Huawei interface row: {line!r}")
        phy = match.groupdict().get("phy", "").lower()
        records.append(
            InterfaceObservation(
                port_name=match.group("port"),
                port_description=(match.group("description") or "").strip(),
                admin_status=("down" if phy.startswith("*") else "up") if phy else "",
                oper_status=phy.lstrip("*"),
            )
        )
    if not records:
        raise ValueError("Huawei interface output contained no parseable records")
    return records


def parse_interface_brief(output: str) -> dict[str, tuple[str, str]]:
    """Parse the approved VRP brief table into status keyed by interface name."""
    if not output.strip():
        return {}
    header_seen = False
    statuses: dict[str, tuple[str, str]] = {}
    for raw_line in output.splitlines():
        line = raw_line.strip()
        if not line or set(line) <= {"-", " "}:
            continue
        if not header_seen and line in _BRIEF_LEGENDS:
            continue
        if _BRIEF_HEADER.fullmatch(line):
            if header_seen:
                raise ValueError("duplicate Huawei interface brief header")
            header_seen = True
            continue
        if not header_seen:
            raise ValueError(f"unrecognized Huawei interface brief row: {line!r}")
        match = _BRIEF_ROW.fullmatch(line)
        if match is None:
            raise ValueError(f"unrecognized Huawei interface brief row: {line!r}")
        port = match.group("port")
        if port in statuses:
            raise ValueError(f"duplicate Huawei interface brief row: {port!r}")
        phy = match.group("phy").lower()
        statuses[port] = (
            "down" if phy.startswith("*") else "up",
            phy.lstrip("*"),
        )
    if not statuses:
        raise ValueError("Huawei interface brief output contained no parseable records")
    return statuses


def _canonical_interface_name(port_name: str) -> str:
    """Expand known VRP abbreviations for description-to-brief matching."""
    match = _CANONICAL_INTERFACE_NAME.fullmatch(port_name)
    if match is None:
        return port_name.casefold()
    expanded = _CANONICAL_INTERFACE_PREFIXES[match.group("prefix").casefold()]
    return f"{expanded}{match.group('suffix')}".casefold()


def _join_description_status(
    descriptions: list[InterfaceObservation], statuses: dict[str, tuple[str, str]]
) -> list[InterfaceObservation]:
    canonical_statuses: dict[str, tuple[str, str]] = {}
    for port_name, status in statuses.items():
        canonical_name = _canonical_interface_name(port_name)
        if canonical_name in canonical_statuses:
            raise ValueError(
                "Huawei interface brief output contained duplicate canonical "
                f"interface {port_name!r}"
            )
        canonical_statuses[canonical_name] = status

    records = []
    for description in descriptions:
        try:
            admin_status, oper_status = canonical_statuses[
                _canonical_interface_name(description.port_name)
            ]
        except KeyError as exc:
            raise ValueError(
                "Huawei interface brief output omitted description interface "
                f"{description.port_name!r}"
            ) from exc
        records.append(
            InterfaceObservation(
                port_name=description.port_name,
                port_description=description.port_description,
                admin_status=admin_status,
                oper_status=oper_status,
            )
        )
    return records


class HuaweiInterfaceAdapter:
    def __init__(self, session: DeviceSession, *, timeout: float = 10.0, cli: DeviceCLI | None = None) -> None:
        self._cli = cli
        self._session = session
        self._timeout = timeout

    def collect(self) -> InterfaceCollection:
        with open_prompt_cli(
            self._session, cli=self._cli,
            paging_command="screen-length 0 temporary",
            prompt_pattern=r"^([^\r\n]*(?:<[^<>\r\n]+>|\[[^\[\]\r\n]+\]))[ \t]*$",
            rejected=lambda output: bool(_REJECTED.search(output)),
            platform_name="Huawei VRP",
            timeout=self._timeout,
        ) as cli:
            output = cli.run_command("display interface description", timeout=self._timeout)
            if _REJECTED.search(output):
                raise ValueError(
                    "Huawei VRP rejected approved command 'display interface description'"
                )
            observations = parse_interface_description(output)
            if observations and not observations[0].admin_status:
                brief_output = cli.run_command(
                    "display interface brief", timeout=self._timeout
                )
                if _REJECTED.search(brief_output):
                    raise ValueError(
                        "Huawei VRP rejected approved command 'display interface brief'"
                    )
                observations = _join_description_status(
                    observations, parse_interface_brief(brief_output)
                )
            return InterfaceCollection(
                device_name=extract_huawei_hostname(cli.prompt),
                observations=observations,
            )
