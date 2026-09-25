"""Cisco IOS, IOS-XE, and IOS-XR running-configuration VLAN observation."""

from __future__ import annotations

from contextlib import closing
import re
from dataclasses import replace

from orbitflow.models import InterfaceVlanObservation, VlanObject
from orbitflow.transport import DeviceSession
from orbitflow.vendors.vlan_types import VlanCollection, parse_vlan_list

from .interfaces import CiscoXRCLI, extract_ios_xr_hostname
from .ios import CiscoIOSCLI, extract_ios_hostname

_REJECTED = re.compile(
    r"%\s*(?:Invalid input|Unknown command|Unrecognized command|Incomplete command)",
    re.I,
)
_IOS_VLAN_DECLARATION = re.compile(
    r"vlan (?P<vlans>\d+(?:\s*-\s*\d+)?(?:[\s,]+\d+(?:\s*-\s*\d+)?)*)"
)


def _blocks(
    output: str, *, preserve_body_indentation: bool = False
) -> list[tuple[str, list[str]]]:
    blocks: list[tuple[str, list[str]]] = []
    heading = ""
    body: list[str] = []
    for raw in output.splitlines() + ["!"]:
        line = raw.rstrip()
        if line and not line[0].isspace() and line != "!":
            if heading:
                blocks.append((heading, body))
            heading, body = line.strip(), []
        elif line == "!":
            if heading:
                blocks.append((heading, body))
            heading, body = "", []
        elif heading:
            body.append(line if preserve_body_indentation else line.strip())
    return blocks


def _description(lines: list[str]) -> str:
    return next((line[12:] for line in lines if line.startswith("description ")), "")


def parse_ios_running_config(
    output: str, *, evc: bool = False
) -> tuple[tuple[InterfaceVlanObservation, ...], tuple[VlanObject, ...]]:
    interfaces: list[InterfaceVlanObservation] = []
    objects: list[VlanObject] = []
    for heading, lines in _blocks(output):
        vlan = _IOS_VLAN_DECLARATION.fullmatch(heading)
        if vlan:
            vlan_ids = parse_vlan_list(vlan.group("vlans"))
            name = next((x[5:] for x in lines if x.startswith("name ")), "")
            objects.extend(
                VlanObject(
                    "vlan",
                    str(vid),
                    name if len(vlan_ids) == 1 else "",
                    (vid,),
                )
                for vid in vlan_ids
            )
            continue
        match = re.fullmatch(r"interface (.+)", heading)
        if not match:
            continue
        name, description = match.group(1), _description(lines)
        mode_line = next((x for x in lines if x.startswith("switchport mode ")), "")
        access = next((x for x in lines if x.startswith("switchport access vlan ")), "")
        native = next(
            (x for x in lines if x.startswith("switchport trunk native vlan ")), ""
        )
        allowed = next(
            (x for x in lines if x.startswith("switchport trunk allowed vlan ")), ""
        )
        if mode_line or access or native or allowed:
            mode = mode_line.rsplit(" ", 1)[-1] if mode_line else "unknown"
            access_id = int(access.rsplit(" ", 1)[-1]) if access else None
            native_id = int(native.rsplit(" ", 1)[-1]) if native else None
            allowed_value = allowed.split("vlan ", 1)[1] if allowed else None
            if allowed_value == "none":
                allowed_ids = ()
            elif allowed_value is not None:
                allowed_ids = parse_vlan_list(allowed_value)
            else:
                allowed_ids = None
            refs = (
                set(allowed_ids or ())
                | ({access_id} if access_id else set())
                | ({native_id} if native_id else set())
            )
            interfaces.append(
                InterfaceVlanObservation(
                    name,
                    description,
                    mode,
                    access_vlan=access_id,
                    native_vlan=native_id,
                    allowed_vlans=allowed_ids,
                    untagged_vlans=(access_id,) if access_id else (),
                    referenced_vlans=tuple(sorted(refs)),
                    vlan_source="switchport",
                )
            )
        if evc:
            current: list[str] | None = None
            sid = ""
            for line in lines + ["service instance end ethernet"]:
                sm = re.fullmatch(r"service instance (\S+) ethernet", line)
                if sm:
                    if current is not None:
                        observation, service_object = _evc(
                            name, description, sid, current
                        )
                        interfaces.append(observation)
                        if service_object is not None and service_object not in objects:
                            objects.append(service_object)
                    sid, current = sm.group(1), []
                elif current is not None:
                    current.append(line)
    return tuple(interfaces), tuple(objects)


def _evc(
    name: str, description: str, sid: str, lines: list[str]
) -> tuple[InterfaceVlanObservation, VlanObject | None]:
    encap = next((x for x in lines if x.startswith("encapsulation dot1q ")), "")
    bridge = next((x for x in lines if x.startswith("bridge-domain ")), "")
    vlan = int(encap.split()[2]) if encap and encap.split()[2].isdigit() else None
    bridge_name = bridge.split()[1] if bridge else ""
    return (
        InterfaceVlanObservation(
            name,
            description,
            "service",
            service_vlan=vlan,
            outer_vlan=vlan,
            referenced_vlans=(vlan,) if vlan else (),
            vlan_source="service-instance",
            vlan_database_applicable=False,
            service_binding_type="bridge-domain" if bridge else "service-instance",
            service_binding_name=bridge_name or sid,
        ),
        VlanObject("bridge-domain", bridge_name, bridge_name) if bridge_name else None,
    )


