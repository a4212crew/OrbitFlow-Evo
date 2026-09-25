"""Ubiquiti EdgeSwitch running-configuration VLAN observation."""

from contextlib import closing
import re

from orbitflow.models import InterfaceVlanObservation, VlanObject
from orbitflow.transport import DeviceSession
from orbitflow.vendors.common import PromptCLI
from orbitflow.vendors.vlan_types import VlanCollection, parse_vlan_list
from .interfaces import extract_edgeswitch_hostname

_REJECTED = re.compile(
    r"(?:%\s*(?:Invalid input|Unknown command)|Unrecognized command)", re.I
)


def parse_edgeswitch_config(
    output: str,
) -> tuple[tuple[InterfaceVlanObservation, ...], tuple[VlanObject, ...]]:
    database: set[int] = set()
    vlan_names: dict[int, str] = {}
    interfaces: list[InterfaceVlanObservation] = []
    lines = output.splitlines()
    index = 0
    while index < len(lines):
        heading = lines[index].strip()
        if heading == "vlan database":
            index += 1
            while index < len(lines) and lines[index].strip() != "exit":
                line = lines[index].strip()
                if line.startswith("vlan "):
                    name_match = re.fullmatch(r"vlan name (\d+) ([\"'])(.*?)\2", line)
                    if name_match:
                        vlan_id = int(name_match.group(1))
                        database.add(vlan_id)
                        vlan_names[vlan_id] = name_match.group(3)
                    else:
                        database.update(parse_vlan_list(line[5:]))
                index += 1
            if index < len(lines):
                index += 1
            continue
        match = re.fullmatch(r"interface (.+)", heading)
        if match:
            name = match.group(1)
            body = []
            index += 1
            while index < len(lines) and lines[index].strip() != "exit":
                body.append(lines[index].strip())
                index += 1
            if index < len(lines):
                index += 1
            description = ""
            for line in body:
                if line.startswith("description "):
                    description = line[12:].strip()
                    if (
                        len(description) >= 2
                        and description[0] in "\"'"
                        and description[-1] == description[0]
                    ):
                        description = description[1:-1]
                    break
            pvid_line = next((x for x in body if x.startswith("vlan pvid ")), "")
            include = next(
                (x for x in body if x.startswith("vlan participation include ")), ""
            )
            exclude = next(
                (x for x in body if x.startswith("vlan participation exclude ")), ""
            )
            tagging = next((x for x in body if x.startswith("vlan tagging ")), "")
            pvid = int(pvid_line.split()[-1]) if pvid_line else None
            included = parse_vlan_list(include[27:]) if include else ()
            excluded = parse_vlan_list(exclude[27:]) if exclude else ()
            tagged = parse_vlan_list(tagging[13:]) if tagging else ()
            refs = tuple(
                sorted(set(included) | set(tagged) | ({pvid} if pvid else set()))
            )
            if refs or excluded:
                mode = (
                    "trunk"
                    if tagged and set(tagged) == set(included)
                    else ("hybrid" if tagged else "access")
                )
                interfaces.append(
                    InterfaceVlanObservation(
                        name,
                        description,
                        mode,
                        pvid=pvid,
                        tagged_vlans=tagged,
                        untagged_vlans=(pvid,) if pvid else (),
                        excluded_vlans=excluded,
                        referenced_vlans=refs,
                        vlan_source="participation",
                    )
                )
            continue
        index += 1
    objects = tuple(
        VlanObject("vlan", str(v), vlan_names.get(v, ""), (v,))
        for v in sorted(database)
    )
    return tuple(interfaces), objects


class EdgeSwitchVlanAdapter:
    def __init__(self, session: DeviceSession, *, timeout: float = 10.0) -> None:
        self._session, self._timeout = session, timeout

    def collect(self) -> VlanCollection:
        with closing(PromptCLI(
            self._session,
            paging_command="terminal length 0",
            prompt_pattern=r"^([^\r\n]+[>#])[ \t]*$",
            rejected=lambda x: bool(_REJECTED.search(x)),
            platform_name="Ubiquiti EdgeSwitch",
            timeout=self._timeout,
        )) as cli:
            output = cli.run_command("show running-config", timeout=self._timeout)
            if _REJECTED.search(output):
                raise ValueError(
                    "EdgeSwitch rejected approved command 'show running-config'"
                )
            interfaces, objects = parse_edgeswitch_config(output)
            return VlanCollection(
                extract_edgeswitch_hostname(cli.prompt), interfaces, objects
            )
