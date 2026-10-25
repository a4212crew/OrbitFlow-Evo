"""Cisco IOS, IOS-XE, and IOS-XR running-configuration VLAN observation."""

from __future__ import annotations

from orbitflow.vendors.aggregation import from_configuration

import re
from dataclasses import replace

from orbitflow.vendors.configuration_facts import observe_configuration
from orbitflow.models import InterfaceVlanObservation, VlanObject
from orbitflow.transport import DeviceSession
from orbitflow.vendors.common import DeviceCLI
from orbitflow.vendors.vlan_types import VlanCollection, parse_vlan_list, forwarding, aggregate_profiles, visible_objects

from orbitflow.vendors.interface_names import canonical_interface_name

from .interfaces import CiscoXRCLI, extract_ios_xr_hostname
from .ios import open_cisco_cli, CiscoIOSCLI, extract_ios_hostname

_REJECTED = re.compile(
    r"%\s*(?:Invalid input|Unknown command|Unrecognized command|Incomplete command)",
    re.I,
)
_IOS_VLAN_DECLARATION = re.compile(
    r"vlan (?P<vlans>\d+(?:\s*-\s*\d+)?(?:[\s,]+\d+(?:\s*-\s*\d+)?)*)"
)


def parse_vlan_lookup(output, vlan_id):
    """Cisco tabular lookup; no raw output escapes this parser."""
    unknown = dict(status="unknown", name="", operational_status="")
    if _REJECTED.search(output) or re.search(r"(?i)(?:%.*(?:error|failed|denied|ambiguous)|authorization failed)", output):
        return dict(unknown, status="error")
    if re.search(rf"(?i)(?:VLAN\s+{vlan_id}\s+(?:not found|does not exist)|VLAN id\s+{vlan_id}\s+not found)", output):
        return dict(unknown, status="absent")
    if not re.search(r"VLAN\s+Name\s+Status\s+Ports", output):
        return unknown
    rows = re.findall(rf"(?m)^\s*{vlan_id}\s+(.+)\s+(active|suspended|inactive|act/unsup|act/lshut)\b", output)
    if len(rows) != 1:
        return unknown
    return dict(status="present", vlan_id=vlan_id, name=rows[0][0].rstrip(), operational_status=rows[0][1])


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
    output: str, *, evc: bool = False, vlan_database: bool = True
) -> tuple[tuple[InterfaceVlanObservation, ...], tuple[VlanObject, ...]]:
    interfaces: list[InterfaceVlanObservation] = []
    objects: list[VlanObject] = []
    blocks = _blocks(output)
    memberships: dict[tuple[str, str], str] = {}
    if evc:
        for heading, lines in blocks:
            bridge = re.fullmatch(r"bridge-domain (\S+)", heading)
            if bridge:
                for line in lines:
                    member = re.fullmatch(r"member (\S+) service-instance (\S+)(?:\s+.*)?", line)
                    if member:
                        key = (canonical_interface_name("cisco_ios", member.group(1)), member.group(2))
                        memberships[key] = bridge.group(1)
    for heading, lines in blocks:
        vlan = _IOS_VLAN_DECLARATION.fullmatch(heading)
        if vlan:
            if not vlan_database:
                continue
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
        bridge = re.fullmatch(r"bridge-domain (\S+)", heading)
        if evc and bridge:
            obj = VlanObject("bridge_domain", bridge.group(1))
            if obj not in objects:
                objects.append(obj)
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
        has_evc = evc and any(x.startswith("service instance ") for x in lines)
        if (mode_line or access or native or allowed) and not has_evc:
            mode = mode_line.rsplit(" ", 1)[-1] if mode_line else "unknown"
            access_id = int(access.rsplit(" ", 1)[-1]) if access else None
            native_id = int(native.rsplit(" ", 1)[-1]) if native else None
            allowed_value = allowed.split("vlan ", 1)[1] if allowed else None
            if allowed_value == "none":
                allowed_ids = ()
            elif allowed_value == "all":
                allowed_ids = None
            elif allowed_value is not None and allowed_value.split()[0] in {"add", "remove", "except"}:
                # Ordered operations are retained in configuration facts for the
                # family audit resolver; legacy profiles do not replay them.
                allowed_ids = ()
            elif allowed_value is not None:
                try:
                    allowed_ids = parse_vlan_list(allowed_value)
                except ValueError:
                    # Typed config facts retain the unsupported operation for
                    # audit/planning; do not abort unrelated description rows.
                    allowed_ids = ()
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
        if not (mode_line or access or native or allowed):
            svi = re.fullmatch(r"Vlan(\d+)", name, re.I)
            encap = next((x for x in lines if x.startswith("encapsulation dot1Q ") or x.startswith("encapsulation dot1q ")), "")
            outer = int(encap.split()[2]) if encap and encap.split()[2].isdigit() else None
            routed = svi or outer or "no switchport" in lines or any(
                x.startswith(("ip address ", "ipv6 address ")) for x in lines
            )
            if routed and not any(x.startswith("service instance ") for x in lines):
                interfaces.append(forwarding(
                    InterfaceVlanObservation(name, description), "routed",
                    tagged=(outer,) if outer else (),
                    domains=(svi.group(1),) if svi else (),
                    mappings=[f"{outer} -> routed"] if outer else [],
                ))
        if evc:
            current: list[str] | None = None
            sid = ""
            for line in lines + ["service instance end ethernet"]:
                sm = re.fullmatch(r"service instance (\S+) ethernet", line)
                if sm:
                    if current is not None:
                        observation, service_object = _evc(
                            name, description, sid, current,
                            memberships.get((canonical_interface_name("cisco_ios", name), sid), "")
                        )
                        interfaces.append(observation)
                        if service_object is not None and service_object not in objects:
                            objects.append(service_object)
                    sid, current = sm.group(1), []
                elif current is not None:
                    current.append(line)
    normalized = []
    for item in interfaces:
        if item.port_type:
            normalized.append(item)
        elif item.vlan_source == "switchport":
            trunk = item.mode == "trunk" or item.native_vlan is not None or item.allowed_vlans is not None
            untagged = (item.native_vlan or 1) if trunk else (item.access_vlan or 1)
            tagged = ("ALL" if item.allowed_vlans is None else item.allowed_vlans or "NONE") if trunk else ()
            domains = (str(untagged),) + (("ALL",) if tagged == "ALL" else () if isinstance(tagged, str) else tuple(map(str, tagged)))
            normalized.append(forwarding(item, "trunk" if trunk else "access", untagged=untagged, tagged=tagged, domains=domains))
        else:
            normalized.append(item)
    return aggregate_profiles(normalized), visible_objects(objects)


