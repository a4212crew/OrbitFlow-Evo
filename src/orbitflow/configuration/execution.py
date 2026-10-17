"""Approved predefined execution: preparation/confirmation independent of Excel.

Workbook ingestion is an adapter. Confirmation records are local replay guards,
not authentication. No writes occur until confirm(..., apply=True).
"""
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from contextlib import contextmanager
import hashlib
import math
import os
from pathlib import Path
import re
import sqlite3
from time import monotonic
from uuid import uuid4

from orbitflow.configuration.plans import canonical, decode, identity, require
from orbitflow.configuration.v2.catalogue import BY_ID
from orbitflow.configuration.v2.planning import BulkPlan, evaluate_decisions, plan
from orbitflow.config import ExecutionConfig
from orbitflow.logging import module_logger, sanitize_text, capability_metadata
from orbitflow.result_spool import ResultSpool, ResultJournal
from orbitflow.execution import execute_devices
from orbitflow.capabilities.save import command_rejected, save_configuration
from orbitflow.capabilities.switchport import SwitchportService
from orbitflow.capabilities.interfaces import InterfaceService
from orbitflow.capabilities.vlans import VlanService
from orbitflow.capabilities.configuration import ConfigurationService
from orbitflow.configuration_backup import BackupWriter
from orbitflow.configuration.v2.observation import snapshot
from orbitflow.inventory import DeviceInventoryResolver, JsonInventoryStore
from orbitflow.transport import connect_device
from orbitflow.vendors.common import DeviceCLI
from orbitflow.vendors.configuration_facts import _safe_source
from orbitflow.vendors.interface_names import canonical_interface_name
from orbitflow.vendors.vlan_types import parse_vlan_list
from orbitflow.vendors.cisco import configuration_execution as cisco_execution
from orbitflow.vendors.ubiquiti import configuration_execution as edge_execution


def _now():
    return datetime.now(timezone.utc).isoformat()


class ExecutionBlocked(Exception):
    """A fixed execution gate code, never device text or arbitrary exception data."""
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def _gate(condition, code):
    if not condition:
        raise ExecutionBlocked(code)


@dataclass(frozen=True)
class ApplySettings:
    """Separate apply limit; all timeouts are finite seconds."""
    max_concurrent_devices: int = 1
    command_timeout: float = 30.0
    save_timeout: float = 300.0
    connection_start_interval: float = 1.0
    connection_retry_delay: float = 5.0

    def __post_init__(self):
        ExecutionConfig(self.max_concurrent_devices, self.connection_start_interval, self.connection_retry_delay)
        for value in (self.command_timeout, self.save_timeout):
            require(type(value) in (int, float) and math.isfinite(value) and value > 0, 'invalid apply timeout')


def verification_commands(request, result):
    t, p = BY_ID[request['template_id']], request['inputs']
    target = result.get('resolved_target', p.get('interface', ''))
    if t.family not in {'C3750X', 'C3850X', 'EdgeSwitch'}:
        return []
    adapter = edge_execution if t.family == 'EdgeSwitch' else cisco_execution
    return adapter.verification_commands(t.function, p, target)


