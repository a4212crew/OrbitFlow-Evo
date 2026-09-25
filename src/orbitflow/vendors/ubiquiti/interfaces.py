"""Ubiquiti EdgeSwitch interface collection command and parser."""

from __future__ import annotations

from contextlib import closing
import re

from orbitflow.transport import DeviceSession
from orbitflow.vendors.common import PromptCLI
from orbitflow.vendors.interface_types import InterfaceCollection, InterfaceObservation

_REJECTED = re.compile(
    r"(?:%\s*(?:Invalid input|Unknown command)|Unrecognized command)", re.IGNORECASE
)
_HEADER = (
    "                                         Link    Physical    Physical    Flow Control",
    "Port       Name                          State   Mode        Status      Status",
    "---------  ----------------------------  ------  ----------  ----------  ------------",
)
_COLUMN_SPANS = tuple(
    (match.start(), match.end()) for match in re.finditer(r"-+", _HEADER[-1])
)
_FOOTER = "Flow Control:Disabled"


def extract_edgeswitch_hostname(prompt: str) -> str:
    """Extract the hostname from an EdgeSwitch exec prompt."""
    match = re.fullmatch(
        r"(?:\((?P<parenthesized>[^()\r\n]+)\)\s*#|" r"(?P<simple>[^:#>\s()]+)[#>])",
        prompt.strip(),
    )
    if match is None:
        raise ValueError(f"unrecognized EdgeSwitch prompt: {prompt!r}")
    return match.group("parenthesized") or match.group("simple")


def parse_interfaces_status(output: str) -> list[InterfaceObservation]:
    if not output.strip():
        return []
    records: list[InterfaceObservation] = []
    header_index = 0
    table_started = False
    footer_seen = False
    for raw_line in output.splitlines():
        line = raw_line.rstrip()
        if not line.strip():
            continue

        if not table_started:
            if line != _HEADER[header_index]:
                raise ValueError(f"unrecognized EdgeSwitch interface row: {line!r}")
            header_index += 1
            table_started = header_index == len(_HEADER)
            continue

        if footer_seen:
            raise ValueError(f"unrecognized EdgeSwitch interface row: {line!r}")
        if line == _FOOTER and records:
            footer_seen = True
            continue

        port_start, port_end = _COLUMN_SPANS[0]
        name_start, name_end = _COLUMN_SPANS[1]
        link_start, link_end = _COLUMN_SPANS[2]
        if len(line) <= link_start or any(
            character != " " for character in line[port_end:name_start]
        ):
            raise ValueError(f"unrecognized EdgeSwitch interface row: {line!r}")
        port = line[port_start:port_end].strip()
        name = line[name_start:name_end].strip()
        link = line[link_start:link_end].strip().lower()
        if (
            not port
            or any(character.isspace() for character in port)
            or link
            not in {
                "up",
                "down",
            }
        ):
            raise ValueError(f"unrecognized EdgeSwitch interface row: {line!r}")
        records.append(
            InterfaceObservation(
                port_name=port,
                port_description=name,
                admin_status="",
                oper_status=link,
            )
        )
    if not table_started:
        raise ValueError("EdgeSwitch interface output contained an incomplete header")
    if not records:
        raise ValueError("EdgeSwitch interface output contained no parseable records")
    return records


class EdgeSwitchInterfaceAdapter:
    def __init__(self, session: DeviceSession, *, timeout: float = 10.0) -> None:
        self._session = session
        self._timeout = timeout

    def collect(self) -> InterfaceCollection:
        with closing(PromptCLI(
            self._session,
            paging_command="terminal length 0",
            prompt_pattern=r"^([^\r\n]+[>#])[ \t]*$",
            rejected=lambda output: bool(_REJECTED.search(output)),
            platform_name="Ubiquiti EdgeSwitch",
            timeout=self._timeout,
        )) as cli:
            command = "show interfaces status all"
            output = cli.run_command(command, timeout=self._timeout)
            if _REJECTED.search(output):
                raise ValueError(f"EdgeSwitch rejected approved command {command!r}")
            return InterfaceCollection(
                device_name=extract_edgeswitch_hostname(cli.prompt),
                observations=parse_interfaces_status(output),
            )