def _evc(
    name: str, description: str, sid: str, lines: list[str], global_bridge: str = ""
) -> tuple[InterfaceVlanObservation, VlanObject | None]:
    encap = next((x for x in lines if x.startswith("encapsulation dot1q ")), "")
    bridge = next((x for x in lines if x.startswith("bridge-domain ")), "")
    vlan = int(encap.split()[2]) if encap and encap.split()[2].isdigit() else None
    outer_expression = encap.split()[2] if encap else ""
    outer_ids = parse_vlan_list(outer_expression) if outer_expression else ()
    bridge_name = bridge.split()[1] if bridge else global_bridge
    observation = InterfaceVlanObservation(
        name,
        description,
        "service",
        service_vlan=vlan,
        outer_vlan=vlan,
        referenced_vlans=outer_ids,
        vlan_source="service-instance",
        vlan_database_applicable=False,
        service_binding_type="bridge-domain" if bridge_name else "service-instance",
        service_binding_name=bridge_name or sid,
    )
    untagged = "encapsulation untagged" in lines
    inner = re.search(r"second-dot1q (\S+)", encap)
    inner_expression = ('1-4094' if inner[1] == 'any' else inner[1]) if inner else ''
    inner_ids = parse_vlan_list(inner_expression) if inner_expression else ()
    observation = replace(observation, inner_vlan=inner_ids[0] if len(inner_ids) == 1 else None,
                          outer_vlan_expression=outer_expression, inner_vlan_expression=inner_expression)
    target = bridge_name
    ingress = "untagged" if untagged else outer_expression
    if inner and (len(outer_ids) > 1 or len(inner_ids) > 1):
        ingress += f" second-dot1q {inner_expression}"
    return (
        forwarding(observation, "evc", untagged=(target if target.isdigit() else "UNTAGGED") if untagged else "",
                   tagged=outer_ids, domains=(target,) if target else (),
                   mappings=[f"{ingress} -> {target}"] if ingress and target else []),
        VlanObject("bridge_domain", bridge_name) if bridge_name else None,
    )