class ExecutionService:
    """Local transactional confirmation store. Keep authority directory protected."""
    def __init__(self, authority_dir='data/configuration/execution'):
        self.path = Path(authority_dir)
        self.path.mkdir(parents=True, exist_ok=True)
        with self._db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS confirmations (reference TEXT PRIMARY KEY, digest TEXT UNIQUE, payload TEXT, state TEXT, run_path TEXT)')

    @contextmanager
    def _db(self):
        db = sqlite3.connect(self.path / 'confirmations.sqlite3', timeout=30)
        try:
            with db:
                yield db
        finally:
            db.close()

    def prepare(self, original, decisions, *, expected_digest, settings=ApplySettings()):
        """No connection. Return exact summary/reference; decisions is row-ID mapping."""
        original = BulkPlan(original.content)
        require(original.digest == expected_digest, 'source digest mismatch')
        settings = ApplySettings(**asdict(settings))
        data = original.to_dict()
        intent = evaluate_decisions(original, decisions, expected_digest=expected_digest,
                                    now=datetime.fromisoformat(data['evaluated_at'])).to_dict()
        selected, skipped = [], []
        results = {r['row_id']: r for r in intent['results']}
        for request in data['requests']:
            result = results[request['row_id']]
            t = BY_ID[request['template_id']]
            reason = ('UNSUPPORTED_TEMPLATE' if t.family not in {'C3750X', 'C3850X', 'EdgeSwitch'} else
                      result['decision'] if result['decision'] != 'Approve' else
                      'BLOCKED' if not result['deployment_ready'] else '')
            entry = dict(request=request, result=result,
                         identity=data['observations'].get(request['inputs']['management_ip'], {}).get('identity'),
                         verification_commands=verification_commands(request, result))
            if reason:
                skipped.append(dict(row_id=request['row_id'], decision=result['decision'], reason=reason, request=request, identity=entry['identity'], blockers=result.get('blockers', result['findings'])))
            else:
                selected.append(entry)
        # Dependency closure is evaluated against executable rows, in order.
        ready = set()
        executable = []
        for entry in selected:
            if not set(entry['result']['dependencies']) <= ready:
                skipped.append(dict(row_id=entry['request']['row_id'], decision=entry['result']['decision'], reason='DEPENDENCY_NOT_EXECUTABLE', request=entry['request'], identity=entry['identity']))
            else:
                executable.append(entry)
                ready.add(entry['request']['row_id'])
        summary = dict(source_digest=original.digest, selected=executable, skipped=skipped,
                       settings=asdict(settings),
                       save_behavior='Save entire running configuration once after attempted writes, including partial changes. EdgeSwitch may interrupt management; recognized save question is answered y.')
        digest = hashlib.sha256(canonical(summary).encode()).hexdigest()
        payload = canonical(dict(summary=summary, plan=data, decisions=intent['decisions']))
        reference = uuid4().hex
        # Added presentation metadata must not make a consumed pre-revision
        # confirmation executable again. Reuse its exact original bound payload.
        legacy = dict(summary, skipped=[{k: v for k, v in e.items() if k not in {'request', 'identity'}} for e in skipped])
        legacy_digest = hashlib.sha256(canonical(legacy).encode()).hexdigest()
        with self._db() as db:
            row = db.execute("SELECT reference, state, run_path, digest, payload FROM confirmations WHERE digest IN (?, ?) ORDER BY CASE WHEN state='awaiting_confirmation' THEN 1 ELSE 0 END", (digest, legacy_digest)).fetchone()
            if row is None:
                db.execute('INSERT OR IGNORE INTO confirmations VALUES (?, ?, ?, ?, ?)', (reference, digest, payload, 'awaiting_confirmation', ''))
                row = db.execute('SELECT reference, state, run_path, digest, payload FROM confirmations WHERE digest=?', (digest,)).fetchone()
        digest = row[3]
        summary = decode(row[4])['summary']
        with module_logger('configuration', 'execution') as (logger, _):
            logger.info(f'Prepare; digest={original.digest}; confirmation={row[0]}; summary={digest}')
        return dict(status=row[1], reference=row[0], summary_digest=digest, summary=summary, run_path=row[2])

    def prepare_workbook(self, original, workbook, *, expected_digest, settings=ApplySettings()):
        from orbitflow.configuration.v2.workbook import consume_decisions
        intent = consume_decisions(original, workbook, expected_digest=expected_digest,
                                   now=datetime.fromisoformat(original.to_dict()['evaluated_at']))
        return self.prepare(original, intent.to_dict()['decisions'], expected_digest=expected_digest, settings=settings)

    def confirm(self, reference, *, summary_digest, apply=False, credentials=None,
                transport_config=None, inventory_path='data/inventory/inventory.json',
                run_root='outputs/runs/configuration_execution', backups_dir=None):
        """Consume confirmation before connecting; replay never starts work.

        backups_dir=None stores captures in the run; explicit overrides allocate
        an external ROOT/run-id directory and retain relative references.
        """
        require(apply is True, 'explicit apply intent required')
        with self._db() as db:
            db.execute('BEGIN IMMEDIATE')
            record = db.execute('SELECT digest, payload, state, run_path FROM confirmations WHERE reference=?', (reference,)).fetchone()
            require(record is not None and record[0] == summary_digest, 'confirmation summary mismatch')
            require(record[2] == 'awaiting_confirmation', 'confirmation already consumed')
            payload = decode(record[1])
            require(hashlib.sha256(canonical(payload['summary']).encode()).hexdigest() == summary_digest, 'corrupt confirmation')
            # Revalidate immutable content before claiming; authority state is local, not authentication.
            original = BulkPlan(canonical(payload['plan']))
            require(original.digest == payload['summary']['source_digest'], 'confirmation source mismatch')
            db.execute("UPDATE confirmations SET state='claimed' WHERE reference=?", (reference,))
        summary = payload['summary']
        try:
            def started(path):
                with self._db() as db:
                    db.execute('UPDATE confirmations SET run_path=? WHERE reference=?', (str(path), reference))
            spool = _run(summary, credentials or {}, transport_config, inventory_path=inventory_path,
                         run_root=run_root, backups_dir=backups_dir, on_started=started)
            with self._db() as db:
                db.execute("UPDATE confirmations SET state='completed', run_path=? WHERE reference=?", (str(spool.path), reference))
            return spool
        except BaseException:
            with self._db() as db:
                db.execute("UPDATE confirmations SET state='interrupted' WHERE reference=?", (reference,))
            raise


