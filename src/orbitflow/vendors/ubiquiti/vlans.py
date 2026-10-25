"""Ubiquiti EdgeSwitch running-configuration VLAN observation."""
from orbitflow.vendors.aggregation import from_configuration

import re

from orbitflow.vendors.configuration_facts import observe_configuration
from orbitflow.models import InterfaceVlanObservation, VlanObject
from orbitflow.transport import DeviceSession
from orbitflow.vendors.common import DeviceCLI, open_prompt_cli
from orbitflow.vendors.vlan_types import VlanCollection, parse_vlan_list, forwarding, visible_objects
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
            active, exclusions, configured_tags = set(), set(), set()
            for line in body:
                if line.startswith("vlan participation include "):
                    ids = set(parse_vlan_list(line[27:]))
                    active.update(ids)
                    exclusions.difference_update(ids)
                elif line.startswith("vlan participation exclude "):
                    ids = set(parse_vlan_list(line[27:]))
                    active.difference_update(ids)
                    exclusions.update(ids)
                elif line.startswith("vlan tagging "):
                    value = line[13:]
                    disable = value.endswith(" disable")
                    value = re.sub(r" (?:enable|disable)$", "", value)
                    ids = set(parse_vlan_list(value))
                    if disable:
                        configured_tags.difference_update(ids)
                    else:
                        configured_tags.update(ids)
            included = tuple(sorted(active))
            excluded = tuple(sorted(exclusions))
            tagged = tuple(sorted(configured_tags))
            refs = tuple(
                sorted(set(included) | set(tagged) | ({pvid} if pvid else set()))
            )
            tagged = tuple(sorted(set(tagged) & active))
            untagged = pvid if pvid in active and pvid not in tagged else ""
            trunk_only = ("switchport mode trunk" in body
                          and all(not line.startswith("switchport ") or line == "switchport mode trunk" for line in body))
            if refs or excluded or trunk_only:
                mode = (
                    "trunk"
                    if (tagged and set(tagged) == set(included)) or (trunk_only and not refs and not excluded)
                    else ("hybrid" if tagged else "access")
                )
                interfaces.append(
                    InterfaceVlanObservation(
                        name,
                        description,
                        mode,
                        pvid=pvid,
                        tagged_vlans=tagged,
                        configured_tagged_vlans=tuple(sorted(configured_tags)),
                        configured_included_vlans=included,
                        untagged_vlans=(pvid,) if pvid else (),
                        excluded_vlans=excluded,
                        referenced_vlans=refs,
                        vlan_source="participation",
                    )
                )
                interfaces[-1] = forwarding(interfaces[-1], "hybrid" if untagged and tagged else "trunk" if tagged or (not refs and not excluded and trunk_only) else "access",
                    untagged=untagged, tagged=tagged, domains=tuple(sorted(active)))
            continue
        index += 1
    objects = tuple(
        VlanObject("vlan", str(v), vlan_names.get(v, ""), (v,))
        for v in sorted(database)
    )
    return tuple(interfaces), visible_objects(objects)


class EdgeSwitchVlanAdapter:
    def __init__(self, session: DeviceSession, *, timeout: float = 10.0, cli: DeviceCLI | None = None, preserve_full_evidence=False) -> None:
        self._preserve_full_evidence = preserve_full_evidence
        self._cli = cli
        self._session, self._timeout = session, timeout

    def collect(self) -> VlanCollection:
        with open_prompt_cli(
            self._session, cli=self._cli,
            paging_command="terminal length 0",
            prompt_pattern=r"^([^\r\n]+[>#])[ \t]*$",
            rejected=lambda x: bool(_REJECTED.search(x)),
            platform_name="Ubiquiti EdgeSwitch",
            timeout=self._timeout,
        ) as cli:
            output = cli.run_command("show running-config", timeout=self._timeout)
            if _REJECTED.search(output):
                raise ValueError(
                    "EdgeSwitch rejected approved command 'show running-config'"
                )
            if self._preserve_full_evidence:
                if not output.strip() or not re.search(r'(?m)^\s*(?:hostname |version |vlan database|interface |!Current Configuration)', output):
                    raise ValueError('running configuration unavailable')
                opened = False
                for line in output.splitlines():
                    text = line.strip()
                    if text == 'vlan database' or text.startswith('interface '):
                        if opened:
                            raise ValueError('incomplete running configuration')
                        opened = True
                    elif text == 'exit':
                        opened = False
                if opened:
                    raise ValueError('incomplete running configuration')
            interfaces, objects = parse_edgeswitch_config(output)
            return VlanCollection(
                extract_edgeswitch_hostname(cli.prompt), interfaces, objects,
                observe_configuration(output, "ubiquiti_edgeswitch", preserve_full_evidence=self._preserve_full_evidence), from_configuration(output, "ubiquiti_edgeswitch")
            )

    def lookup(self, vlan_id):
        if type(vlan_id) is not int or not 2 <= vlan_id <= 4093:
            raise ValueError("invalid VLAN lookup ID")
        try:
            with open_prompt_cli(self._session, cli=self._cli, paging_command="terminal length 0",
                                 prompt_pattern=r"^([^\r\n]+[>#])[ \t]*$", rejected=lambda x: bool(_REJECTED.search(x)),
                                 platform_name="Ubiquiti EdgeSwitch", timeout=self._timeout) as cli:
                output = cli.run_command(f"show vlan {vlan_id}", timeout=self._timeout)
        except Exception:
            return dict(status="error", name="", operational_status="", ports=[], evidence=[])
        return parse_vlan_lookup(output, vlan_id)


def parse_vlan_lookup(output, vlan_id):
    """Preserve operational Current/Configured/Tagging independently."""
    from orbitflow.vendors.configuration_facts import _safe_source
    result = dict(status="unknown", name="", operational_status="", vlan_type="", ports_complete=False, ports=[],
                  evidence=[dict(source_filename=f"show vlan {vlan_id}", line=i, excerpt=_safe_source(line, 'ubiquiti_edgeswitch'))
                            for i, line in enumerate(output.splitlines(), 1)])
    if _REJECTED.search(output):
        result['status'] = 'error'
        return result
    if re.fullmatch(r"\s*VLAN does not exist\.\s*", output, re.I):
        result['status'] = 'absent'
        return result
    vid = re.search(r"(?im)^\s*VLAN ID:\s*(\d+)\s*$", output)
    name = re.search(r"(?im)^\s*VLAN Name:\s*(.*?)\s*$", output)
    kind = re.search(r"(?im)^\s*VLAN Type:\s*(\w+)\s*$", output)
    if vid and int(vid[1]) == vlan_id and name and kind:
        result.update(status='present', name=name[1], operational_status=kind[1], vlan_type=kind[1], vlan_id=vlan_id)
    table = False
    malformed = False
    for line in output.splitlines():
        if re.search(r'^\s*(?:Port|Interface)\s+Current\s+Configured\s+Tagging\s*$', line, re.I):
            table = True
            continue
        match = re.fullmatch(r"\s*(\d+/\d+|lag \d+)\s+(Include|Exclude|Auto)\s+(Include|Exclude|Auto)\s+(Tagged|Untagged)\s*", line, re.I)
        if match:
            result['ports'].append(dict(interface=match[1], current=match[2], configured=match[3], tagging=match[4]))
        elif table and line.strip() and not re.fullmatch(r'[\s-]+', line):
            malformed = True
    result['ports_complete'] = table and not malformed
    return result