def parse_ios_xr_running_config(
    output: str,
) -> tuple[tuple[InterfaceVlanObservation, ...], tuple[VlanObject, ...]]:
    interfaces: list[InterfaceVlanObservation] = []
    objects: list[VlanObject] = []
    bindings: dict[str, tuple[str, str]] = {}
    interface_descriptions: dict[str, str] = {}
    for heading, lines in _blocks(output, preserve_body_indentation=True):
        if heading.startswith("l2vpn"):
            bridge_group: tuple[int, str] | None = None
            bridge_domain: tuple[int, str] | None = None
            for raw in lines:
                indent = len(raw) - len(raw.lstrip())
                line = raw.strip()
                if bridge_domain is not None and indent <= bridge_domain[0]:
                    bridge_domain = None
                if bridge_group is not None and indent <= bridge_group[0]:
                    bridge_group = None
                if line.startswith("bridge group "):
                    bridge_group = (indent, line[13:])
                    bridge_domain = None
                elif line.startswith("bridge-domain "):
                    if bridge_group is None or indent <= bridge_group[0]:
                        continue
                    bridge_domain = (indent, line[14:])
                    identity = f"{bridge_group[1]}/{bridge_domain[1]}"
                    objects.append(
                        VlanObject("bridge-domain", identity, bridge_domain[1])
                    )
                elif bridge_domain is not None and indent > bridge_domain[0]:
                    assert bridge_group is not None
                    identity = f"{bridge_group[1]}/{bridge_domain[1]}"
                    if line.startswith("interface "):
                        bindings[line[10:].split()[0]] = ("bridge-domain", identity)
                    elif line.startswith("routed interface "):
                        bindings[line[17:].strip()] = ("bridge-domain", identity)
            continue
        match = re.fullmatch(r"interface (.+?)(?: (l2transport))?", heading)
        if not match:
            continue
        name, l2 = match.group(1), bool(match.group(2))
        stripped_lines = [line.strip() for line in lines]
        interface_descriptions[name] = _description(stripped_lines)
        encap = next(
            (
                x
                for x in stripped_lines
                if x.startswith("encapsulation dot1q ") or x == "encapsulation untagged"
            ),
            "",
        )
        if not encap:
            continue
        vlan = inner_vlan = None
        if encap.startswith("encapsulation dot1q "):
            tokens = encap.split()
            token = tokens[2]
            vlan = int(token) if token.isdigit() else None
            if "second-dot1q" in tokens:
                inner_token = tokens[tokens.index("second-dot1q") + 1]
                inner_vlan = int(inner_token) if inner_token.isdigit() else None
        binding = bindings.get(name, ("", ""))
        interfaces.append(
            InterfaceVlanObservation(
                name,
                _description(stripped_lines),
                "service" if l2 else "routed_subinterface",
                service_vlan=vlan,
                outer_vlan=vlan,
                inner_vlan=inner_vlan,
                untagged_vlans=() if vlan else (() if not encap else ()),
                referenced_vlans=tuple(
                    item for item in (vlan, inner_vlan) if item is not None
                ),
                vlan_source="dot1q" if vlan else "untagged",
                vlan_database_applicable=False,
                service_binding_type=binding[0],
                service_binding_name=binding[1],
            )
        )
    observed_names = {observation.interface_name for observation in interfaces}
    interfaces = [
        (
            replace(
                observation,
                service_binding_type=bindings[observation.interface_name][0],
                service_binding_name=bindings[observation.interface_name][1],
            )
            if observation.interface_name in bindings
            else observation
        )
        for observation in interfaces
    ]
    for interface_name, binding in bindings.items():
        if interface_name not in observed_names:
            interfaces.append(
                InterfaceVlanObservation(
                    interface_name,
                    description=interface_descriptions.get(interface_name, ""),
                    mode=(
                        "svi" if interface_name.upper().startswith("BVI") else "service"
                    ),
                    vlan_source="l2vpn-binding",
                    vlan_database_applicable=False,
                    service_binding_type=binding[0],
                    service_binding_name=binding[1],
                )
            )
    return tuple(interfaces), tuple(objects)


class CiscoVlanAdapter:
    def __init__(
        self, session: DeviceSession, *, timeout: float = 10.0, evc: bool = False
    ) -> None:
        self._session, self._timeout, self._evc = session, timeout, evc

    def collect(self) -> VlanCollection:
        with closing(CiscoIOSCLI(self._session, timeout=self._timeout)) as cli:
            output = cli.run_command("show running-config", timeout=self._timeout)
            if _REJECTED.search(output):
                raise ValueError("Cisco rejected approved command 'show running-config'")
            interfaces, objects = parse_ios_running_config(output, evc=self._evc)
            return VlanCollection(extract_ios_hostname(cli.prompt), interfaces, objects)


class CiscoXEVlanAdapter(CiscoVlanAdapter):
    def __init__(self, session: DeviceSession, *, timeout: float = 10.0) -> None:
        super().__init__(session, timeout=timeout, evc=True)


class CiscoXRVlanAdapter:
    def __init__(self, session: DeviceSession, *, timeout: float = 10.0) -> None:
        self._session, self._timeout = session, timeout

    def collect(self) -> VlanCollection:
        with closing(CiscoXRCLI(self._session, timeout=self._timeout)) as cli:
            output = cli.run_command("show running-config", timeout=self._timeout)
            if _REJECTED.search(output):
                raise ValueError(
                    "Cisco IOS-XR rejected approved command 'show running-config'"
                )
            interfaces, objects = parse_ios_xr_running_config(output)
            return VlanCollection(extract_ios_xr_hostname(cli.prompt), interfaces, objects)
