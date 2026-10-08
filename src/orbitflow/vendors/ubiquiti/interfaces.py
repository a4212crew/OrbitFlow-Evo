"""Ubiquiti EdgeSwitch interface collection command and parser."""

from __future__ import annotations

import re

from orbitflow.transport import DeviceSession
from orbitflow.vendors.common import DeviceCLI, open_prompt_cli
from orbitflow.vendors.interface_types import InterfaceCollection, InterfaceObservation
from .prompts import extract_edgeswitch_hostname

_REJECTED = re.compile(
    r"(?:%\s*(?:Invalid input|Unknown command)|Unrecognized command)", re.IGNORECASE
)
_HEADERS = (
    (
        "                                         Link    Physical    Physical    Flow Control",
        "Port       Name                          State   Mode        Status      Status",
        "---------  ----------------------------  ------  ----------  ----------  ------------",
    ),
    (
        "                                         Link    Physical    Physical    Media               Flow Control",
        "Port       Name                          State   Mode        Status      Type                Status",
        "---------  ----------------------------  ------  ----------  ----------  ------------------  ------------",
    ),
)
_FOOTER = "Flow Control:Disabled"


def _parse_row(
    line: str, spans: tuple[tuple[int, int], ...], *, byte_width: bool = False,
) -> InterfaceObservation | None:
    # Keep the original description intact. Byte-counted CLI padding and
    # character-counted padding are checked against the same recognised layout;
    # never collapse whitespace or shift columns to search for a status token.
    row = line.encode("utf-8") if byte_width else line
    space = b" " if byte_width else " "
    if len(row) <= spans[2][0] or row[spans[-1][1]:].strip(space):
        return None
    for (_, end), (start, _) in zip(spans, spans[1:]):
        if row[end:start].strip(space):
            return None
    try:
        fields = [
            row[start:end].decode("utf-8") if byte_width else row[start:end]
            for start, end in spans
        ]
    except UnicodeDecodeError:
        return None
    port, name, link = (field.strip(" ") for field in fields[:3])
    if not re.fullmatch(r"[0-9]+/[0-9]+", port) or link.lower() not in {"up", "down"}:
        return None
    return InterfaceObservation(
        port_name=port, port_description=name, admin_status="", oper_status=link.lower(),
    )


def parse_interfaces_status(output: str) -> list[InterfaceObservation]:
    if not output.strip():
        return []
    records: list[InterfaceObservation] = []
    header_index = 0
    candidates = _HEADERS
    spans: tuple[tuple[int, int], ...] = ()
    footer_seen = False
    for raw_line in output.splitlines():
        line = raw_line.rstrip(" ")
        if not line.strip():
            continue

        if not spans:
            candidates = tuple(header for header in candidates if line == header[header_index])
            if not candidates:
                raise ValueError("unrecognized EdgeSwitch interface row (header)")
            header_index += 1
            if header_index == 3:
                spans = tuple(
                    (match.start(), match.end())
                    for match in re.finditer(r"-+", candidates[0][-1])
                )
            continue

        if footer_seen:
            raise ValueError("unrecognized EdgeSwitch interface row (after footer)")
        if line == _FOOTER and records:
            footer_seen = True
            continue

        record = _parse_row(line, spans)
        if record is None and not line.isascii():
            record = _parse_row(line, spans, byte_width=True)
        if record is None:
            # Do not propagate descriptions or raw device output through the
            # shared capability's exception wrapper into diagnostics.
            raise ValueError("unrecognized EdgeSwitch interface row (invalid fields)")
        records.append(record)
    if not spans:
        raise ValueError("EdgeSwitch interface output contained an incomplete header")
    if not records:
        raise ValueError("EdgeSwitch interface output contained no parseable records")
    return records


class EdgeSwitchInterfaceAdapter:
    def __init__(self, session: DeviceSession, *, timeout: float = 10.0, cli: DeviceCLI | None = None) -> None:
        self._cli = cli
        self._session = session
        self._timeout = timeout

    def collect(self) -> InterfaceCollection:
        with open_prompt_cli(
            self._session, cli=self._cli,
            paging_command="terminal length 0",
            prompt_pattern=r"^([^\r\n]+[>#])[ \t]*$",
            rejected=lambda output: bool(_REJECTED.search(output)),
            platform_name="Ubiquiti EdgeSwitch",
            timeout=self._timeout,
        ) as cli:
            command = "show interfaces status all"
            output = cli.run_command(command, timeout=self._timeout)
            if _REJECTED.search(output):
                raise ValueError(f"EdgeSwitch rejected approved command {command!r}")
            return InterfaceCollection(
                device_name=extract_edgeswitch_hostname(cli.prompt),
                observations=parse_interfaces_status(output),
            )