def _observe(session, context, cli, entries, timeout):
    interfaces = InterfaceService(timeout=timeout).collect(session, context, cli=cli)
    vlans = VlanService(timeout=timeout).collect(session, context, cli=cli, preserve_full_evidence=True)
    obs = snapshot(context, interfaces, vlans)
    vids = set()
    for entry in entries:
        p = entry['request']['inputs']
        vids.update(p[k] for k in ('vlan_id', 'pvid', 'native_vlan') if k in p)
        vids.update(p.get('vlans', []))
        vids.update(parse_vlan_list(p.get('tagged_vlans', '')))
    obs['vlan_lookups'] = {str(v): VlanService(timeout=timeout).lookup(session, context, v, cli=cli) for v in sorted(vids)}
    return obs


def _set(value):
    if value == 'ALL':
        return set(range(1, 4095))
    if value == 'NONE':
        return set()
    return set(value) if isinstance(value, list) else None


def _expected_mode(command, previous, exec_prompt, edge):
    """Deterministic mode transition for the approved renderer allowlist."""
    return (edge_execution if edge else cisco_execution).expected_mode(command, previous, exec_prompt)


def verify_row(session, context, cli, entry, before, *, timeout=30.0, correlation=None):
    """Read-only verification returning Verified/Failed/Unknown and scoped evidence.

    Access-only missing operational VLAN may use reliable explicit exact-target
    normalized config; preserve parser unknowns and disclose the fallback source.
    """
    from orbitflow.configuration.v2.evidence import scoped_evidence
    request, result = entry['request'], entry['result']
    t, p = BY_ID[request['template_id']], request['inputs']
    if t.function == 'VLAN Database':
        lookup = VlanService(timeout=timeout).lookup(session, context, p['vlan_id'], cli=cli)
        status = ('Verified' if lookup.get('name') == p['name'] else 'Failed') if lookup['status'] == 'present' else 'Failed' if lookup['status'] == 'absent' else 'Unknown'
        return dict(status=status, lookup=lookup, warnings=['VLAN_INACTIVE'] if lookup.get('operational_status') in {'suspended', 'inactive', 'act/lshut'} else [])
    after = _observe(session, context, cli, [entry], timeout)
    target = result.get('resolved_target', p['interface'])
    key = lambda value: canonical_interface_name(context.platform, value)
    actual = [i for i in after['interfaces'] if key(i['port_name']) == key(target)]
    previous = [i for i in before['interfaces'] if key(i['port_name']) == key(target)]
    if len(actual) != 1 or len(previous) != 1:
        return dict(status='Unknown', error_category='InterfaceEvidenceUnavailable')
    description = p.get('description', previous[0]['port_description'])
    checks = [actual[0]['port_description'] == description]
    # Retain scoped config and prove admin setting preservation independently of link state.
    def settings(obs):
        nodes = [n for n in obs['facts'] if n['kind'] == 'interface' and key(n['value']) == key(target)]
        return nodes[0]['children'] if len(nodes) == 1 else None
    old, new = settings(before), settings(after)
    if old is None or new is None:
        return dict(status='Unknown', error_category='ConfigurationEvidenceUnavailable')
    modified = {'description'} if t.function == 'Interface Description' else (
        {'description', 'mode', 'access', 'routed'} if t.function == 'Access Port' else
        {'description', 'mode', 'allowed', 'allowed_add', 'allowed_remove', 'allowed_except', 'native'} if t.function == 'Trunk Port' else
        {'description', 'include', 'exclude', 'tagged', 'untagged_vlans', 'pvid'})
    if t.function == 'Trunk Port' and context.device_family == 'C3750X' and 'switchport trunk encapsulation dot1q' in result['commands']:
        modified.add('trunk_encapsulation')
        checks.append([n['value'] for n in new if n['kind'] == 'trunk_encapsulation'] == ['dot1q'])
    # Compare stable fact values, not capture line numbers. Omitted fields remain
    # protected separately below; unrelated settings must survive every template.
    def signature(node):
        return (node['kind'], node['value'], [signature(child) for child in node.get('children', [])])
    def preserved(nodes):
        return [signature(n) for n in nodes if n['kind'] not in modified]
    checks.append(preserved(old) == preserved(new))
    evidence = dict(configuration=scoped_evidence(request, after), description=actual[0], preservation='Matched' if all(checks) else 'Description or unrelated setting mismatch')
    if t.function != 'Interface Description':
        try:
            switchport = SwitchportService(timeout=timeout).collect(session, context, target, cli=cli, correlation=correlation).to_dict()
        except Exception as exc:
            evidence['warnings'] = ['Operational switchport evidence unavailable: ' + type(exc).__name__]
            return dict(status='Unknown', error_category=type(exc).__name__, evidence=evidence)
        evidence['switchport'] = switchport
        f = switchport['facts']
        if t.function == 'Access Port':
            access = f['access_vlan']
            if access is None:
                missing_access_field = 'Access Mode VLAN' not in switchport.get('fields', {})
                evidence['missing_fields' if missing_access_field else 'invalid_fields'] = ['Access Mode VLAN']
                explicit = [n['value'] for n in new if n['kind'] == 'access']
                if missing_access_field and after.get('configuration_reliable') is True and f['enabled'] is True and f['administrative_mode'] == 'static access' and len(explicit) == 1 and isinstance(explicit[0], list) and len(explicit[0]) == 1 and type(explicit[0][0]) is int and 1 <= explicit[0][0] <= 4094:
                    access = explicit[0][0]
                    evidence['access_vlan_source'] = 'fresh exact-interface explicit configuration'
                    evidence['warnings'] = ['ACCESS_VLAN_CONFIG_FALLBACK: Access Mode VLAN not reported']
                else:
                    evidence['warnings'] = [('Access Mode VLAN not reported' if missing_access_field else 'Access Mode VLAN malformed') + '; unambiguous explicit configuration fallback unavailable']
                with module_logger('configuration', 'execution') as (logger, _):
                    logger.warning('Access Mode VLAN %s; verification source=%s',
                                   'not reported' if missing_access_field else 'malformed', evidence.get('access_vlan_source', 'unavailable'),
                                   extra=capability_metadata(context, correlation, interface=target, stage='verification', outcome='Fallback' if access is not None else 'Unknown'))
            evidence['access_vlan_check'] = dict(actual=access, requested=p['vlan_id'])
            required = [f['enabled'], f['administrative_mode'], access]
            if any(v is None for v in required):
                return dict(status='Failed' if not all(checks) or f['enabled'] is False or f['administrative_mode'] not in (None, 'static access') else 'Unknown', evidence=evidence)
            checks += [f['enabled'] is True, f['administrative_mode'] == 'static access', access == p['vlan_id']]
            evidence['vlan_lookup'] = after['vlan_lookups'].get(str(p['vlan_id']))
            lookup = evidence['vlan_lookup'] or {}
            evidence.setdefault('warnings', []).extend(['GLOBAL_VLAN_NOT_ACTIVE'] if lookup.get('status') == 'absent' or lookup.get('operational_status') in {'inactive', 'suspended', 'act/lshut'} else [])
        elif t.function == 'Trunk Port':
            desired = result['desired_allowed_state']
            values = set(desired['values'])
            allowed = set(range(1, 4095)) - values if desired['all'] else values
            native = result['projected_state']['native']
            if any(f[k] is None for k in ('enabled', 'administrative_mode', 'allowed_vlans', 'native_vlan')) or len(native) != 1:
                evidence['warnings'] = ['Missing operational fields: ' + ', '.join(k for k in ('enabled', 'administrative_mode', 'allowed_vlans', 'native_vlan') if f[k] is None)]
                return dict(status='Unknown', evidence=evidence)
            checks += [f['enabled'] is True, f['administrative_mode'] == 'trunk', _set(f['allowed_vlans']) == allowed, f['native_vlan'] == native[0]]
        else:
            desired = result['projected_state']
            if any(f[k] is None for k in ('pvid', 'tagged_vlans', 'untagged_vlans')):
                evidence['warnings'] = ['Missing operational fields: ' + ', '.join(k for k in ('pvid', 'tagged_vlans', 'untagged_vlans') if f[k] is None)]
                return dict(status='Unknown', evidence=evidence)
            checks += [f['pvid'] == desired['pvid'], _set(f['tagged_vlans']) == set(desired['tagged'])]
            # PVID untagged handling is checked independently from participation.
            if desired['pvid'] is not None:
                checks.append((desired['pvid'] in _set(f['untagged_vlans'])) == (desired['pvid'] not in set(desired['tagged'])))
            evidence['lookups'] = after['vlan_lookups']
            wanted = set(parse_vlan_list(p.get('tagged_vlans', '')))
            for vid in wanted | ({p['pvid']} if 'pvid' in p else set()):
                lookup = after['vlan_lookups'][str(vid)]
                ports = [v for v in lookup.get('ports', []) if key(v['interface']) == key(target)]
                if lookup['status'] != 'present' or not lookup.get('ports_complete') or len(ports) != 1:
                    return dict(status='Unknown', evidence=evidence)
                port = ports[0]
                remove = p['action'] == 'Remove' and vid in wanted
                checks.append(port['configured'].lower() == ('exclude' if remove else 'include'))
                if vid in wanted:
                    checks.append(port['tagging'].lower() == ('untagged' if remove else 'tagged'))
    return dict(status='Verified' if all(checks) else 'Failed', evidence=evidence)


