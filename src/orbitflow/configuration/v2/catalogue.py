"""Versioned, UI-independent schemas for the approved bulk planning catalogue."""
from dataclasses import dataclass
import ipaddress
import re

from orbitflow.configuration.plans import PlanError, require
from orbitflow.logging import sanitize_text

VERSION = "2.3"
FAMILIES = {
    "C3750X": ("cisco_ios", "c3750x_switching"),
    "C3850X": ("cisco_xe", "c3850_switching"),
    "ME3600X": ("cisco_ios", "me3600x_evc"),
    "ASR920": ("cisco_xe", "asr920_evc"),
    "NCS540": ("cisco_xr", ""),
    "EdgeSwitch": ("ubiquiti_edgeswitch", ""),
    "NE05E": ("huawei_vrp", ""),
}
SCHEMAS = {
    "VLAN Database": ("vlan_id name", ""),
    "Access Port": ("interface vlan_id", "description"),
    "Trunk Port": ("interface action vlans", "native_vlan description"),
    "Interface Description": ("interface description", ""),
    "EVC": ("interface service_instance_id encapsulation bridge_domain", "outer_vlan inner_vlan rewrite push_vlan split_horizon_group description interface_description"),
    "L2VPN": ("interface subinterface encapsulation bridge_group bridge_domain", "outer_vlan inner_vlan description"),
    "VLAN Port": ("interface action", "tagged_vlans pvid description"),
    "Subinterface VSI": ("interface subinterface vlan_id encapsulation vsi", "description control_vid"),
    "Manual CLI": ("platform mode scope commands", ""),
}


def safe(value, *, multiline=False):
    require(isinstance(value, str) and 0 < len(value) <= (16000 if multiline else 256), "invalid text")
    require(all(32 <= ord(c) < 127 or (multiline and c in "\r\n\t") for c in value), "unsafe characters")
    require(sanitize_text(value) == value and not re.search(
        r"(?i)password|passwd|secret|token|credential|private.key|authorization|authentication|"
        r"\b(?:otp|community|key|username|cipher|encrypted|snmp-server|snmp-agent|local-user)\b|://|-----BEGIN", value),
        "secret-bearing input forbidden")
    return value


