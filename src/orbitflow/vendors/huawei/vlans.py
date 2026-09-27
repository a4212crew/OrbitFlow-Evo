"""Huawei VRP current-configuration VLAN observation."""

import re

from orbitflow.models import InterfaceVlanObservation, VlanObject
from orbitflow.transport import DeviceSession
from orbitflow.vendors.common import DeviceCLI, open_prompt_cli
from orbitflow.vendors.vlan_types import VlanCollection, parse_vlan_list, forwarding
from .interfaces import extract_huawei_hostname

_REJECTED = re.compile(
    r"(?:Error:.*(?:Unrecognized|Wrong parameter)|\^\s*$)", re.I | re.M
)


def parse_huawei_config(
    output: str,
) -> tuple[tuple[InterfaceVlanObservation, ...], tuple[VlanObject, ...]]:
    database: set[int] = set()
    interfaces: list[InterfaceVlanObservation] = []
    service_objects: dict[str, VlanObject] = {}
    vlan_names = {}
    sections = re.split(r"^#\s*$", output, flags=re.M)
    for section in sections:
        lines = [x.strip() for x in section.splitlines() if x.strip()]
        if not lines:
            continue
        for line in lines:
            if line.startswith("vlan batch "):
                database.update(parse_vlan_list(line[11:], range_word="to"))
        declaration = re.fullmatch(r"vsi (\S+)(?: static)?", lines[0])
        if declaration:
            vsi_name = declaration.group(1)
            service_objects[vsi_name] = VlanObject("vsi", vsi_name)
        declaration = re.fullmatch(r"vlan (\d+)", lines[0])
        if declaration:
            vid = int(declaration.group(1))
            database.add(vid)
            vlan_names[vid] = next((x[12:] for x in lines if x.startswith("description ")), "")
        match = re.fullmatch(r"interface (.+)", lines[0])
        if not match:
            continue
        name = match.group(1)
        description = next((x[12:] for x in lines if x.startswith("description ")), "")
        access = next((x for x in lines if x.startswith((
            "port default vlan ", "port trunk pvid vlan ", "port hybrid pvid vlan "
        ))), "")
        trunk = next(
            (x for x in lines if x.startswith(("port trunk allow-pass vlan ", "port hybrid tagged vlan "))), ""
        )
        tagged_value = trunk.split("vlan ", 1)[1] if trunk else ""
        dot1q = next((x for x in lines if x.startswith("vlan-type dot1q ")), "")
        termination = next(
            (x for x in lines if x.startswith("dot1q termination vid ")), ""
        )
        control = next(
            (x for x in lines if re.fullmatch(r"control-vid \d+ dot1q-termination", x)),
            "",
        )
        vsi = next((x for x in lines if x.startswith("l2 binding vsi ")), "")
        if name.lower().startswith("vlanif") and name[6:].isdigit():
            vlan = int(name[6:])
            interfaces.append(
                InterfaceVlanObservation(
                    name,
                    description,
                    "svi",
                    access_vlan=vlan,
                    referenced_vlans=(vlan,),
                    vlan_source="Vlanif",
                )
            )
        elif access:
            vlan = int(access.rsplit(" ", 1)[-1])
            interfaces.append(
                InterfaceVlanObservation(
                    name,
                    description,
                    "access",
                    access_vlan=vlan,
                    untagged_vlans=(vlan,),
                    referenced_vlans=(vlan,),
                    vlan_source="port-default-vlan",
                )
            )
        elif trunk:
            vlans = parse_vlan_list(tagged_value, range_word="to") if tagged_value != "all" else ()
            interfaces.append(
                InterfaceVlanObservation(
                    name,
                    description,
                    "trunk",
                    allowed_vlans=vlans,
                    tagged_vlans=vlans,
                    referenced_vlans=vlans,
                    vlan_source="allow-pass",
                )
            )
        elif dot1q or termination or control or vsi:
            dot1q_match = re.search(r"vlan-type dot1q\s+(\d+)", dot1q)
            termination_match = re.search(r"termination vid\s+(\d+)", termination)
            control_match = re.search(r"control-vid\s+(\d+)", control)
            service_match = termination_match or dot1q_match
            service_vlan = int(service_match.group(1)) if service_match else None
            control_vlan = int(control_match.group(1)) if control_match else None
            referenced = tuple(
                sorted(
                    value for value in {service_vlan, control_vlan} if value is not None
                )
            )
            vsi_name = vsi[15:] if vsi else ""
            interfaces.append(
                InterfaceVlanObservation(
                    name,
                    description,
                    (
                        "service"
                        if vsi
                        else "routed_subinterface"
                    ),
                    service_vlan=service_vlan,
                    control_vlan=control_vlan,
                    outer_vlan=service_vlan,
                    referenced_vlans=referenced,
                    vlan_source=(
                        "dot1q-termination"
                        if (termination or control)
                        else "vlan-type-dot1q"
                    ),
                    vlan_database_applicable=False,
                    service_binding_type="vsi" if vsi else "",
                    service_binding_name=vsi_name,
                )
            )
        elif "undo portswitch" in lines or any(
            x.startswith(("ip address ", "ipv6 address ")) for x in lines
        ):
            interfaces.append(InterfaceVlanObservation(name, description, "routed"))
        else:
            continue
        item = interfaces[-1]
        if item.mode == "svi":
            item = forwarding(item, "routed", domains=(item.access_vlan,), mappings=[])
        elif item.mode in {"access", "trunk"}:
            tags = parse_vlan_list(tagged_value, range_word="to") if tagged_value and tagged_value != "all" else "ALL" if trunk else ()
            untagged = item.access_vlan or ""
            domains = ((str(untagged),) if untagged else ()) + (("ALL",) if tags == "ALL" else tuple(map(str, tags)))
            item = forwarding(item, "hybrid" if untagged and tags else item.mode,
                              untagged=untagged, tagged=tags, domains=domains)
        else:
            target = item.service_binding_name or "routed"
            item = forwarding(item, "service" if item.service_binding_name else "routed",
                              tagged=(item.outer_vlan,) if item.outer_vlan else (),
                              domains=(item.service_binding_name,) if item.service_binding_name else (),
                              mappings=[f"{item.outer_vlan} -> {target}"] if item.outer_vlan else [])
        interfaces[-1] = item
    objects = tuple(
        VlanObject("vlan", str(vlan), vlan_names.get(vlan, ""), vlan_ids=(vlan,)) for vlan in sorted(database)
    ) + tuple(service_objects[name] for name in sorted(service_objects))
    return tuple(interfaces), objects


class HuaweiVlanAdapter:
    def __init__(self, session: DeviceSession, *, timeout: float = 10.0, cli: DeviceCLI | None = None) -> None:
        self._cli = cli
        self._session, self._timeout = session, timeout

    def collect(self) -> VlanCollection:
        with open_prompt_cli(
            self._session, cli=self._cli,
            paging_command="screen-length 0 temporary",
            prompt_pattern=r"^([^\r\n]*(?:<[^<>\r\n]+>|\[[^\[\]\r\n]+\]))[ \t]*$",
            rejected=lambda x: bool(_REJECTED.search(x)),
            platform_name="Huawei VRP",
            timeout=self._timeout,
        ) as cli:
            output = cli.run_command("display current-configuration", timeout=self._timeout)
            if _REJECTED.search(output):
                raise ValueError(
                    "Huawei VRP rejected approved command 'display current-configuration'"
                )
            interfaces, objects = parse_huawei_config(output)
            return VlanCollection(extract_huawei_hostname(cli.prompt), interfaces, objects)
