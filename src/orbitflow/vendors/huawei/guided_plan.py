"""NE05E explicit subinterface candidate; no VSI, save or execution."""


def render(template, interface, p):
    commands = ["system-view", "interface " + interface]
    if "description" in p:
        commands.append("description " + p["description"])
    return commands + [f"vlan-type dot1q {p['vlan']}", "quit", "return"]
