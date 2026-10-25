"""Fresh EVC execution safety and configured-intent checks; never render apply CLI."""
from orbitflow.vendors.configuration_facts import interface_settings
from orbitflow.vendors.cisco.evc import ingress, overlaps, service_signature, service_settings, source_child_commands, desired_service
from orbitflow.vendors.aggregation import for_observation, relationship_uncertain
from orbitflow.vendors.interface_names import canonical_interface_name


def supported_context(context):
    return (context.device_family, context.platform, context.capability_profile) in {
        ('ME3600X', 'cisco_ios', 'me3600x_evc'),
        ('ASR920', 'cisco_xe', 'asr920_evc'),
    }


def signature(node):
    """Stable normalized evidence, excluding capture locations and formatting."""
    return (node['kind'], node['value'], [signature(c) for c in node.get('children', [])])


def children(observed, platform, target):
    nodes = interface_settings(observed['facts'], platform, target)
    return nodes[0]['children'] if len(nodes) == 1 else None


def vlan_prerequisite(observed, vid):
    """Require consistent database and lookup presence; preserve unknown lookup."""
    status = observed.get('vlan_lookups', {}).get(str(vid), {}).get('status')
    declared = any(o['object_type'] == 'vlan' and str(o['object_id']) == str(vid)
                   for o in observed.get('objects', []))
    if not declared or status == 'absent':
        return False
    return True if status == 'present' else None


def detail_conflict(detail, services):
    if detail.get('status') == 'absent':
        return bool(services)
    if detail.get('status') == 'present':
        if len(services) != 1:
            return True
        actual = service_settings(dict(children=detail['facts']))
        expected = service_settings(services[0])
        return (actual['ingress'] != expected['ingress'] or actual['rewrites'] != expected['rewrites']
                or actual['domains'] != expected['domains']
                or bool(actual['groups']) and actual['groups'] != expected['groups'])
    return False  # Complete reliable configuration is the documented fallback.


def target_blocker(entry, observed, context):
    p, result = entry['request']['inputs'], entry['result']
    target = result.get('resolved_target') or p['interface']
    key = lambda name: canonical_interface_name(context.platform, name, normalize_aggregation=True)
    if not supported_context(context) or key(target) != key(p['interface']):
        return 'TARGET_DRIFT'
    nodes = children(observed, context.platform, target)
    if nodes is None or observed.get('configuration_reliable') is not True:
        return 'SERVICE_STATE_UNKNOWN'
    aggregation = for_observation(observed, context.platform)
    if aggregation.owner(target):
        return 'NOT_ALLOW_ON_CHILD_PORT_CHANNEL'
    if relationship_uncertain(aggregation, target, nodes) or aggregation.capture_incomplete:
        return 'OWNERSHIP_REQUIRES_REVIEW'
    if any(finding['code'] == 'PORT_CHANNEL_CONFIG_CONFLICT'
           for row in observed.get('audit', [])
           if key(row['config_interface_name']) == key(target) or key(row.get('configuration_owner', '')) == key(target)
           for finding in row.get('configuration_findings', [])):
        return 'PORT_CHANNEL_CONFIG_CONFLICT'
    vals = lambda kind: [n['value'] for n in nodes if n['kind'] == kind]
    services = [n for n in nodes if n['kind'] == 'service_instance']
    routed = any(n.get('excerpt', '').strip().startswith(('ip address ', 'ipv6 address ', 'ip unnumbered ', 'no switchport')) for n in nodes if n['kind'] != 'service_instance')
    empty = not services and not any(vals(k) for k in ('routed', 'access', 'allowed', 'native', 'mode', 'methodology_unknown')) and not routed
    if routed or vals('methodology_unknown'):
        return 'INCOMPATIBLE_EVC_PARENT'
    if context.device_family == 'ME3600X':
        compatible = vals('mode') == ['trunk'] and vals('allowed') == ['NONE']
        if (not compatible and not empty) or any(vals(k) for k in ('access', 'native', 'allowed_add', 'allowed_remove', 'allowed_except')):
            return 'INCOMPATIBLE_EVC_PARENT'
        # An empty parent can only be initialized by commands actually approved.
        if empty and not {'switchport mode trunk', 'switchport trunk allowed vlan none'} <= set(result['commands']):
            return 'EVC_PARENT_DRIFT'
        if vlan_prerequisite(observed, p['bridge_domain']) is not True:
            return 'VLAN_PREREQUISITE_UNAVAILABLE'
    else:
        if any(vals(k) for k in ('mode', 'access', 'allowed', 'native', 'allowed_add', 'allowed_remove', 'allowed_except')):
            return 'INCOMPATIBLE_EVC_PARENT'
        if any(m.get('global_bridge_domain') for a in observed.get('audit', []) if key(a['config_interface_name']) == key(target) for m in a.get('numeric_mappings', [])):
            return 'ASR920_GLOBAL_BINDING_CONFLICT'
    targets = [s for s in services if s['value'] == str(p['service_instance_id'])]
    if len(targets) > 1:
        return 'AMBIGUOUS_SERVICE_INSTANCE'
    for service in services:
        match = service_signature(service)
        if match is None:
            return 'SERVICE_STATE_UNKNOWN'
        if service not in targets and overlaps(ingress(p), match):
            return 'INGRESS_TAG_OVERLAP'
    # Destructive replacement must not discard newly introduced child settings.
    if (source_child_commands(targets[0]) if targets else []) != result['service_instance_changes']['before']:
        return 'SERVICE_INSTANCE_DRIFT'
    detail = observed.get('service_details', {}).get(target + ':' + str(p['service_instance_id']), {})
    return 'SERVICE_OBSERVATION_CONFLICT' if detail_conflict(detail, targets) else ''


