"""Fresh EVC pre-write safety and operational-presence verification; never render apply CLI."""
from orbitflow.vendors.configuration_facts import interface_settings
from orbitflow.vendors.cisco.evc import ingress, overlaps, service_signature, service_settings, source_child_commands
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
    """Verify fresh operational presence only, retaining scoped configuration evidence.

    This does not establish complete configured intent or forwarding health.
    Pre-write safety remains the responsibility of target_blocker.
    """
    from orbitflow.configuration.v2.evidence import scoped_evidence
    p = entry['request']['inputs']
    target = entry['result'].get('resolved_target') or p['interface']
    detail = after.get('service_details', {}).get(target + ':' + str(p['service_instance_id']), {})
    key = lambda name: canonical_interface_name(context.platform, name, normalize_aggregation=True)
    identified = (type(detail.get('service_instance_id')) is int and
                  isinstance(detail.get('interface'), str) and bool(detail['interface']))
    matches = identified and detail['service_instance_id'] == p['service_instance_id'] and key(detail['interface']) == key(target)
    status = 'Unknown'
    if detail.get('status') not in {'error', 'timeout'}:
        if detail.get('identity_status') == 'contradictory' or identified and not matches:
            status = 'Failed'
        elif detail.get('status') == 'absent':
            # The shared parser emits absent only for an explicit exact-target negative.
            status = 'Failed'
        elif detail.get('status') == 'present' and matches:
            status = 'Verified'
    warnings = ['SERVICE_INSTANCE_DOWN'] if detail.get('operational_status') == 'down' else []
    return dict(status=status, evidence=dict(
        verification_scope='Presence verified' if status == 'Verified' else 'Operational presence',
        configuration=scoped_evidence(entry['request'], after), service_detail=detail, warnings=warnings))