def _run(summary, credentials, transport_config, *, inventory_path, run_root, backups_dir, on_started=None):
    settings = ApplySettings(**summary['settings'])
    groups = {}
    for entry in summary['selected']:
        groups.setdefault(entry['request']['inputs']['management_ip'], []).append(entry)
    secrets = [v for credential in credentials.values() for v in (credential.username, credential.password, credential.secret) if v]
    capture_secrets = {v for credential in credentials.values() for v in (credential.password, credential.secret) if v}
    pattern = re.compile('|'.join(re.escape(v) for v in sorted(set(secrets), key=len, reverse=True))) if secrets else None
    def clean(text):
        text = sanitize_text(text)
        return pattern.sub('[REDACTED]', text) if pattern else text
    spool = ResultSpool.create(run_root, 'configuration_execution', len(groups), clean=clean)
    if on_started:
        on_started(spool.path)
    (spool.path / 'summary.json').write_text(canonical(summary), encoding='utf-8')
    journal = ResultJournal(spool.path / 'events.jsonl', clean=clean)
    backup = BackupWriter(Path(backups_dir) / spool.path.name if backups_dir else spool.path / 'backups', datetime.now(timezone.utc), exact_directory=True)
    store = JsonInventoryStore(inventory_path)
    with module_logger('configuration', 'execution') as (logger, log_path):
        def event(ip, stage, **values):
            item = dict(run_id=spool.path.name, digest=summary['source_digest'], management_ip=ip,
                        stage=stage, timestamp=_now(), log_reference=str(log_path), **values)
            journal.append(item)
            logger.info(clean(f"run={spool.path.name}; digest={summary['source_digest']}; ip={ip}; stage={stage}; row={values.get('row_id', '-')}; command={values.get('command_index', '-')}; status={values.get('status', '-')}; category={values.get('error_category', '-') }; backup={values.get('backup_path', '-')}"))
        def worker(ip):
            entries = groups[ip]
            attempted, rows, usable = False, [], True
            save = dict(status='Not required')
            event(ip, 'connect')
            try:
                require(ip in credentials, 'credentials unavailable')
                with connect_device(ip, credentials[ip], transport_config) as session:
                    with DeviceCLI(session) as cli:
                        event(ip, 'preflight')
                        context = DeviceInventoryResolver(store, sanitize_fact=clean).resolve(session, management_ip=ip, cli=cli)
                        _gate(all(identity(context) == e['identity'] for e in entries), 'FRESH_IDENTITY_MISMATCH')
                        before = _observe(session, context, cli, entries, settings.command_timeout)
                        exec_prompt = cli.prompt
                        require(exec_prompt.endswith('#'), 'privileged EXEC required')
                        event(ip, 'backup')
                        content = ConfigurationService(timeout=settings.command_timeout).collect(session, context, cli=cli)
                        for secret in capture_secrets:
                            content = content.replace(secret, '[REDACTED]')
                        path = backup.write(context.hostname, context.platform, content)
                        try:
                            backup_reference = Path(os.path.relpath(path, spool.path)).as_posix()
                        except ValueError:
                            # Windows external overrides may be on another drive.
                            backup_reference = path.resolve().as_posix()
                        event(ip, 'backup_complete', backup_reference=backup_reference, backup_path=str(path.resolve()))
                        completed = set()
                        try:
                            for entry in entries:
                                r, approved = entry['request'], entry['result']
                                rid = r['row_id']
                                row = dict(row_id=rid, decision=approved['decision'], status='Not executed')
                                rows.append(row)
                                try:
                                    _gate(usable, 'SESSION_UNUSABLE')
                                    _gate(set(approved['dependencies']) <= completed, 'DEPENDENCY_FAILED')
                                    event(ip, 'row_preflight', row_id=rid)
                                    # A fresh snapshot per row incorporates preceding verified effects.
                                    before = _observe(session, context, cli, [entry], settings.command_timeout)
                                    from orbitflow.configuration.v2.evidence import scoped_evidence
                                    row['pre_config'] = scoped_evidence(r, before)
                                    event(ip, 'pre_row_evidence', row_id=rid, evidence=row['pre_config'])
                                    fresh = plan([r], {ip: before}, decisions={rid: 'Approve'}).to_dict()['results'][0]
                                    row['preflight_findings'] = fresh.get('findings', [])
                                    _gate(fresh['deployment_ready'], 'FRESH_PREFLIGHT_BLOCKED')
                                    _gate(fresh.get('resolved_target') == approved.get('resolved_target'), 'TARGET_DRIFT')
                                    _gate(fresh['commands'] == approved['commands'] and fresh['no_op'] == approved['no_op'], 'APPROVED_COMMAND_DRIFT')
                                    _gate(fresh.get('projected_state') == approved.get('projected_state'), 'APPROVED_RESULT_DRIFT')
                                    if BY_ID[r['template_id']].function == 'VLAN Port' and r['inputs']['action'] != 'Remove':
                                        row['missing_prerequisite_vlans'] = [v for v, lookup in before['vlan_lookups'].items() if lookup['status'] != 'present']
                                        _gate(not row['missing_prerequisite_vlans'], 'VLAN_PREREQUISITE_UNAVAILABLE')
                                    rejected = False
                                    for index, command in enumerate(approved['commands'], 1):
                                        cli.execution_mode(exec_prompt, context.platform)
                                        event(ip, 'command_intent', row_id=rid, command_index=index, command=command)
                                        attempted = True
                                        row['status'] = 'Unknown'
                                        previous_prompt = cli.prompt
                                        started = monotonic()
                                        try:
                                            response = cli.run_command(command, timeout=settings.command_timeout)
                                        except BaseException:
                                            event(ip, 'command_unknown', row_id=rid, command_index=index,
                                                  response=_safe_source(getattr(cli, 'last_response', ''), context.platform), status='Unknown')
                                            raise
                                        rejected = command_rejected(response)
                                        if cli.prompt not in _expected_mode(command, previous_prompt, exec_prompt, context.platform == 'ubiquiti_edgeswitch'):
                                            rejected = True
                                        event(ip, 'command_result', row_id=rid, command_index=index,
                                              response=_safe_source(response, context.platform), status='Rejected' if rejected else 'Returned', elapsed_seconds=monotonic() - started)
                                        if rejected:
                                            row['status'] = 'Failed'
                                            break
                                    if cli.prompt != exec_prompt:
                                        # Only known vendor modes admit recovery, never arbitrary '#'.
                                        for index in range(2):
                                            cli.execution_mode(exec_prompt, context.platform)
                                            command = 'exit' if context.platform == 'ubiquiti_edgeswitch' else 'end'
                                            event(ip, 'mode_intent', row_id=rid, command=command)
                                            response = cli.run_command(command, timeout=settings.command_timeout)
                                            event(ip, 'mode_result', row_id=rid, response=_safe_source(response, context.platform))
                                            if cli.prompt == exec_prompt:
                                                break
                                        require(cli.prompt == exec_prompt, 'EXEC recovery failed')
                                    event(ip, 'verification_intent', row_id=rid, commands=entry['verification_commands'])
                                    if not rejected:
                                        row['status'] = 'Unknown'
                                    started = monotonic()
                                    verification = verify_row(session, context, cli, entry, before, timeout=settings.command_timeout, correlation={'run_id': spool.path.name, 'digest': summary['source_digest'], 'row_id': rid})
                                    row.update(status='Failed' if rejected else verification['status'], verification=verification)
                                    for warning in verification.get('evidence', {}).get('warnings', []) if isinstance(verification.get('evidence'), dict) else []:
                                        event(ip, 'verification_warning', row_id=rid, warning=warning)
                                    row['verification_seconds'] = monotonic() - started
                                    if row['status'] == 'Verified':
                                        completed.add(rid)
                                except Exception as exc:
                                    row['error_category'] = type(exc).__name__
                                    if isinstance(exc, ExecutionBlocked):
                                        row['blocker'] = exc.code
                                    try:
                                        cli.require_session(session)
                                        usable = cli.prompt == exec_prompt
                                    except Exception:
                                        usable = False
                                event(ip, 'row_result', **row)
                        finally:
                            try:
                                cli.require_session(session)
                                usable = usable and cli.prompt == exec_prompt
                            except Exception:
                                usable = False
                            if attempted and usable:
                                event(ip, 'save_intent', command='write memory')
                                save = dict(status='Unknown', error_category='SaveCapabilityIncomplete')
                                try:
                                    save = save_configuration(session, context, cli=cli, exec_prompt=exec_prompt, timeout=settings.save_timeout, correlation={'run_id': spool.path.name, 'digest': summary['source_digest']})
                                except BaseException:
                                    event(ip, 'save_result', status='Unknown', error_category='SaveCapabilityIncomplete',
                                          response=_safe_source(getattr(cli, 'last_response', ''), context.platform))
                                    raise
                            elif attempted:
                                save = dict(status='Unknown', error_category='SessionUnusable')
                            event(ip, 'save_result', **save)
                event(ip, 'cleanup', status='Completed')
                return dict(rows=rows, save=save)
            except Exception as exc:
                event(ip, 'device_failure', error_category=type(exc).__name__)
                done = {r['row_id'] for r in rows}
                for entry in entries:
                    rid = entry['request']['row_id']
                    if rid not in done:
                        row = dict(row_id=rid, status='Not executed', error_category=type(exc).__name__)
                        rows.append(row)
                        event(ip, 'row_result', **row)
                return dict(rows=rows, save=save, error_category=type(exc).__name__)
        def persist(outcome):
            ip = list(groups)[outcome.position - 1]
            value = outcome.value or {}
            failed = (outcome.error_category or value.get('error_category')
                      or value.get('save', {}).get('status') == 'Unknown'
                      or value.get('save', {}).get('explicit_error')
                      or any(r['status'] != 'Verified' for r in value.get('rows', [])))
            spool.append(outcome, target=ip, failed=bool(failed))
        event('-', 'confirm', status='Claimed')
        with spool.collection():
            execute_devices(list(groups), worker, config=ExecutionConfig(settings.max_concurrent_devices, settings.connection_start_interval, settings.connection_retry_delay), on_outcome=persist)
        event('-', 'recording', status='Completed')
    return spool


