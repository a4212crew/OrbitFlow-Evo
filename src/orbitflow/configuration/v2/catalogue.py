"""Versioned, UI-independent schemas for the approved bulk planning catalogue."""
from dataclasses import dataclass
import ipaddress
import re

from orbitflow.configuration.plans import PlanError, require
from orbitflow.logging import sanitize_text

VERSION = "2.2"
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
    "EVC": ("interface service_instance encapsulation bridge_domain", "outer_vlan inner_vlan pop_tags rewrite push_vlan description"),
    "L2VPN": ("interface subinterface encapsulation bridge_group bridge_domain", "outer_vlan inner_vlan description"),
    "VLAN Port": ("interface", "action mode vlans pvid replace_untagged description"),
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
        require(type(values) is dict and set(values) <= set(self.columns), "unknown template field")
        require(all(values.get(k) not in (None, "") for k in ("management_ip", *self.required)), "required input missing")
        data = {k: v for k, v in values.items() if v not in (None, "")}
        numeric_fields = {"vlan_id", "outer_vlan", "inner_vlan", "native_vlan", "pvid", "control_vid",
                          "service_instance", "subinterface", "pop_tags", "push_vlan"}
        if self.function == "EVC":
            numeric_fields.add("bridge_domain")
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
            if self.function == "EVC":
                require(type(data["bridge_domain"]) is int and 1 <= data["bridge_domain"] <= 4094, "invalid bridge domain")
                if self.family == "ME3600X":
                    self.vlan(data["bridge_domain"])
            else:
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
        if self.function in {"EVC", "L2VPN"}:
            require(data["encapsulation"] in {"dot1q", "QinQ", "untagged"}, "invalid encapsulation")
            enc = data["encapsulation"]
            require(("outer_vlan" in data) == (enc != "untagged"), "outer tag mismatch")
            require(("inner_vlan" in data) == (enc == "QinQ"), "inner tag mismatch")
            require("pop_tags" not in data or data["pop_tags"] <= (2 if enc == "QinQ" else 1 if enc == "dot1q" else 0), "invalid rewrite")
        if "rewrite" in data:
            require(self.function == "EVC" and data["rewrite"] in {"None", "Pop1", "Pop2", "Push"}, "invalid rewrite choice")
            require("pop_tags" not in data, "conflicting rewrite fields")
            enc = data["encapsulation"]
            require(data["rewrite"] != "Pop1" or enc != "untagged", "invalid rewrite")
            require(data["rewrite"] != "Pop2" or enc == "QinQ", "invalid rewrite")
            require(data["rewrite"] != "Push" or (self.family == "ASR920" and enc == "untagged"), "unsupported push rewrite")
        require(("push_vlan" in data) == (data.get("rewrite") == "Push"), "push VLAN mismatch")
        if self.function == "Subinterface VSI":
            require(data["encapsulation"] in {"dot1q termination", "vlan-type dot1q"}, "unsupported encapsulation")
            require("control_vid" not in data or data["encapsulation"] == "dot1q termination", "unexpected control VID")
        if self.function == "VLAN Port":
            require(data.get("mode", "Tagged") in {"Access", "Tagged"}, "invalid port mode")
            require(data.get("replace_untagged", "No") in {"Yes", "No"}, "invalid untagged replacement")
            require(data.get("replace_untagged") != "Yes" or data.get("action") == "Replace", "replacement requires Replace")
            require("vlans" not in data or "action" in data, "membership action missing")
            require(bool(data.get("vlans")) or "pvid" in data, "membership or PVID required")
            if data.get("mode") == "Access":
                require(len(data.get("vlans", [])) == 1 and data.get("action") != "Remove", "invalid access request")
                require(data.get("pvid", data["vlans"][0]) == data["vlans"][0], "access PVID mismatch")
        if self.family == "All":
            require(data["platform"] in {v[0] for v in FAMILIES.values()}, "invalid platform")
            require(data["mode"] in {"configuration", "interface", "service"}, "invalid CLI mode")
        return data

    def vlan(self, value):
        require(type(value) is int and 1 <= value <= (4093 if self.family == "EdgeSwitch" else 4094), "invalid VLAN")
        if self.family in {"C3750X", "C3850X", "ME3600X"}:
            require(value not in range(1002, 1006), "reserved VLAN")


def _catalogue():
    operations = {
        "C3750X": ("VLAN Database", "Access Port", "Trunk Port", "Interface Description"),
        "C3850X": ("VLAN Database", "Access Port", "Trunk Port", "Interface Description"),
        "ME3600X": ("VLAN Database", "EVC", "Interface Description"),
        "ASR920": ("EVC", "Interface Description"),
        "NCS540": ("L2VPN", "Interface Description"),
        "EdgeSwitch": ("VLAN Database", "VLAN Port", "Interface Description"),
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
               "subinterface", "service_instance", "pop_tags", "push_vlan"}
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
