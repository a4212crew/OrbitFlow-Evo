"""EdgeSwitch proposals preserve independent membership, tagging and PVID."""
from orbitflow.vendors.vlan_types import parse_vlan_list


def render(template, p, existing=None):
    existing = existing or {}
    if template.function == 'VLAN Database':
        return ['vlan database', *([] if existing.get('exists') else [f"vlan {p['vlan_id']}"]),
                f"vlan name {p['vlan_id']} \"{p['name']}\"", 'exit']
    lines = ['configure', f"interface {p['interface']}"]
    if p.get('description') and p['description'] != existing.get('description'):
        lines += [f"description \"{p['description']}\""]
    if template.function == 'VLAN Port':
        wanted = set(parse_vlan_list(p.get('tagged_vlans', '')))
        included = set(existing.get('included', []))
        excluded = set(existing.get('excluded', []))
        tagged = set(existing.get('tagged', []))
        def emit(command, ids):
            if ids:
                expression = p['tagged_vlans'] if ids == wanted else ','.join(map(str, sorted(ids)))
                lines.append(command + expression)
        if p['action'] == 'Remove':
            emit('no vlan tagging ', wanted & tagged)
            emit('vlan participation exclude ', wanted - excluded)
        else:
            emit('vlan participation include ', wanted - included)
            emit('vlan tagging ', wanted - tagged)
            included |= wanted
            if 'pvid' in p:
                if p['pvid'] not in included:
                    lines.append(f"vlan participation include {p['pvid']}")
                if p['pvid'] != existing.get('pvid'):
                    lines.append(f"vlan pvid {p['pvid']}")
    return lines + ['exit', 'exit']
