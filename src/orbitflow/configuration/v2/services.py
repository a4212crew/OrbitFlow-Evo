"""Approved Templates 9–16 over preserved shared vendor facts.

This layer compares typed observations only. CLI grammar and rendering belong
to vendor modules; projected services follow per-device row order for conflicts,
while independent EVC parent setup is derived from observed state per row.
"""
from copy import deepcopy
from orbitflow.vendors.configuration_facts import interface_settings
from orbitflow.vendors.aggregation import for_observation, relationship_uncertain
from .catalogue import BY_ID

from orbitflow.vendors.interface_names import canonical_interface_name
from orbitflow.vendors.vlan_types import parse_vlan_list
from orbitflow.vendors.cisco.bulk_plan import render as cisco
from orbitflow.vendors.ubiquiti.bulk_plan import render as edge
from orbitflow.vendors.cisco.evc import ingress, overlaps, service_signature, service_settings, child_commands, source_child_commands, omitted_child_commands
from orbitflow.configuration.plans import canonical


def evaluate(t, p, obs, out, prior):
    warnings = set()
    findings = out['findings']
    def warn(code):
        findings.append(code)
        warnings.add(code)
    def block(code):
        findings.append(code)
    key = lambda n: canonical_interface_name(obs.get('identity', {}).get('platform', ''), n, normalize_aggregation=True)
    reliable = obs.get('configuration_reliable') is True and obs.get('status') == 'live_read_only'
    if not reliable:
        block('CONFIGURATION_EVIDENCE_UNAVAILABLE')
    database = {int(o['object_id']): o.get('name', '') for o in obs.get('objects', [])
                if o['object_type'] == 'vlan' and str(o['object_id']).isdigit()}
    if t.family == 'ME3600X':
        for fact in obs.get('facts', []):
            if fact['kind'] == 'vlan':
                names = [n['value'] for n in fact['children'] if n['kind'] == 'vlan_name']
                for vid in fact['value']:
                    if vid in database:
                        database[vid] = names[-1] if names else ''
    observed_database = set(database)
    for q, result in prior:
        if q['inputs'].get('vlan_id') and result.get('projected_state', {}).get('vlan_name') is not None and not result.get('blockers') and result['decision'] != 'Reject':
            database[q['inputs']['vlan_id']] = result['projected_state']['vlan_name']

    def lookup(vid):
        value = obs.get('vlan_lookups', {}).get(str(vid), {})
        status = value.get('status')
        if status in {'present', 'absent'}:
            exists = status == 'present'
            if reliable and (exists != (vid in database) or exists and (t.family != 'ME3600X' or bool(database[vid])) and database[vid] != value['name']):
                # Prior approved planning may change this resource after observation.
                if not any(q['inputs'].get('vlan_id') == vid and result.get('projected_state') for q, result in prior):
                    block('VLAN_OBSERVATION_CONFLICT')
            if value.get('operational_status') in {'suspend', 'inactive', 'down'}:
                warn('VLAN_INACTIVE')
            return exists, value.get('name', '')
        if reliable:
            warn('VLAN_LOOKUP_FALLBACK')
            return vid in database, database.get(vid, '')
        block('VLAN_STATE_UNKNOWN')
        return None, ''

    renderer = edge if t.family == 'EdgeSwitch' else cisco
    if t.function == 'VLAN Database':
        exists, name = lookup(p['vlan_id'])
        out['no_op'] = exists is True and name == p['name']
        if exists and not out['no_op']:
            warn('VLAN_RENAME_IMPACT')
        out['commands'] = [] if out['no_op'] else renderer(t, p, dict(exists=exists))
        out['projected_state'] = dict(vlan_name=p['name'])
    else:
        target = p['interface']
        nodes = interface_settings(obs.get('facts', []), obs.get('identity', {}).get('platform', ''), target)
        if t.family == 'EdgeSwitch' and sum(key(i['port_name']) == key(target) for i in obs.get('interfaces', [])) != 1:
            block('INTERFACE_ABSENT_OR_AMBIGUOUS')
        if len(nodes) != 1:
            block('INTERFACE_CONFIGURATION_ABSENT_OR_AMBIGUOUS' if t.family == 'EdgeSwitch' else 'INTERFACE_ABSENT_OR_AMBIGUOUS')
        node = deepcopy(nodes[0]) if len(nodes) == 1 else dict(children=[])
        def vals(kind):
            return [n['value'] for n in node['children'] if n['kind'] == kind]
        description = vals('description')[-1] if vals('description') else ''
        if t.family == 'EdgeSwitch' and len(description) >= 2 and description[0] == description[-1] and description[0] in "\"'":
            description = description[1:-1]
        out['resolved_target'] = target
        projected = None
        for q, result in prior:
            if key(result.get('resolved_target', '')) == key(target) and result.get('projected_state') and not result.get('blockers') and result['decision'] != 'Reject':
                projected = result['projected_state']
                independent_description = ((t.function == 'Interface Description') !=
                    (BY_ID[q['template_id']].function == 'Interface Description'))
                independent_evc = (t.function == BY_ID[q['template_id']].function == 'EVC'
                    and p['service_instance_id'] != q['inputs']['service_instance_id']
                    and not overlaps(ingress(p), ingress(q['inputs']))
                    and (not p.get('interface_description') or not q['inputs'].get('interface_description')
                         or p['interface_description'] == q['inputs']['interface_description']))
                if not independent_description and not independent_evc:
                    out['dependencies'].append(q['row_id'])
                if not independent_description and not independent_evc and not result['deployment_ready']:
                    block('DEPENDENCY_NOT_APPROVED')
        if projected:
            description = projected.get('description', description)
        if t.function == 'Interface Description':
            out['no_op'] = description == p['description']
            for a in obs.get('audit', []):
                if key(a['config_interface_name']) == key(target) and a.get('configuration_findings'):
                    warn('EXISTING_VLAN_WARNING: ' + canonical(a['configuration_findings']))
            out['commands'] = [] if out['no_op'] else renderer(t, p)
            out['projected_state'] = {**(projected or {}), 'description': p['description']}
        else:
            aggregation = for_observation(obs, obs.get('identity', {}).get('platform', ''))
            if aggregation.owner(target):
                block('NOT_ALLOW_ON_CHILD_PORT_CHANNEL')
            elif relationship_uncertain(aggregation, target, node['children']) or (obs.get('aggregation') is not None and aggregation.capture_incomplete) or any(key(a.get('configuration_owner', '')) != key(target) for a in obs.get('audit', []) if key(a['config_interface_name']) == key(target)):
                block('OWNERSHIP_REQUIRES_REVIEW')
            if t.function == 'VLAN Port':
                included, excluded, tagged, pvid = set(), set(), set(), None
                for n in node['children']:
                    kind, value = n['kind'], n['value']
                    if kind == 'include':
                        included.update(value)
                        excluded.difference_update(value)
                    elif kind == 'exclude':
                        excluded.update(value)
                        included.difference_update(value)
                    elif kind == 'tagged':
                        tagged.update(value)
                    elif kind == 'untagged_vlans':
                        tagged.difference_update(value)
                    elif kind == 'pvid':
                        pvid = value[0]
                    elif kind == 'methodology_unknown':
                        block('MEMBERSHIP_STATE_UNKNOWN')
                if projected and 'included' in projected:
                    included, excluded, tagged, pvid = (set(projected[k]) if k != 'pvid' else projected[k] for k in ('included', 'excluded', 'tagged', 'pvid'))
                wanted = set(parse_vlan_list(p.get('tagged_vlans', '')))
                for vid in sorted(wanted | ({p['pvid']} if 'pvid' in p else set())):
                    exists, _ = lookup(vid)
                    if exists is False:
                        warn('VLAN_NOT_IN_DATABASE')
                if p['action'] == 'Remove' and pvid in wanted:
                    block('PVID_REMOVAL_REQUIRES_REVIEW')
                existing = dict(included=sorted(included), excluded=sorted(excluded), tagged=sorted(tagged), pvid=pvid, description=description)
                out['commands'] = renderer(t, p, existing)
                out['no_op'] = len(out['commands']) == 4
                if out['no_op']:
                    out['commands'] = []
                else:
                    warn('SERVICE_IMPACT_REVIEW')
                if p['action'] == 'Remove':
                    tagged -= wanted
                    included -= wanted
                    excluded |= wanted
                else:
                    tagged |= wanted
                    included |= wanted
                    excluded -= wanted
                    if 'pvid' in p:
                        pvid = p['pvid']
                        included.add(pvid)
                        excluded.discard(pvid)
                out['projected_state'] = dict(description=p.get('description', description), included=sorted(included), excluded=sorted(excluded), tagged=sorted(tagged), pvid=pvid)
            else:
                services = [n for n in node['children'] if n['kind'] == 'service_instance']
                # Project sibling services for collision detection, never to borrow
                # their approval or suppress this row's observed parent setup.
                observed_services = services
                if projected and 'services' in projected:
                    services = projected['services']
                mode = vals('mode')
                empty = not observed_services and not any(n['kind'] in {'routed', 'access', 'allowed', 'native', 'mode', 'methodology_unknown'} for n in node['children'])
                # Evidence-only unrelated parent settings are preserved. Layer-3
                # addresses and policies require explicit conversion review.
                parent_lines = [n.get('excerpt', '').strip() for n in node['children'] if n['kind'] != 'service_instance']
                routed = any(s.startswith(('ip address ', 'ipv6 address ', 'ip unnumbered ', 'no switchport')) for s in parent_lines)
                empty &= not routed
                if t.family == 'ME3600X':
                    compatible = mode == ['trunk'] and vals('allowed') == ['NONE']
                    if (not compatible and not empty) or routed or vals('access') or vals('native') or vals('allowed_add') or vals('allowed_remove') or vals('allowed_except'):
                        block('INCOMPATIBLE_EVC_PARENT')
                elif routed or mode or vals('access') or vals('allowed'):
                    block('INCOMPATIBLE_EVC_PARENT')
                if any(n['kind'] == 'methodology_unknown' for n in node['children']):
                    block('UNRESOLVED_CONFIGURATION')
                wanted_ingress = ingress(p)
                targets = [s for s in services if s['value'] == str(p['service_instance_id'])]
                if len(targets) > 1:
                    block('AMBIGUOUS_SERVICE_INSTANCE')
                for s in services:
                    signature = service_signature(s)
                    if signature is None:
                        block('SERVICE_STATE_UNKNOWN')
                    elif s['value'] != str(p['service_instance_id']) and overlaps(wanted_ingress, signature):
                        block('INGRESS_TAG_OVERLAP')
                        # Only normalized selectors and validated row metadata are
                        # persisted; never copy raw device output into diagnostics.
                        def selector(sig):
                            def ranges(values):
                                groups = []
                                for value in sorted(set(values)):
                                    if groups and value == groups[-1][-1] + 1:
                                        groups[-1].append(value)
                                    else:
                                        groups.append([value])
                                return ','.join(str(g[0]) if len(g) == 1 else f'{g[0]}-{g[-1]}' for g in groups)
                            return dict(kind=sig[0], outer_vlan=ranges(sig[1]), inner_vlan=ranges(sig[2]))
                        origin = dict(kind='existing')
                        for q, result in prior:
                            if (BY_ID[q['template_id']].function == 'EVC'
                                    and key(q['inputs']['interface']) == key(target)
                                    and str(q['inputs']['service_instance_id']) == s['value']
                                    and result.get('projected_state') and not result.get('blockers')
                                    and result['decision'] != 'Reject'):
                                origin = dict(kind='projected', row_id=q['row_id'],
                                              sheet=BY_ID[q['template_id']].sheet, row=q['row'])
                        requested = selector(wanted_ingress)
                        conflicting = selector(signature)
                        def display(value):
                            return ('untagged' if value['kind'] == 'untagged' else
                                    'dot1q ' + value['outer_vlan'] +
                                    (' second-dot1q ' + value['inner_vlan'] if value['inner_vlan'] else ''))
                        explanation = (f"{p['management_ip']} {target}: requested SI {p['service_instance_id']} "
                                       f"({display(requested)}) overlaps {origin['kind']} SI {s['value']} "
                                       f"({display(conflicting)})" +
                                       (f" from {origin['sheet']} row {origin['row']}" if origin['kind'] == 'projected' else '') +
                                       '. INGRESS_TAG_OVERLAP blocks this row.')
                        out.setdefault('ingress_conflicts', []).append(dict(
                            code='INGRESS_TAG_OVERLAP', management_ip=p['management_ip'], interface=key(target),
                            requested=dict(service_instance_id=p['service_instance_id'], selector=requested),
                            conflicting=dict(service_instance_id=int(s['value']), selector=conflicting, origin=origin),
                            explanation=explanation))
                if targets:
                    warn('SERVICE_INSTANCE_RECREATE_IMPACT')
                    before = source_child_commands(targets[0])
                    out['omitted_child_commands'] = omitted_child_commands(targets[0], p)
                    if out['omitted_child_commands']:
                        warn('OMITTED_CHILD_SETTINGS')
                else:
                    before = []
                after = child_commands(p)
                out['service_instance_changes'] = dict(before=before, after=after,
                    removed=[line for line in before if line not in after],
                    added=[line for line in after if line not in before],
                    recreation=True, existed=bool(targets))
                detail = obs.get('service_details', {}).get(target + ':' + str(p['service_instance_id']), {})
                if detail.get('operational_status') == 'down':
                    warn('SERVICE_INSTANCE_DOWN')
                if detail.get('status') == 'absent' and targets or detail.get('status') == 'present' and not targets:
                    block('SERVICE_OBSERVATION_CONFLICT')
                if detail.get('status') == 'present':
                    operational = service_settings(dict(children=detail['facts']))
                    if len(operational['domains']) != 1:
                        block('SERVICE_DETAIL_INCOMPLETE')
                    if targets:
                        configured = service_settings(targets[0])
                        if (any(operational[k] != configured[k] for k in ('ingress', 'rewrites')) or
                                operational['domains'] and operational['domains'] != configured['domains'] or
                                operational['groups'] and operational['groups'] != configured['groups']):
                            block('SERVICE_OBSERVATION_CONFLICT')
                if detail.get('status') not in {'present', 'absent'}:
                    if reliable:
                        warn('SERVICE_DETAIL_FALLBACK')
                    else:
                        block('SERVICE_STATE_UNKNOWN')
                if t.family == 'ME3600X':
                    exists, _ = lookup(p['bridge_domain'])
                    if exists is False or p['bridge_domain'] not in observed_database:
                        warn('GLOBAL_VLAN_REQUIRED')
                        out['missing_global_vlans'] = [p['bridge_domain']]
                for a in obs.get('audit', []):
                    if key(a['config_interface_name']) == key(target) and any(m.get('global_bridge_domain') for m in a.get('numeric_mappings', [])) and t.family == 'ASR920':
                        block('ASR920_GLOBAL_BINDING_CONFLICT')
                warn('SERVICE_IMPACT_REVIEW')
                out['commands'] = renderer(t, p, dict(initialize=empty, description=vals('description')[-1] if vals('description') else ''))
                # Store normalized desired children through the shared vendor helper.
                from orbitflow.vendors.cisco.evc import desired_service
                # Only ME3600X converts an empty parent into a shared trunk
                # resource. ASR920's address-free parent needs no conversion;
                # its defensive no-ip command must not serialize siblings.
                out['projected_state'] = dict(description=p.get('interface_description', description),
                    evc_parent=True, initializes_parent=t.family == 'ME3600X' and empty, services=[s for s in services if s['value'] != str(p['service_instance_id'])] + [desired_service(p)])
    out['findings'] = sorted(set(findings))
    out['warnings'] = sorted(warnings)
    out['blockers'] = sorted(set(findings) - warnings)
    out.update(consistency='unresolved' if out['blockers'] else 'consistent', impact='none' if out['no_op'] else 'review_required',
               deployment_ready=not out['blockers'] and out['decision'] == 'Approve')
    return out