def operator_summary(prepared):
    """Pure presentation projection; full confirmation payload/digest remain unchanged."""
    source = prepared['summary']
    devices = {}
    changes = no_ops = 0
    reasons = []
    for entry in source['selected']:
        r, result = entry['request'], entry['result']
        ip = r['inputs']['management_ip']
        t = BY_ID[r['template_id']]
        device = devices.setdefault(ip, dict(ip=ip, hostname=(entry.get('identity') or {}).get('hostname', ''), family=t.family, actions={}))
        action = t.function + ': ' + r['inputs'].get('action', 'Set')
        device['actions'][action] = device['actions'].get(action, 0) + 1
        no_ops += bool(result['no_op'])
        changes += not result['no_op']
        for finding in result.get('findings', []):
            reasons.append(dict(row_id=r['row_id'], source=f"{t.sheet} row {r.get('row', '?')} / {ip} / {r['inputs'].get('interface', '')}", reason=finding, details={k: r['inputs'][k] for k in ('vlan_id', 'pvid', 'native_vlan', 'vlans', 'tagged_vlans') if k in r['inputs']}))
    for entry in source['skipped']:
        r = entry.get('request', {})
        reasons.append(dict(row_id=entry['row_id'], source=f"{BY_ID[r['template_id']].sheet} row {r.get('row', '?')} / {r['inputs']['management_ip']}" if r else 'retained row', reason=entry['reason'], details=entry.get('blockers', [])))
    return dict(reference=prepared['reference'], source_digest=source['source_digest'], summary_digest=prepared['summary_digest'],
                device_count=len(devices), changes=changes, no_ops=no_ops, skipped=len(source['skipped']),
                concurrency=source['settings']['max_concurrent_devices'], devices=list(devices.values()), reasons=reasons,
                save_behavior=source['save_behavior'], fresh_checks='Offline selection only. Fresh identity, state, VLAN prerequisites and protected backup are checked after confirmation.')


