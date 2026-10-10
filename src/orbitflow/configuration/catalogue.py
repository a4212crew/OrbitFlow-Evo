"""Versioned, bounded offline templates. No observed methodology grants authority."""

from dataclasses import dataclass
import re

from .plans import require, safe_text

VERSION = "1"


@dataclass(frozen=True)
class Parameter:
    name: str
    kind: str
    required: bool = True
    default: str = ""
    example: str = "3500"


@dataclass(frozen=True)
class Template:
    template_id: str
    action: str
    profiles: tuple
    capability: str
    parameters: tuple[Parameter, ...]
    method: str
    version: str = "1"


SWITCHES = (("cisco_ios", "C3750X", "c3750x_switching"),
            ("cisco_xe", "C3850", "c3850_switching"))
EVC = (("cisco_ios", "ME3600X", "me3600x_evc"), ("cisco_xe", "ASR920", "asr920_evc"))
DESCRIPTION = Parameter("description", "description", False, "", "Customer uplink")
CATALOGUE = (
    Template("cisco.access", "access port", SWITCHES, "classic_switchport",
             (Parameter("vlan", "vlan"), DESCRIPTION), "M01"),
    Template("cisco.trunk.add", "trunk VLAN add", SWITCHES, "classic_switchport",
             (Parameter("vlans", "vlans", example="3500,3501"),), "M01"),
    Template("cisco.trunk.replace", "trunk VLAN replace", SWITCHES, "classic_switchport",
             (Parameter("vlans", "vlans", example="3500,3501"),), "M01"),
    *(Template("cisco.evc." + binding, "EVC", EVC, "evc",
               (Parameter("service_instance", "id"), Parameter("outer_vlan", "vlan"),
                Parameter("bridge_domain", "id"),
                Parameter("inner_vlan", "vlan", False), DESCRIPTION), method)
      for binding, method in (("local", "M03"), ("global", "M02"))),
    Template("huawei.dot1q", "tagged subinterface",
             (("huawei_vrp", "NE05E", "ne05e"),), "dot1q_subinterface",
             (Parameter("vlan", "vlan"), DESCRIPTION), "M08"),
)


def candidates(ident, flags, action):
    profile = tuple(ident[k] for k in ("platform", "device_family", "capability_profile"))
    return tuple(t for t in CATALOGUE if t.action == action and profile in t.profiles and t.capability in flags)


def select(ident, flags, action, template_id, version):
    matches = [t for t in candidates(ident, flags, action)
               if t.template_id == template_id and t.version == version]
    require(len(matches) == 1, "compatible template selection required")
    return matches[0]


def number(value, maximum=4094):
    require(type(value) in (str, int) and re.fullmatch(r"[0-9]+", str(value)) is not None,
            "integer parameter required")
    result = int(value)
    require(1 <= result <= maximum, "parameter out of range")
    return result


def vlan(value):
    result = number(value)
    require(result >= 2 and result not in range(1002, 1006), "invalid or reserved VLAN")
    return result


def parameters(template, supplied):
    require(type(supplied) is dict and set(supplied) <= {p.name for p in template.parameters},
            "unknown template parameter")
    result = {}
    for p in template.parameters:
        value = supplied.get(p.name, p.default)
        if value == "":
            require(not p.required, "required parameter missing")
            continue
        if p.kind == "vlan":
            value = vlan(value)
        elif p.kind == "id":
            value = number(value)
        elif p.kind == "vlans":
            if type(value) is str:
                value = [vlan(v.strip()) for v in value.split(",")]
            require(type(value) is list and 0 < len(value) <= 256, "invalid VLAN list")
            value = sorted(set(vlan(v) for v in value))
        else:
            safe_text(value)
            require(re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9 _./:-]{0,79}", value) is not None,
                    "invalid description")
        result[p.name] = value
    return result


def interface_name(value, platform):
    safe_text(value)
    # Require a full, canonical name to avoid alias collisions (Gi versus GigabitEthernet).
    pattern = (r"(?:GigabitEthernet|TenGigabitEthernet|FastEthernet|Port-channel)[0-9]+(?:/[0-9]+)*(?:\.[0-9]+)?"
               if platform.startswith("cisco_") else r"(?:GigabitEthernet|Ethernet|Eth-Trunk)[0-9]+(?:/[0-9]+)*(?:\.[0-9]+)?")
    require(re.fullmatch(pattern, value) is not None, "full canonical interface name required")
    require(all(str(int(n)) == n for n in re.findall(r"[0-9]+", value)), "noncanonical interface numbering")


def render(template, interface, values):
    if template.template_id.startswith("cisco."):
        from orbitflow.vendors.cisco.guided_plan import render
    else:
        from orbitflow.vendors.huawei.guided_plan import render
    return render(template.template_id, interface, values)
