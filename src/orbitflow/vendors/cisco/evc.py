"""Typed Cisco ingress matching shared by deterministic EVC planning."""
from dataclasses import asdict

from orbitflow.vendors.vlan_types import parse_vlan_list
from orbitflow.vendors.configuration_facts import observe_configuration


def ingress(p):
    return ('untagged', (), ()) if p['encapsulation'] == 'Untagged' else (
        'tagged', tuple(parse_vlan_list(p['outer_vlan'])), tuple(parse_vlan_list(p.get('inner_vlan', ''))))


def service_signature(service):
    children = service['children']
    def values(kind):
        return [n['value'] for n in children if n['kind'] == kind]
    if values('untagged') == ['untagged'] and not values('encapsulation') and not values('inner_vlan'):
        return ('untagged', (), ())
    outer, inner = values('encapsulation'), values('inner_vlan')
    if len(outer) != 1 or len(inner) > 1 or values('untagged') or any(n['kind'] == 'methodology_unknown' for n in children):
        return None
    return ('tagged', tuple(outer[0]), tuple(inner[0]) if inner else ())


def service_settings(service):
    """Comparable operational/config semantics without source formatting."""
    children = service['children']
    domains = [n['value'] for n in children if n['kind'] == 'bridge_domain']
    rewrites = []
    for n in children:
        if n['kind'] == 'tag_rewrite':
            r = n['value']
            rewrites.append((r['operation'], r['tag_count'], r['symmetric'], tuple(tuple(tag) for tag in r['output_tags'])))
    groups = [c['value'] for n in children for c in n.get('children', []) if c['kind'] == 'methodology_split_horizon_group']
    return dict(ingress=service_signature(service), domains=domains, rewrites=rewrites, groups=groups)


def overlaps(left, right):
    if left[0] != right[0]:
        return False
    if left[0] == 'untagged':
        return True
    # QinQ pairs with distinct inner tags are disjoint. Single-tag and QinQ
    # overlap cannot be assumed safe without an approved coexistence rule.
    return bool(set(left[1]) & set(right[1]) and
                (not left[2] or not right[2] or set(left[2]) & set(right[2])))


def child_commands(p):
    lines = []
    if p.get('description'):
        lines.append('description ' + p['description'])
    lines.append('encapsulation untagged' if p['encapsulation'] == 'Untagged' else
                 'encapsulation dot1q ' + p['outer_vlan'] + (' second-dot1q ' + p['inner_vlan'] if 'inner_vlan' in p else ''))
    rewrite = p.get('rewrite', 'None')
    if rewrite.startswith('Push'):
        lines.append(f"rewrite ingress tag push dot1q {p['push_vlan']}" + (' symmetric' if rewrite.endswith('symmetric') else ''))
    elif rewrite.startswith('Pop'):
        lines.append(f"rewrite ingress tag pop {rewrite.split()[1]} symmetric")
    lines.append(f"bridge-domain {p['bridge_domain']}" + (f" split-horizon group {p['split_horizon_group']}" if 'split_horizon_group' in p else ''))
    return lines


def desired_service(p):
    from orbitflow.configuration.plans import canonical, decode
    text = 'interface ' + p['interface'] + '\n service instance ' + str(p['service_instance_id']) + ' ethernet\n'
    text += '\n'.join('  ' + line for line in child_commands(p))
    return decode(canonical(asdict(observe_configuration(text, 'cisco_ios')[0].children[0])))


def source_child_commands(service):
    """One command per source line; multi-fact lines are not extra settings."""
    sources = {}
    def visit(nodes):
        for node in nodes:
            if node['value'] != 'stanza_end':
                sources[(node['source_filename'], node['line'])] = node['excerpt'].strip()
            visit(node.get('children', []))
    visit(service['children'])
    return list(dict.fromkeys(sources.values()))


def omitted_child_commands(service, p):
    """Report dropped settings, excluding schema-owned intentional replacements."""
    desired = set(child_commands(p))
    replaced = {'encapsulation', 'inner_vlan', 'untagged', 'bridge_domain', 'methodology_split_horizon_group'}
    if p.get('description'):
        replaced.add('description')
    if p.get('rewrite', 'None') != 'None':
        replaced.add('tag_rewrite')
    represented = {n['excerpt'].strip() for n in service['children'] if n['kind'] in replaced}
    unknown = {n['excerpt'].strip() for n in service['children'] if n['kind'] not in replaced}
    omitted = []
    for line in source_child_commands(service):
        # Removing an optional split-horizon setting still deserves review.
        dropped_group = (line.startswith('bridge-domain ') and ' split-horizon group ' in line
                         and 'split_horizon_group' not in p)
        if line not in desired and (dropped_group or line not in represented or line in unknown):
            omitted.append(line)
    return omitted