def render_summary(summary):
    """Concise text for CLI or other operator surfaces, without nested evidence."""
    lines = [f"Execution reference: {summary['reference']}",
             f"Plan: {summary['source_digest'][:12]} (full digest in preparation/summary.json)",
             f"Devices: {summary['device_count']} | Changes: {summary['changes']} | No-op: {summary['no_ops']} | Skipped: {summary['skipped']} | Concurrency: {summary['concurrency']}"]
    for device in summary['devices']:
        actions = ', '.join(f"{name}={count}" for name, count in device['actions'].items())
        lines.append(f"{device['hostname']} {device['ip']} {device['family']} | {actions}")
    for reason in summary['reasons']:
        lines.append(f"{reason['source']} / {reason['row_id']}: {readable(reason['reason'])}" + (f"; {readable(reason['details'])}" if reason.get('details') else ''))
    lines.extend([summary['fresh_checks'], summary['save_behavior']])
    return '\n'.join(lines)


def readable(value):
    """Readable retained facts/evidence; no JSON encoding in operator cells."""
    if value is None:
        return 'Unknown'
    if isinstance(value, list):
        return '\n'.join(readable(v) for v in value)
    if isinstance(value, dict):
        if 'excerpt' in value:
            return f"{value.get('source_filename', '')}:{value.get('line', '')}: {value['excerpt']}"
        return '\n'.join(f"{k}: {readable(v)}" for k, v in value.items())
    return str(value)


