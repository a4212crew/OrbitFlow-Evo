"""Approved Templates 9–16 over preserved shared vendor facts.

This layer compares typed observations only. CLI grammar and rendering belong
to vendor modules; projected state follows the existing per-device row order.
"""
from copy import deepcopy
from .catalogue import BY_ID

from orbitflow.vendors.interface_names import canonical_interface_name
from orbitflow.vendors.vlan_types import parse_vlan_list
from orbitflow.vendors.cisco.bulk_plan import render as cisco
from orbitflow.vendors.ubiquiti.bulk_plan import render as edge
from orbitflow.vendors.cisco.evc import ingress, overlaps, service_signature, service_settings, child_commands, source_child_commands
from orbitflow.configuration.plans import canonical


def evaluate(t, p, obs, out, prior):
    warnings = set()
    findings = out['findings']
    def warn(code):
        findings.append(code)
        warnings.add(code)
    def block(code):
        findings.append(code)
    key = lambda n: canonical_interface_name(obs.get('identity', {}).get('platform', ''), n)
    reliable = obs.get('configuration_reliable') is True and obs.get('status') == 'live_read_only'
    if not reliable:
        block('CONFIGURATION_EVIDENCE_UNAVAILABLE')
    database = {int(o['object_id']): o.get('name', '') for o in obs.get('objects', [])
                if o['object_type'] == 'vlan' and str(o['object_id']).isdigit()}
    observed_database = set(database)
    for q, result in prior:
        if q['inputs'].get('vlan_id') and result.get('projected_state', {}).get('vlan_name') is not None and not result.get('blockers') and result['decision'] != 'Reject':
            database[q['inputs']['vlan_id']] = result['projected_state']['vlan_name']

    def lookup(vid):
        value = obs.get('vlan_lookups', {}).get(str(vid), {})
        status = value.get('status')
        if status in {'present', 'absent'}:
            exists = status == 'present'
            if reliable and (exists != (vid in database) or exists and database[vid] != value['name']):
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
        nodes = [n for n in obs.get('facts', []) if n['kind'] in {'interface', 'l2_interface'} and key(n['value']) == key(target)]
        if len(nodes) != 1:
            block('INTERFACE_ABSENT_OR_AMBIGUOUS')
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
                independent_description = (t.family == 'EdgeSwitch' and
                    {t.function, BY_ID[q['template_id']].function} ==
                    {'VLAN Port', 'Interface Description'})
                if not independent_description:
                    out['dependencies'].append(q['row_id'])
                if not independent_description and not result['deployment_ready']:
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
            if vals('aggregate') or any(key(a.get('configuration_owner', '')) != key(target) for a in obs.get('audit', []) if key(a['config_interface_name']) == key(target)):
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
                if projected and 'services' in projected:
                    services = projected['services']
                mode = vals('mode')
                empty = not services and not any(n['kind'] in {'routed', 'access', 'allowed', 'native', 'mode', 'methodology_unknown'} for n in node['children'])
                # Evidence-only unrelated parent settings are preserved. Layer-3
                # addresses and policies require explicit conversion review.
                parent_lines = [n.get('excerpt', '').strip() for n in node['children'] if n['kind'] != 'service_instance']
                routed = any(s.startswith(('ip address ', 'ipv6 address ', 'ip unnumbered ', 'no switchport')) for s in parent_lines)
                empty &= not routed
                if t.family == 'ME3600X':
                    compatible = mode == ['trunk'] and vals('allowed') == ['NONE'] or bool(projected and projected.get('evc_parent'))
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
                if targets:
                    warn('SERVICE_INSTANCE_RECREATE_IMPACT')
                    desired = set(child_commands(p))
                    before = source_child_commands(targets[0])
                    out['omitted_child_commands'] = [line for line in before if line not in desired]
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
                if detail.get('status') == 'present' and targets:
                    operational = service_settings(dict(children=detail['facts']))
                    configured = service_settings(targets[0])
                    if any(operational[k] != configured[k] for k in ('ingress', 'domains', 'rewrites')) or operational['groups'] and operational['groups'] != configured['groups']:
                        block('SERVICE_OBSERVATION_CONFLICT')
                if detail.get('status') not in {'present', 'absent'}:
                    if reliable:
                        warn('SERVICE_DETAIL_FALLBACK')
                    else:
                        block('SERVICE_STATE_UNKNOWN')
                if t.family == 'ME3600X':
                    exists, _ = lookup(p['bridge_domain'])
                    if exists is False or p['bridge_domain'] not in observed_database:
                        candidates = [(q, result) for q, result in prior if q['inputs'].get('vlan_id') == p['bridge_domain'] and result.get('projected_state', {}).get('vlan_name') is not None]
                        if candidates:
                            q, result = candidates[-1]
                            out['dependencies'].append(q['row_id'])
                            if not result['deployment_ready']:
                                block('DEPENDENCY_NOT_APPROVED')
                        else:
                            warn('GLOBAL_VLAN_REQUIRED')
                        out['missing_global_vlans'] = [p['bridge_domain']]
                for a in obs.get('audit', []):
                    if key(a['config_interface_name']) == key(target) and any(m.get('global_bridge_domain') for m in a.get('numeric_mappings', [])) and t.family == 'ASR920':
                        block('ASR920_GLOBAL_BINDING_CONFLICT')
                warn('SERVICE_IMPACT_REVIEW')
                out['commands'] = renderer(t, p, dict(initialize=empty, description=description))
                # Store normalized desired children through the shared vendor helper.
                from orbitflow.vendors.cisco.evc import desired_service
                out['projected_state'] = dict(description=p.get('interface_description', description),
                    evc_parent=True, services=[s for s in services if s['value'] != str(p['service_instance_id'])] + [desired_service(p)])
    out['findings'] = sorted(set(findings))
    out['warnings'] = sorted(warnings)
    out['blockers'] = sorted(set(findings) - warnings)
    out.update(consistency='unresolved' if out['blockers'] else 'consistent', impact='none' if out['no_op'] else 'review_required',
               deployment_ready=not out['blockers'] and out['decision'] == 'Approve')
    return out
