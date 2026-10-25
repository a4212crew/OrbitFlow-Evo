"""Approved Catalyst planning over shared typed facts and audited ownership."""
from orbitflow.vendors.interface_names import canonical_interface_name
from orbitflow.vendors.cisco.bulk_plan import render
from orbitflow.compliance.resolvers import reconstruct_allowed
from orbitflow.vendors.aggregation import for_observation, relationship_uncertain


def evaluate(t, p, obs, out, prior):
    findings = out['findings']
    warnings = set()
    def warn(code):
        findings.append(code)
        warnings.add(code)
    def block(code):
        findings.append(code)
    key = lambda n: canonical_interface_name(obs.get('identity', {}).get('platform', ''), n, normalize_aggregation=True)
    database = {int(o['object_id']): o.get('name', '') for o in obs.get('objects', [])
                if o['object_type'] == 'vlan' and str(o['object_id']).isdigit()}
    def lookup(vid):
        value = obs.get('vlan_lookups', {}).get(str(vid), {})
        status = value.get('status')
        if status == 'present':
            if value.get('operational_status') != 'active':
                warn('VLAN_INACTIVE')
            return True, value['name']
        if status == 'absent':
            return False, ''
        if obs.get('status') == 'live_read_only' and obs.get('configuration_reliable', bool(obs.get('evidence'))) is True:
            warn('VLAN_LOOKUP_FALLBACK')
            return vid in database, database.get(vid, '')
        block('VLAN_STATE_UNKNOWN')
        return None, ''
    if t.function == 'VLAN Database':
        exists, name = lookup(p['vlan_id'])
        out['no_op'] = exists is True and name == p['name']
        if exists and not out['no_op']:
            warn('VLAN_RENAME_IMPACT')
        out['commands'] = [] if out['no_op'] else render(t, p)
    else:
        target = p['interface']
        nodes = [n for n in obs.get('facts', []) if n['kind'] in {'interface', 'l2_interface'} and key(n['value']) == key(target)]
        if len(nodes) != 1:
            block('INTERFACE_ABSENT_OR_AMBIGUOUS')
        node = nodes[0] if len(nodes) == 1 else {'children': []}
        def last(kind, default=None):
            items = [n['value'] for n in node['children'] if n['kind'] == kind]
            return items[-1] if items else default
        aggregation = for_observation(obs, obs.get('identity', {}).get('platform', ''))
        member = aggregation.owner(target)
        uncertain = relationship_uncertain(aggregation, target, node['children']) or (
            obs.get('aggregation') is not None and aggregation.capture_incomplete)
        if t.function != 'Interface Description' and uncertain:
            block('PORT_CHANNEL_OWNER_UNRESOLVED')
        if member and t.function != 'Interface Description':
            block('NOT_ALLOW_ON_CHILD_PORT_CHANNEL')
            if any(d['code'] == 'PORT_CHANNEL_CONFIG_CONFLICT'
                   for a in obs.get('audit', []) if key(a['config_interface_name']) == key(target)
                   for d in a.get('configuration_findings', [])):
                block('PORT_CHANNEL_CONFIG_CONFLICT')
        out['resolved_target'] = target
        desc = last('description', '')
        mode = 'routed' if last('routed') else last('mode', 'unconfigured')
        access = last('access')
        operations = [(n['kind'], n['value']) for n in node['children'] if n['kind'].startswith('allowed') or n['kind'] == 'unsupported_allowed']
        unknown = any(n['kind'] == 'methodology_unknown' for n in node['children'])
        native = last('native', [1])
        projected = None
        for q, result in prior:
            if (key(result.get('resolved_target', '')) == key(target)
                    and result.get('projected_state') and not result.get('blockers')
                    and result['decision'] != 'Reject'):
                projected = result['projected_state']
        if projected:
            desc, mode, access, native = (projected[k] for k in ('description', 'mode', 'access', 'native'))
        if t.function == 'Interface Description':
            out['no_op'] = desc == p['description']
            defects = [d for a in obs.get('audit', []) if key(a['config_interface_name']) == key(target) for d in a.get('configuration_findings', [])]
            if defects or unknown:
                warn('EXISTING_VLAN_WARNING')
        elif t.function == 'Access Port':
            exists, _ = lookup(p['vlan_id'])
            if exists is False:
                warn('GLOBAL_VLAN_REQUIRED')
                for q, result in prior:
                    if q['inputs'].get('vlan_id') == p['vlan_id'] and 'name' in q['inputs']:
                        out['dependencies'].append(q['row_id'])
                        if not result['deployment_ready']:
                            warn('DEPENDENCY_NOT_APPROVED')
            if mode in {'trunk', 'routed'}:
                block('ACCESS_CONVERSION_BLOCKED')
            if mode not in {'access', 'trunk', 'routed'}:
                warn('UNSPECIFIED_OR_DYNAMIC_ACCESS_MODE')
            if mode == 'access' and operations:
                warn('RESIDUAL_TRUNK_CONFIGURATION')
            if unknown:
                block('UNRESOLVED_CONFIGURATION')
            out['no_op'] = mode == 'access' and access == [p['vlan_id']] and (not p.get('description') or desc == p['description'])
        else:
            same = False
            try:
                state = reconstruct_allowed(operations)
            except ValueError:
                state = dict(all=False, values=[], explicit=False)
                block('UNSUPPORTED_ALLOWED_VLAN_OPERATION')
            # Use the audit projection when available, retaining symbolic ALL.
            audit = [a for a in obs.get('audit', []) if key(a['config_interface_name']) == key(target)]
            if len(audit) == 1 and 'planning_allowed' in audit[0]:
                state = audit[0]['planning_allowed']
            out['observed_allowed_state'] = state
            if projected and projected.get('allowed') is not None:
                state = projected['allowed']
            if mode == 'access' or (mode == 'unconfigured' and access) or mode == 'routed':
                block('TRUNK_CONVERSION_BLOCKED')
            if unknown:
                block('UNRESOLVED_CONFIGURATION')
            if p['action'] == 'Add' and not state['explicit']:
                block('ADD_REQUIRES_EXPLICIT_BASELINE')
                out['prerequisite_details'] = 'Add requires an explicit allowed-list baseline; use Replace. Matching membership/No-op does not waive this blocker.'
            wanted, values = set(p['vlans']), set(state['values'])
            present = wanted - values if state['all'] else wanted & values
            same = (present == wanted if p['action'] == 'Add' else not present if p['action'] == 'Remove' else not state['all'] and wanted == values)
            out['no_op'] = bool(mode == 'trunk' and same and ('native_vlan' not in p or native == [p['native_vlan']]) and (not p.get('description') or desc == p['description']))
            if p['action'] in {'Replace', 'Remove'} and not out['no_op']:
                warn('SERVICE_IMPACT_REVIEW')
            if 'native_vlan' in p and (native != [p['native_vlan']] or (p['action'] == 'Remove' and p['native_vlan'] in wanted)):
                warn('NATIVE_VLAN_IMPACT')
            elif p['action'] == 'Remove' and native[0] in wanted:
                warn('NATIVE_VLAN_IMPACT')
            out['allowed_state'] = state
            operation = 'allowed' if p['action'] == 'Replace' else 'allowed_' + p['action'].lower()
            base = [('allowed_except', state['values'])] if state['all'] else [('allowed', state['values'])]
            out['desired_allowed_state'] = reconstruct_allowed(base + [(operation, p['vlans'])])
        params = dict(p, interface=target)
        existing = dict(mode=mode, description=desc)
        if t.function == 'Trunk Port' and mode == 'trunk':
            # Optional fields only emit when they differ on existing trunks.
            if p.get('description') == desc:
                params.pop('description', None)
            if 'native_vlan' in p and native == [p['native_vlan']]:
                params.pop('native_vlan')
        out['commands'] = [] if out['no_op'] else render(t, params, existing)
        if t.function == 'Trunk Port' and mode == 'trunk' and same:
            out['commands'] = [c for c in out['commands'] if not c.startswith('switchport trunk allowed vlan ')]
        out['projected_state'] = dict(description=p.get('description') or desc,
            mode='access' if t.function == 'Access Port' else 'trunk' if t.function == 'Trunk Port' else mode,
            access=[p['vlan_id']] if t.function == 'Access Port' else access,
            native=[p['native_vlan']] if 'native_vlan' in p else native,
            allowed=out.get('desired_allowed_state', projected.get('allowed') if projected else None))
    out['findings'] = sorted(set(findings))
    out['warnings'] = sorted(warnings)
    out['blockers'] = sorted(set(findings) - warnings)
    out.update(consistency='unresolved' if out['blockers'] else 'consistent',
               impact='none' if out['no_op'] else 'review_required',
               deployment_ready=not out['blockers'] and out['decision'] == 'Approve')
    return out