def parse_ios_xr_running_config(
    output: str,
) -> tuple[tuple[InterfaceVlanObservation, ...], tuple[VlanObject, ...]]:
    interfaces: list[InterfaceVlanObservation] = []
    objects: list[VlanObject] = []
    bindings: dict[str, tuple[str, str]] = {}
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
                        VlanObject("bridge_domain", identity, bridge_domain[1], domain_id=bridge_domain[1])
                    )
                elif bridge_domain is not None and indent > bridge_domain[0]:
                    assert bridge_group is not None
                    identity = f"{bridge_group[1]}/{bridge_domain[1]}"
                    if line.startswith("interface "):
                        bindings[canonical_interface_name("cisco_xr", line[10:].split()[0])] = ("bridge-domain", identity)
                    elif line.startswith("routed interface "):
                        bindings[canonical_interface_name("cisco_xr", line[17:].strip())] = ("bridge-domain", identity)
            continue
        match = re.fullmatch(r"interface (.+?)(?: (l2transport))?", heading)
        if not match:
            continue
        name, l2 = match.group(1), bool(match.group(2))
        stripped_lines = [line.strip() for line in lines]
        encap = next(
            (
                x
                for x in stripped_lines
                if x.startswith("encapsulation dot1q ") or x == "encapsulation untagged"
            ),
            "",
        )
        vlan = inner_vlan = None
        if encap.startswith("encapsulation dot1q "):
            tokens = encap.split()
            token = tokens[2]
            vlan = int(token) if token.isdigit() else None
            if "second-dot1q" in tokens:
                inner_token = tokens[tokens.index("second-dot1q") + 1]
                inner_vlan = int(inner_token) if inner_token.isdigit() else None
        binding = bindings.get(canonical_interface_name("cisco_xr", name), ("", ""))
        interfaces.append(
            InterfaceVlanObservation(
                name,
                _description(stripped_lines),
                "service" if l2 else "routed_subinterface",
                service_vlan=vlan,
                outer_vlan=vlan,
                inner_vlan=inner_vlan,
                referenced_vlans=tuple(
                    item for item in (vlan, inner_vlan) if item is not None
                ),
                vlan_source="dot1q" if vlan else "untagged" if encap else "",
                vlan_database_applicable=False,
                service_binding_type=binding[0],
                service_binding_name=binding[1],
            )
        )
    normalized = []
    for item in interfaces:
        binding = bindings.get(canonical_interface_name("cisco_xr", item.interface_name))
        domain = binding[1].split("/", 1)[1] if binding else ""
        if binding:
            item = replace(item, service_binding_type=binding[0], service_binding_name=binding[1])
        routed = item.mode != "service"
        ingress = str(item.outer_vlan) if item.outer_vlan else "untagged" if item.vlan_source == "untagged" else ""
        target = "routed" if routed else domain
        normalized.append(forwarding(item, "routed" if routed else "service",
            untagged=(domain if domain.isdigit() else "UNTAGGED") if ingress == "untagged" else "",
            tagged=(item.outer_vlan,) if item.outer_vlan else (),
            domains=(domain,) if domain else (),
            mappings=[f"{ingress} -> {target}"] if ingress and target else []))
    return tuple(normalized), visible_objects(objects)