def verify(entry, before, after, context):
    p = entry['request']['inputs']
    target = entry['result'].get('resolved_target') or p['interface']
    key = lambda name: canonical_interface_name(context.platform, name, normalize_aggregation=True)
    if any(sum(key(i['port_name']) == key(target) for i in obs['interfaces']) != 1 for obs in (before, after)):
        return dict(status='Unknown', error_category='InterfaceEvidenceUnavailable')
    old, new = (children(obs, context.platform, target) for obs in (before, after))
    if old is None or new is None or after.get('configuration_reliable') is not True:
        return dict(status='Unknown', error_category='ConfigurationEvidenceUnavailable')
    sid = str(p['service_instance_id'])
    actual = [n for n in new if n['kind'] == 'service_instance' and n['value'] == sid]
    wanted = desired_service(p)
    checks = dict(service=len(actual) == 1 and signature(actual[0]) == signature(wanted))
    def preserved(nodes):
        return [signature(n) for n in nodes if not (n['kind'] == 'service_instance' and n['value'] == sid)
                and n['kind'] not in ({'description'} if p.get('interface_description') else set())
                and not (context.device_family == 'ME3600X' and n['kind'] in {'mode', 'allowed'})]
    checks['preservation'] = preserved(old) == preserved(new)
    if p.get('interface_description'):
        checks['parent_description'] = [n['value'] for n in new if n['kind'] == 'description'] == [p['interface_description']]
    if context.device_family == 'ME3600X':
        checks['parent_mode'] = [n['value'] for n in new if n['kind'] == 'mode'] == ['trunk']
        checks['parent_allowed'] = [n['value'] for n in new if n['kind'] == 'allowed'] == ['NONE']
        checks['vlan_prerequisite'] = vlan_prerequisite(after, p['bridge_domain'])
    detail = after.get('service_details', {}).get(target + ':' + sid, {})
    checks['operational_consistency'] = not detail_conflict(detail, actual)
    warnings = ['SERVICE_DETAIL_FALLBACK'] if detail.get('status') not in {'present', 'absent'} else []
    if detail.get('operational_status') == 'down':
        warnings.append('SERVICE_INSTANCE_DOWN')
    from orbitflow.configuration.v2.evidence import scoped_evidence
    status = 'Failed' if False in checks.values() else 'Unknown' if None in checks.values() else 'Verified'
    return dict(status=status, evidence=dict(
        checks=checks, configuration=scoped_evidence(entry['request'], after), service_detail=detail, warnings=warnings))