def export_results(run_path, output):
    """Offline literal report grouped by original template, from retained journal only."""
    from openpyxl import Workbook
    from openpyxl.cell import WriteOnlyCell
    from openpyxl.styles import Alignment
    from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
    require(not Path(output).exists(), 'output already exists')
    run_path = Path(run_path)
    source = decode((run_path / 'summary.json').read_text(encoding='utf-8'))
    book = Workbook(write_only=True)
    summary = book.create_sheet('Run Summary')
    details = book.create_sheet('Evidence Details')
    details.append(['Row / Event', 'Field', 'Part', 'Complete readable text'])
    def literal_row(sheet, values, reference=''):
        cells = []
        for column, value in enumerate(values, 1):
            text = ILLEGAL_CHARACTERS_RE.sub('', sanitize_text(str(value)))
            if len(text) > 30000:
                for offset in range(0, len(text), 30000):
                    literal_row(details, [reference, column, offset // 30000 + 1, text[offset:offset + 30000]])
                text = text[:29000] + f"\nContinued completely in Evidence Details: {reference}, field {column}"
            cell = WriteOnlyCell(sheet, value=text)
            cell.data_type = 's'
            cell.alignment = Alignment(wrap_text=True, vertical='top')
            cells.append(cell)
        sheet.append(cells)
    literal_row(summary, ['Run', run_path.name])
    literal_row(summary, ['Plan digest', source['source_digest']])
    literal_row(summary, ['Save policy', source.get('save_behavior', '')])
    saves, backups, row_offsets = {}, {}, {}
    for index, event in enumerate(ResultJournal(run_path / 'events.jsonl').records(), 1):
        stage, ip, rid = event['stage'], event.get('management_ip', ''), event.get('row_id')
        literal_row(details, [f'Event {index}', stage, 1, readable(event)], f'Event {index}')
        if stage == 'save_result':
            saves[ip] = {k: event[k] for k in ('status', 'explicit_error', 'error_category') if k in event}
        elif stage == 'backup_complete':
            backups[ip] = event.get('backup_reference', '')
        elif rid:
            # Only journal positions are retained across the run; evidence is read per row.
            row_offsets.setdefault(rid, []).append(index)
    for ip in dict.fromkeys([e['request']['inputs']['management_ip'] for e in source['selected']]):
        literal_row(summary, [ip, 'Save: ' + readable(saves.get(ip, {'status': 'Not recorded'})), 'Backup: ' + backups.get(ip, 'Not recorded')])
    sheets = {}
    headers = ['Run ID', 'IP', 'Row ID', 'Source row', 'Hostname', 'Family', 'Original Inputs', 'Decision', 'No-op', 'Pre-config', 'Config Sent', 'Config Evidence (post-row)', 'Apply Status', 'Status Verification', 'Error', 'Warning', 'Save Status', 'Backup Reference', 'Log Reference']
    entries = [(entry, False) for entry in source['selected']] + [(entry, True) for entry in source['skipped']]
    entries.sort(key=lambda pair: (pair[0].get('request', {}).get('sheet_order', 999), pair[0].get('request', {}).get('row', 999)))
    for entry, skipped in entries:
        r, result = entry.get('request', {}), entry.get('result', {})
        t = BY_ID.get(r.get('template_id'))
        title = t.sheet if t else 'Legacy Skipped'
        if title not in sheets:
            sheet = book.create_sheet(title)
            sheet.freeze_panes = 'D2'
            for col in ('G', 'J', 'K', 'L', 'N', 'O', 'P'):
                sheet.column_dimensions[col].width = 55
            literal_row(sheet, headers)
            sheets[title] = sheet
        rid = entry.get('row_id', r.get('row_id'))
        ip = r.get('inputs', {}).get('management_ip', '')
        event, pre_config, sent = {}, 'Not captured', []
        positions = set(row_offsets.get(rid, []))
        for index, item in enumerate(ResultJournal(run_path / 'events.jsonl').records(), 1):
            if index not in positions:
                continue
            stage = item['stage']
            if stage == 'pre_row_evidence':
                pre_config = item['evidence']
            elif stage == 'command_intent':
                sent.append(dict(command=item['command'], status='Pending / uncertain'))
                event = dict(item, status='Unknown')
            elif stage in {'command_result', 'command_unknown'} and sent:
                sent[-1].update(status=item.get('status', 'Unknown'), response=item.get('response', ''))
            elif stage == 'row_result':
                event = item
                pre_config = item.get('pre_config', pre_config)
        verification = event.get('verification', {})
        evidence = verification.get('evidence', verification.get('lookup', 'Not captured'))
        errors = {k: event[k] for k in ('error_category', 'blocker', 'missing_prerequisite_vlans') if event.get(k)}
        if event.get('blocker'):
            errors['Preflight findings'] = event.get('preflight_findings', [])
        if verification.get('error_category'):
            errors['Verification error'] = verification['error_category']
        if skipped:
            errors.update(reason=entry['reason'], details=entry.get('blockers', []))
        for command in sent:
            if command['status'] == 'Rejected':
                errors['Rejected command'] = command
            elif command['status'] in {'Unknown', 'Pending / uncertain'}:
                errors['Uncertain command'] = command
        if verification.get('status') == 'Failed':
            errors['Verification'] = evidence
        warnings = list(evidence.get('warnings', [])) if isinstance(evidence, dict) else []
        warnings.extend(verification.get('warnings', []))
        if not event.get('blocker'):
            warnings.extend(event.get('preflight_findings', []))
        apply_status = ('Skipped' if skipped else 'Unknown' if any(c['status'] in {'Unknown', 'Pending / uncertain'} for c in sent) else 'Rejected' if any(c['status'] == 'Rejected' for c in sent) else 'Applied' if sent else 'No-op' if result.get('no_op') and verification else 'Not executed')
        literal_row(sheets[title], [run_path.name, ip, rid, r.get('row', ''), (entry.get('identity') or {}).get('hostname', ''), t.family if t else '',
            readable(r.get('source_inputs') or r.get('inputs', {})), entry.get('decision', result.get('decision', '')), result.get('no_op', ''),
            readable(pre_config), readable(sent) if sent else 'None (no-op)' if result.get('no_op') else 'None attempted', readable(evidence),
            apply_status, readable(dict(requested=result.get('projected_state') or r.get('inputs', {}), actual_checks=verification)) if verification else 'Not performed', readable(errors), readable(warnings),
            saves.get(ip, {}).get('status', 'Not recorded'), backups.get(ip, ''), event.get('log_reference', '')], rid)
    with Path(output).open('xb') as stream:
        book.save(stream)
    return Path(output)
