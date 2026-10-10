"""Qualified bounded candidate syntax; never sends CLI or saves configuration."""

import re


def manual_conflicts(commands, effect, same_interface):
    """Recognize definite contradictions; all other manual effects stay unknown."""
    codes = set()
    kind = effect.get("kind", "")
    requested = set(effect.get("vlans", [effect["vlan"]] if "vlan" in effect else []))
    for command in commands:
        match = re.fullmatch(r"no vlan ([0-9,]+)", command)
        if match and requested.intersection(map(int, match[1].split(","))):
            codes.add("manual_deletes_requested_vlan")
        if not same_interface:
            continue
        match = re.fullmatch(r"switchport trunk allowed vlan remove ([0-9,]+)", command)
        if match and requested.intersection(map(int, match[1].split(","))):
            codes.add("manual_removes_requested_vlan")
        if (command == "switchport mode access" and kind.startswith("cisco.trunk.")) or (
                command == "switchport mode trunk" and kind == "cisco.access"):
            codes.add("manual_mode_conflict")
        match = re.fullmatch(r"switchport access vlan ([0-9]+)", command)
        if match and kind == "cisco.access" and int(match[1]) != effect["vlan"]:
            codes.add("manual_access_vlan_conflict")
        match = re.fullmatch(r"(?:no )?service instance ([0-9]+) ethernet", command)
        if match and kind.startswith("cisco.evc.") and int(match[1]) == effect["service_instance"]:
            codes.add("manual_service_instance_collision")
        if command.startswith("description ") and "description" in effect and command != "description " + effect["description"]:
            codes.add("manual_description_conflict")
    return sorted(codes)


def render(template, interface, p):
    commands = ["configure terminal", "interface " + interface]
    if "description" in p:
        commands.append("description " + p["description"])
    if template == "cisco.access":
        commands += ["switchport", "switchport mode access", f"switchport access vlan {p['vlan']}"]
    elif template.startswith("cisco.trunk."):
        modifier = "add " if template.endswith("add") else ""
        commands += ["switchport", "switchport mode trunk",
                     "switchport trunk allowed vlan " + modifier + ",".join(map(str, p["vlans"]))]
    else:
        commands += [f"service instance {p['service_instance']} ethernet",
                     f"encapsulation dot1q {p['outer_vlan']}" +
                     (f" second-dot1q {p['inner_vlan']}" if "inner_vlan" in p else "")]
        if template.endswith("local"):
            commands += [f"bridge-domain {p['bridge_domain']}"]
        else:
            commands += ["exit", "exit", f"bridge-domain {p['bridge_domain']}",
                         f"member {interface} service-instance {p['service_instance']}"]
    return commands + ["end"]