def parse_service_detail(output, interface, service_instance_id):
    """Operational EVC fields reuse the saved-config fact grammar."""
    from dataclasses import asdict
    from orbitflow.vendors.configuration_facts import _safe_source
    result = dict(status='unknown', facts=[], operational_status='', evidence=[
        dict(source_filename=f'service detail {interface} {service_instance_id}', line=i, excerpt=_safe_source(line, 'cisco_ios'))
        for i, line in enumerate(output.splitlines(), 1)])
    if _REJECTED.search(output) or re.search(r'(?im)^\s*%.*(?:error|failed|denied|ambiguous|timeout)|authorization failed', output):
        result['status'] = 'error'
        return result
    def port_key(name):
        # IOS accepts the single-letter GigabitEthernet abbreviation too.
        return canonical_interface_name('cisco_ios', re.sub(r'(?i)^g(?=\d)', 'Gi', name))

    ids = re.findall(r'(?im)^\s*(?:Service Instance ID|Id):\s*(\d+)\s*$', output)
    ports = re.findall(r'(?im)^\s*(?:Associated Interface|Interface):\s*(\S+)\s*$', output)
    matches = bool(ids == [str(service_instance_id)] and len(ports) == 1 and
                   port_key(ports[0]) == port_key(interface))
    if re.search(r'(?i)does not exist', output):
        # Only explicitly identified requested targets prove absence.
        negatives = re.findall(r'(?im)^\s*Service Instance(?: ID)?\s+(\d+)\s+(?:on\s+)?interface\s+(\S+)\s+does not exist\s*\.?\s*$', output)
        if (not ids and not ports and len(negatives) == 1 and
                int(negatives[0][0]) == service_instance_id and
                port_key(negatives[0][1]) == port_key(interface)):
            result['status'] = 'absent'
        return result
    if not matches:
        return result
    lines = []
    valid_domains = True
    for line in output.splitlines():
        enc = re.fullmatch(r'\s*Encapsulation:\s*(.+?)\s*', line, re.I)
        rewrite = re.fullmatch(r'\s*Rewrite:\s*(.+?)\s*', line, re.I)
        bd = re.fullmatch(r'\s*Bridge[- ]domain:\s*(.+?)\s*', line, re.I)
        state = re.fullmatch(r'\s*State:\s*(Up|Down)\s*', line, re.I)
        description = re.fullmatch(r'\s*Description:\s*(.+?)\s*', line, re.I)
        if enc:
            value = re.sub(r'\s+vlan protocol type 0x8100\b', '', enc[1], flags=re.I)
            lines.append(' encapsulation ' + value.lower())
        if description:
            lines.append(' description ' + description[1])
        if rewrite and rewrite[1].lower() != 'none':
            value = re.sub(r' vlan-type 0x[0-9a-fA-F]+', '', rewrite[1])
            lines.append(' rewrite ' + value)
        if bd:
            lines.append(' bridge-domain ' + bd[1])
            valid_domains = valid_domains and bool(re.fullmatch(r'\d+(?: split-horizon group \d+)?', bd[1]))
        if state:
            result['operational_status'] = state[1].lower()
    facts = observe_configuration('interface ' + interface + '\n service instance ' + str(service_instance_id) + ' ethernet\n' +
                                  '\n'.join(' ' + line for line in lines), 'cisco_ios')
    children = facts[0].children[0].children if facts and facts[0].children else ()
    from orbitflow.compliance.vlan import safe_data
    result['facts'] = safe_data([asdict(n) for n in children])
    from orbitflow.vendors.cisco.evc import service_signature
    # Existence and forwarding completeness are distinct: a valid EFP may
    # have no forwarding microblock. The planner still checks domain facts.
    if (valid_domains and service_signature(dict(children=result['facts'])) is not None and
            (result['operational_status'] or any(n.kind == 'bridge_domain' for n in children)) and
            sum(n.kind == 'bridge_domain' for n in children) <= 1 and
            sum(n.kind == 'tag_rewrite' for n in children) <= 1 and
            len(re.findall(r'(?im)^\s*State:', output)) <= 1):
        result['status'] = 'present'
    return result