@dataclass(frozen=True)
class Template:
    id: str
    family: str
    function: str
    required: tuple
    optional: tuple

    @property
    def sheet(self):
        function = "Description" if self.function == "Interface Description" else self.function
        return "Manual CLI" if self.family == "All" else f"{self.family} {function}"

    @property
    def columns(self):
        return ("management_ip", *self.required, *self.optional)

    def validate(self, values):
        if self.function in {"EVC", "VLAN Port"}:
            return validate_service(self, values)
        require(type(values) is dict and set(values) <= set(self.columns), "unknown template field")
        require(all(values.get(k) not in (None, "") for k in ("management_ip", *self.required)), "required input missing")
        data = {k: v for k, v in values.items() if v not in (None, "")}
        numeric_fields = {"vlan_id", "outer_vlan", "inner_vlan", "native_vlan", "pvid", "control_vid",
                          "service_instance", "subinterface", "pop_tags", "push_vlan"}
        for k, v in data.items():
            require(type(v) is (int if k in numeric_fields else list if k == "vlans" else str), "invalid field type")
        try:
            data["management_ip"] = str(ipaddress.ip_address(data["management_ip"]))
        except ValueError:
            raise PlanError("invalid management IP") from None
        for k, v in data.items():
            if isinstance(v, str):
                safe(v, multiline=k == "commands")
                if k != "commands":
                    require(v == v.strip(), "surrounding whitespace forbidden")
        for k in ("vlan_id", "outer_vlan", "inner_vlan", "native_vlan", "pvid", "control_vid", "push_vlan"):
            if k in data:
                self.vlan(data[k])
        if "vlans" in data:
            require(type(data["vlans"]) is list and (0 if self.function == "VLAN Port" else 1) <= len(data["vlans"]) <= 4094, "invalid VLAN list")
            for v in data["vlans"]:
                self.vlan(v)
            require(len(set(data["vlans"])) == len(data["vlans"]), "duplicate VLAN")
        for k, upper in (("service_instance", 4000), ("subinterface", 4094 if self.family == "NE05E" else 2147483647), ("pop_tags", 2)):
            if k in data:
                lower = 0 if k == "subinterface" and self.family == "NCS540" else 1
                require(type(data[k]) is int and lower <= data[k] <= upper, "invalid numeric parameter")
        for k in ("interface", "vsi", "bridge_group"):
            if k in data:
                require(isinstance(data[k], str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9./:-]*|lag [0-9]+", data[k]), "invalid CLI identifier")
        if self.family in {"C3750X", "C3850X"} and "interface" in data:
            require(re.fullmatch(r"(?:FastEthernet|GigabitEthernet|TenGigabitEthernet|FortyGigabitEthernet|HundredGigE|Port-channel|Vlan|Loopback)[0-9]+(?:/[0-9]+)*(?:\.[0-9]+)?", data["interface"]), "interface: full canonical Cisco name required")
        if "bridge_domain" in data:
            require(isinstance(data["bridge_domain"], str) and re.fullmatch(r"[A-Za-z0-9_.:-]+", data["bridge_domain"]), "invalid bridge domain")
        for k in ("name", "description"):
            if k in data:
                require(isinstance(data[k], str) and not any(c in data[k] for c in '\";\\'), "invalid descriptive text")
        if "name" in data:
            require(len(data["name"]) <= (80 if self.family == "NE05E" else 32), "name too long")
            if self.family == "C3850X":
                require(re.fullmatch(r"[A-Za-z0-9_.:-]+", data["name"]), "invalid VLAN name")
            elif self.family not in {"EdgeSwitch", "NE05E"}:
                require(re.fullmatch(r"[A-Za-z0-9_.:-]+", data["name"]), "invalid VLAN name")
        if "action" in data:
            require(data["action"] in {"Add", "Remove", "Replace"}, "invalid action")
        if self.function == "L2VPN":
            require(data["encapsulation"] in {"dot1q", "QinQ", "untagged"}, "invalid encapsulation")
            enc = data["encapsulation"]
            require(("outer_vlan" in data) == (enc != "untagged"), "outer tag mismatch")
            require(("inner_vlan" in data) == (enc == "QinQ"), "inner tag mismatch")
            require("pop_tags" not in data or data["pop_tags"] <= (2 if enc == "QinQ" else 1 if enc == "dot1q" else 0), "invalid rewrite")
        if self.function == "Subinterface VSI":
            require(data["encapsulation"] in {"dot1q termination", "vlan-type dot1q"}, "unsupported encapsulation")
            require("control_vid" not in data or data["encapsulation"] == "dot1q termination", "unexpected control VID")
        if self.family == "All":
            require(data["platform"] in {v[0] for v in FAMILIES.values()}, "invalid platform")
            require(data["mode"] in {"configuration", "interface", "service"}, "invalid CLI mode")
        return data

    def vlan(self, value):
        require(type(value) is int and (2 if self.family == "EdgeSwitch" else 1) <= value <= (4093 if self.family == "EdgeSwitch" else 4094), "invalid VLAN")
        if self.family in {"C3750X", "C3850X", "ME3600X"}:
            require(value not in range(1002, 1006), "reserved VLAN")


def _catalogue():
    operations = {
        "C3750X": ("VLAN Database", "Access Port", "Trunk Port", "Interface Description"),
        "C3850X": ("VLAN Database", "Access Port", "Trunk Port", "Interface Description"),
        "ME3600X": ("VLAN Database", "EVC", "Interface Description"),
        "ASR920": ("EVC", "Interface Description"),
        "EdgeSwitch": ("VLAN Database", "VLAN Port", "Interface Description"),
        "NCS540": ("L2VPN", "Interface Description"),
        "NE05E": ("VLAN Database", "Subinterface VSI", "Interface Description"),
        "All": ("Manual CLI",),
    }
    return tuple(Template(f"{family.lower()}.{function.lower().replace(' ', '_')}.v2", family, function,
                          tuple(SCHEMAS[function][0].split()), tuple(SCHEMAS[function][1].split()))
                 for family, functions in operations.items() for function in functions)


CATALOGUE = _catalogue()
BY_ID = {t.id: t for t in CATALOGUE}
BY_SHEET = {t.sheet: t for t in CATALOGUE}


def normalize_display_inputs(template, values):
    """Parse human-entered scalars without depending on Excel or another UI."""
    p = {k: v for k, v in values.items() if v not in (None, "")}
    numeric = {"vlan_id", "outer_vlan", "inner_vlan", "native_vlan", "pvid", "control_vid",
               "subinterface", "service_instance", "service_instance_id", "split_horizon_group", "pop_tags", "push_vlan"}
    if template.function == "EVC":
        numeric -= {"outer_vlan", "inner_vlan"}
    if template.function == "EVC":
        numeric.add("bridge_domain")
    for k in numeric & p.keys():
        try:
            n = int(p[k])
            require(str(n) == str(p[k]) or type(p[k]) is int, "invalid integer")
            p[k] = n
        except (ValueError, TypeError):
            raise PlanError("invalid integer") from None
    if "vlans" in p and not isinstance(p["vlans"], list):
        vlans = []
        try:
            for part in str(p["vlans"]).split(","):
                limits = [int(v.strip()) for v in part.split("-")]
                require(1 <= len(limits) <= 2 and 1 <= limits[0] <= limits[-1] <= 4094, "invalid VLAN range")
                vlans.extend(range(limits[0], limits[-1] + 1))
            p["vlans"] = vlans
        except ValueError:
            raise PlanError("invalid VLAN list") from None
    if template.function == "L2VPN" and "bridge_domain" in p:
        p["bridge_domain"] = str(p["bridge_domain"])
    return template.validate(p)


def vlan_expression(value):
    """Compact approved match syntax, expanded through the shared VLAN parser."""
    from orbitflow.vendors.vlan_types import parse_vlan_list
    value = str(value) if type(value) is int else value
    require(type(value) is str and re.fullmatch(r"[0-9]+(?:-[0-9]+)?(?:,[0-9]+(?:-[0-9]+)?)*", value), "invalid VLAN expression")
    try:
        parse_vlan_list(value)
    except ValueError:
        raise PlanError("invalid VLAN expression") from None
    return value


def validate_service(t, values):
    require(type(values) is dict and set(values) <= set(t.columns), "unknown template field")
    require(all(values.get(k) not in (None, "") for k in ("management_ip", *t.required)), "required input missing")
    p = {k: v for k, v in values.items() if v not in (None, "")}
    require(type(p['management_ip']) is str, 'invalid management IP')
    try:
        p['management_ip'] = str(ipaddress.ip_address(p['management_ip']))
    except (ValueError, TypeError):
        raise PlanError("invalid management IP") from None
    require(type(p['interface']) is str and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9./:-]*|lag [0-9]+", p['interface']), "invalid interface")
    for k in ('description', 'interface_description'):
        if k in p:
            safe(p[k])
            require(not any(c in p[k] for c in '\";\\'), "invalid descriptive text")
    if t.function == 'VLAN Port':
        require(type(p['action']) is str and p['action'] in {'Add/Change', 'Remove'}, "invalid action")
        require(p['action'] != 'Remove' or 'pvid' not in p, "REMOVE_OPERATION_CANNOT_INCLUDE_PVID")
        require('tagged_vlans' in p or 'pvid' in p, "membership or PVID required")
        if 'tagged_vlans' in p:
            p['tagged_vlans'] = vlan_expression(p['tagged_vlans'])
            from orbitflow.vendors.vlan_types import parse_vlan_list
            for v in parse_vlan_list(p['tagged_vlans']):
                t.vlan(v)
        if 'pvid' in p:
            t.vlan(p['pvid'])
        return p
    require(re.fullmatch(r'(?:GigabitEthernet|TenGigabitEthernet|FastEthernet|Port-channel|Gi|Te|Fa|Po)[0-9]+(?:/[0-9]+)*', p['interface']),
            'unsupported EVC parent interface')
    for k, low, high in [('service_instance_id', 1, 4000), ('bridge_domain', 1, 4094), ('split_horizon_group', 0, 15)]:
        if k in p:
            require(type(p[k]) is int and low <= p[k] <= high, "invalid " + k)
    if t.family == 'ME3600X':
        t.vlan(p['bridge_domain'])
    require(type(p['encapsulation']) is str and p['encapsulation'] in {'Untagged', 'Dot1q', 'QinQ'}, "invalid encapsulation")
    enc = p['encapsulation']
    require(('outer_vlan' in p) == (enc != 'Untagged'), "outer tag mismatch")
    require(('inner_vlan' in p) == (enc == 'QinQ'), "inner tag mismatch")
    for k in ('outer_vlan', 'inner_vlan'):
        if k in p:
            p[k] = '1-4094' if k == 'inner_vlan' and p[k] == 'any' else vlan_expression(p[k])
    rewrite = p.get('rewrite', 'None')
    require(type(rewrite) is str and rewrite in {'None', 'Pop 1 symmetric', 'Pop 2 symmetric', 'Push dot1q', 'Push dot1q symmetric'}, "invalid rewrite")
    require(('push_vlan' in p) == rewrite.startswith('Push'), "push VLAN mismatch")
    if 'push_vlan' in p:
        require(type(p['push_vlan']) is int and 1 <= p['push_vlan'] <= 4094, "invalid push VLAN")
    from orbitflow.vendors.vlan_types import parse_vlan_list
    outer_single = enc != 'Untagged' and len(parse_vlan_list(p['outer_vlan'])) == 1
    inner_single = enc == 'QinQ' and len(parse_vlan_list(p['inner_vlan'])) == 1
    allowed = ({'None', 'Push dot1q', 'Push dot1q symmetric'} if enc == 'Untagged' else
               {'Pop 1 symmetric', 'Push dot1q', 'Push dot1q symmetric'} if enc == 'Dot1q' and outer_single else
               {'None', 'Push dot1q', 'Push dot1q symmetric'} if enc == 'Dot1q' else
               {'Pop 1 symmetric', 'Pop 2 symmetric', 'Push dot1q symmetric'} if inner_single else
               {'None', 'Pop 1 symmetric', 'Push dot1q symmetric'})
    require(rewrite in allowed, "UNSUPPORTED_OR_UNTESTED_REWRITE_COMBINATION")
    return p