class CiscoVlanAdapter:
    def __init__(
        self, session: DeviceSession, *, timeout: float = 10.0, evc: bool = False, cli: DeviceCLI | None = None, preserve_full_evidence: bool = False
    ) -> None:
        self._preserve_full_evidence = preserve_full_evidence
        self._cli = cli
        self._session, self._timeout, self._evc = session, timeout, evc

    vlan_database = True

    def lookup(self, vlan_id, *, preserve_evidence=False):
        if type(vlan_id) is not int or not 1 <= vlan_id <= 4094:
            raise ValueError("invalid VLAN lookup ID")
        try:
            with open_cisco_cli(self._session, cli=self._cli, cli_type=CiscoIOSCLI, timeout=self._timeout) as cli:
                output = cli.run_command(f"show vlan id {vlan_id}", timeout=self._timeout)
        except Exception:
            return dict(status="error", name="", operational_status="")
        result = parse_vlan_lookup(output, vlan_id)
        if preserve_evidence:
            from orbitflow.vendors.configuration_facts import _safe_source
            result['evidence'] = [dict(source_filename=f'show vlan id {vlan_id}', line=i, excerpt=_safe_source(line, 'cisco_ios'))
                                  for i, line in enumerate(output.splitlines(), 1)]
        return result

    def service_detail(self, interface, service_instance_id):
        if not re.fullmatch(r"[A-Za-z][A-Za-z0-9/-]+", interface) or type(service_instance_id) is not int or not 1 <= service_instance_id <= 4000:
            raise ValueError("invalid service detail target")
        try:
            with open_cisco_cli(self._session, cli=self._cli, cli_type=CiscoIOSCLI, timeout=self._timeout) as cli:
                output = cli.run_command(f"show ethernet service instance id {service_instance_id} interface {interface} detail", timeout=self._timeout)
        except Exception:
            return dict(status='error', facts=[], evidence=[], operational_status='')
        return parse_service_detail(output, interface, service_instance_id)

    def collect(self) -> VlanCollection:
        with open_cisco_cli(self._session, cli=self._cli, cli_type=CiscoIOSCLI, timeout=self._timeout) as cli:
            output = cli.run_command("show running-config", timeout=self._timeout)
            if not output.strip() or _REJECTED.search(output) or re.search(r"(?im)^%.*(?:error|failed)", output):
                raise ValueError("Cisco rejected approved command 'show running-config'")
            if not re.search(r"(?m)^(?:hostname |interface |vlan |version |Building configuration|Current configuration)", output):
                raise ValueError("running configuration unavailable")
            if self._preserve_full_evidence and self._evc and not re.search(r'(?m)^end\s*$', output):
                raise ValueError('incomplete running configuration')
            interfaces, objects = parse_ios_running_config(output, evc=self._evc, vlan_database=self.vlan_database)
            return VlanCollection(extract_ios_hostname(cli.prompt), interfaces, objects,
                                  observe_configuration(output, "cisco_ios", preserve_full_evidence=self._preserve_full_evidence), from_configuration(output, "cisco_ios"))


class CiscoXEVlanAdapter(CiscoVlanAdapter):
    def __init__(self, session: DeviceSession, *, timeout: float = 10.0, cli: DeviceCLI | None = None, preserve_full_evidence: bool = False) -> None:
        super().__init__(session, timeout=timeout, evc=True, cli=cli, preserve_full_evidence=preserve_full_evidence)


class CiscoASRVlanAdapter(CiscoXEVlanAdapter):
    """Supported ASR920 forwarding objects are EVC bridge domains."""

    vlan_database = False


class CiscoXRVlanAdapter:
    def __init__(self, session: DeviceSession, *, timeout: float = 10.0, cli: DeviceCLI | None = None) -> None:
        self._cli = cli
        self._session, self._timeout = session, timeout

    def collect(self) -> VlanCollection:
        with open_cisco_cli(self._session, cli=self._cli, cli_type=CiscoXRCLI, timeout=self._timeout) as cli:
            output = cli.run_command("show running-config", timeout=self._timeout)
            if _REJECTED.search(output):
                raise ValueError(
                    "Cisco IOS-XR rejected approved command 'show running-config'"
                )
            interfaces, objects = parse_ios_xr_running_config(output)
            return VlanCollection(extract_ios_xr_hostname(cli.prompt), interfaces, objects,
                                  observe_configuration(output, "cisco_xr"), from_configuration(output, "cisco_xr"))
