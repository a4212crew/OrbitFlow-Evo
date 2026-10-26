"""Literal Excel blocks: fresh shells, redacted evidence, success-only automatic save.

Explicit engineer persistence commands may save before any later row failure.

Public API: create_template, load_rows, summary, execute, regenerate_report.
No legacy plan conversion, automatic replay, rollback or independent verification.
"""
from copy import deepcopy
from contextlib import contextmanager
from dataclasses import dataclass, asdict
from threading import Event, current_thread, main_thread
import signal
from datetime import datetime, timezone
from pathlib import Path
import hashlib
import ipaddress
import math
import os
import re
from tempfile import NamedTemporaryFile

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment
from orbitflow.config import ExecutionConfig
from orbitflow.configuration.manual_auth import authorize
from orbitflow.configuration.plans import canonical
from orbitflow.configuration_backup import BackupWriter, filename_component
from orbitflow.execution import execute_devices
from orbitflow.result_spool import ResultSpool, ResultJournal
from orbitflow.progress import Progress
from orbitflow.logging import sanitize_text, module_logger
from orbitflow.transport import connect_device
from orbitflow.inventory import DeviceInventoryResolver, JsonInventoryStore
from orbitflow.capabilities.configuration import ConfigurationService
from orbitflow.capabilities.save import save_configuration
from orbitflow.vendors.common import DeviceCLI, normalize_output
from orbitflow.vendors.configuration_facts import _safe_source
from orbitflow.vendors import manual_configuration as vendor

EMPTY_ERROR = 'Invalid input: command block contains no executable commands'
INPUT_ERROR = 'Invalid input: management_ip must be an IP address'
CELL_ERROR = 'Invalid input: command cell must be text'
SIZE_ERROR = 'Invalid input: command cell exceeds 32767 characters'
COUNT_ERROR = 'Invalid input: command block exceeds 1000 nonblank lines'
FORMULA_ERROR = 'Invalid input: formula cells are unsupported'
CONTROL_ERROR = 'Invalid input: control character at cell line '
SCOPE = 'Transcript only — configuration not independently verified'
# Disclosure-only recognition, never used to accept/reject CLI. Shared evidence
# policy covers full vendor labels; these common abbreviated labels also identify
# operands whose bare echoes must be masked.
DISCLOSURE_LABEL = re.compile(
    r'(?i)(?<![\w./:-])(?:pass(?:w(?:or(?:d)?)?)?|sec(?:r(?:e(?:t)?)?)?|'
    r'comm(?:u(?:n(?:i(?:t(?:y)?)?)?)?)?)(?![\w./-])')


def input_error(value):
    return value in {INPUT_ERROR, EMPTY_ERROR, CELL_ERROR, SIZE_ERROR, COUNT_ERROR, FORMULA_ERROR} or (
        isinstance(value, str) and re.fullmatch(re.escape(CONTROL_ERROR) + r'[1-9][0-9]{0,4}', value) is not None)


INTERACTION = re.compile(r'(?i)(?:--\s*more\s*--|\[more\]|password\s*:(?=\s*(?:\r?\n|$))|username\s*:(?=\s*(?:\r?\n|$))|\(y/n\)|\[y/n\]|\[yes/no\]|\[confirm\]|press (?:any|enter|return)|continue\?|are you sure|destination filename|overwrite\?|\[(?:yes|no|y|n)(?:/[^\]]+)?\]|(?:enter|input|confirm|proceed)[^\r\n]{0,120}:|\?\s*$)')


@contextmanager
def interrupt_guard(cancelled):
    """Notify active workers before the scheduler waits for owned cleanup."""
    previous = None
    if current_thread() is main_thread():
        previous = signal.getsignal(signal.SIGINT)
        def interrupted(signum, frame):
            cancelled.set()
            if callable(previous):
                previous(signum, frame)
            else:
                raise KeyboardInterrupt()
        signal.signal(signal.SIGINT, interrupted)
    try:
        yield
    except BaseException:
        cancelled.set()
        raise
    finally:
        if previous is not None:
            signal.signal(signal.SIGINT, previous)


def now():
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class CaptureSettings:
    first_response: float = 10.0
    inactivity: float = 1.0
    maximum: float = 30.0
    setup_timeout: float = 30.0
    save_timeout: float = 60.0

    def __post_init__(self):
        for value in asdict(self).values():
            if type(value) not in (int, float) or not math.isfinite(value) or not 0 < value <= 300:
                raise ValueError('Capture deadlines must be finite seconds in (0, 300]')
        if max(self.first_response, self.inactivity) >= self.maximum:
            raise ValueError('Capture overall deadline must exceed first response and inactivity')


def commands(text):
    """Validate transport structure only; return literal nonblank authored lines."""
    if text is None:
        raise ValueError(EMPTY_ERROR)
    if not isinstance(text, str):
        raise ValueError(CELL_ERROR)
    if len(text) > 32767:
        raise ValueError(SIZE_ERROR)
    source = text.replace('\r\n', '\n').split('\n')
    for number, line in enumerate(source, 1):
        if not line.strip():
            continue
        if any(ord(c) < 32 or 127 <= ord(c) <= 159 or c in '\u2028\u2029' for c in line):
            raise ValueError(CONTROL_ERROR + str(number))
    lines = [line for line in source if line.strip()]
    if not lines:
        raise ValueError(EMPTY_ERROR)
    if len(lines) > 1000:
        raise ValueError(COUNT_ERROR)
    return lines


def create_template(directory='data/input/generated_template'):
    """Allocate an exclusive daily template; command cells accept Alt+Enter."""
    root = Path(directory)
    root.mkdir(parents=True, exist_ok=True)
    book = Workbook()
    sheet = book.active
    sheet.title = 'Manual Configuration'
    sheet.append(['management_ip', 'command'])
    sheet.column_dimensions['A'].width = 24
    sheet.column_dimensions['B'].width = 90
    sheet['B2'].alignment = Alignment(wrap_text=True, vertical='top')
    from openpyxl.comments import Comment
    sheet['B1'].comment = Comment('Literal newline-separated commands (Alt+Enter). Starts in global configuration mode. Engineer CLI is sent literally, including explicit save commands. Automatic save is success-only; unsupported questions stop the row. Protect credential-bearing source workbooks.', 'OrbitFlow')
    for sequence in range(1, 100000):
        path = root / f'manual_config_{datetime.now():%Y%m%d}_{sequence:03d}.xlsx'
        try:
            stream = path.open('xb')
        except FileExistsError:
            continue
        try:
            with stream:
                book.save(stream)
        except BaseException:
            path.unlink(missing_ok=True)
            raise
        return path
    raise ValueError('Template allocation exhausted')


def load_rows(path):
    """Retain every nonempty input row and fixed validation errors, never secrets."""
    book = load_workbook(path, read_only=True, data_only=False)
    rows = []
    try:
        sheet = book.active
        iterator = sheet.iter_rows()
        headers = next(iterator, ())
        if [cell.value for cell in headers] != ['management_ip', 'command']:
            raise ValueError('Manual workbook requires exactly management_ip and command columns')
        for number, cells in enumerate(iterator, 2):
            values = [cell.value for cell in cells]
            if all(value is None for value in values):
                continue
            item = dict(source_row=number, management_ip='', commands=[], error='')
            try:
                item['management_ip'] = str(ipaddress.ip_address(str(values[0]).strip()))
                if any(cell.data_type == 'f' for cell in cells):
                    raise ValueError(FORMULA_ERROR)
                item['commands'] = commands(values[1])
                item['command_lines'] = [i for i, line in enumerate(values[1].replace('\r\n', '\n').split('\n'), 1) if line.strip()]
            except Exception as exc:
                item['error'] = str(exc) if input_error(str(exc)) else INPUT_ERROR
                item['commands'] = []
            rows.append(item)
            if len(rows) > 10000:
                raise ValueError('Manual workbook exceeds 10000 rows')
    finally:
        book.close()
    if not rows:
        raise ValueError('Manual workbook contains no rows')
    return rows


def summary(rows, execution_config=ExecutionConfig(1), settings=CaptureSettings()):
    """Digest binds confirmation to exact ordered validated rows and settings."""
    if not 1 <= execution_config.max_concurrent_devices <= 5:
        raise ValueError('Manual concurrency must be 1–5')
    body = dict(rows=rows, execution=asdict(execution_config), capture=asdict(settings))
    return dict(digest=hashlib.sha256(canonical(body).encode()).hexdigest(),
                rows=len(rows), devices=len({r['management_ip'] for r in rows if r['management_ip']}),
                commands=sum(len(r['commands']) for r in rows),
                invalid=sum(bool(r['error']) for r in rows), concurrency=execution_config.max_concurrent_devices)


def execute(rows, *, profile, password, confirmation_digest, credentials, transport_config,
            execution_config=ExecutionConfig(1), settings=CaptureSettings(),
            inventory_path='data/inventory/inventory.json',
            run_root='outputs/runs/manual_configuration',
            backups_dir='outputs/backups/configuration', progress=None, on_started=None,
            reports_dir='outputs/reports/manual_configuration', on_output=None):
    """Apply only after local password and summary-bound explicit confirmation.

    credentials maps IP to existing DeviceCredentials. Authored CLI may contain secrets;
    source workbooks must be protected. Save status describes automatic save only.
    Returns a retained run path. Refreshes one consolidated report per device via the
    scheduler and optional on_output(Path); export failures retain offline recovery.
    """
    authorize(profile, password)  # Before allocation, connection, identity or backup.
    rows = deepcopy(rows)
    # API callers receive the same validation as XLSX input; do not trust supplied
    # row dictionaries, commands or digest as execution authorization by themselves.
    if not 1 <= len(rows) <= 10000:
        raise ValueError('Manual input requires 1–10000 rows')
    for row in rows:
        if row.get('error') != '' and not input_error(row.get('error')):
            raise ValueError('Invalid manual input diagnostic')
        if row.get('error') and row.get('commands') != []:
            raise ValueError('Invalid rows cannot retain command cells')
        if row.get('management_ip') or not row.get('error'):
            try:
                ipaddress.ip_address(row['management_ip'])
            except (TypeError, ValueError):
                raise ValueError(INPUT_ERROR) from None
        if set(row) - {'command_lines'} != {'source_row', 'management_ip', 'commands', 'error'}:
            raise ValueError('Invalid manual row schema')
        if type(row['source_row']) is not int or row['source_row'] < 2:
            raise ValueError('Invalid source row')
        if not row['error']:
            if commands('\n'.join(row['commands'])) != row['commands']:
                raise ValueError('Invalid commands')
    for row in rows:
        mapping = row.get('command_lines', list(range(1, len(row['commands']) + 1)))
        if (len(mapping) != len(row['commands']) or any(type(i) is not int or i < 1 for i in mapping)
                or mapping != sorted(set(mapping))):
            raise ValueError('Invalid command line mapping')
    if len({r['source_row'] for r in rows}) != len(rows):
        raise ValueError('Duplicate source row identity')
    rows = sorted(rows, key=lambda r: r['source_row'])
    bound = summary(rows, execution_config, settings)
    if confirmation_digest != bound['digest']:
        raise ValueError('Explicit manual summary confirmation required')
    # Disclosure policy never rejects authored CLI. Learn sensitive operands so
    # bare/fragmented device echoes are redacted as well as labelled output.
    secrets = {password}
    secrets.update(v for c in credentials.values() for v in (c.username, c.password, c.secret) if v)
    for row in rows:
        for command in row['commands']:
            label = DISCLOSURE_LABEL.search(command)
            if label:
                secrets.update(re.findall(r"[^\s:=\"']+", command[label.end():]))
            for platform in vendor.PROFILES:
                masked = _safe_source(command, platform)
                if '[REDACTED]' in masked:
                    prefix = masked.split('[REDACTED]', 1)[0].rstrip()
                    operands = command[len(prefix):]
                    secrets.add(operands.strip())
                    secrets.update(re.findall(r"[^\s:=\"']+", operands))
    secret_values = sorted(filter(None, secrets), key=len, reverse=True)
    def clean(text):
        text = normalize_output(str(text))
        for value in secret_values:
            text = text.replace(value, '[REDACTED]')
        # Whole lines retained; shared credential-label policy also covers
        # unanticipated secrets. Terminal escape sequences are removed first.
        lines = []
        for line in sanitize_text(text).split('\n'):
            # An interruption/finalization boundary can leave only a prefix or
            # suffix of an unlabelled secret. Mask such operands conservatively;
            # complete-line buffering already covers ordinary receive chunks.
            line = re.sub(r"[^\s:=\"']+", lambda match: '[REDACTED]'
                          if any(value.startswith(match[0]) or value.endswith(match[0])
                                 for value in secret_values) else match[0], line)
            for platform in vendor.PROFILES:
                line = _safe_source(line, platform)
            lines.append(line)
        return '\n'.join(lines)
    def safe_record(value):
        # Field names are fixed application schema, never device input. Redact
        # device/command text before the shared writer. Trusted fixed categories,
        # validated IPs and artifact references are metadata: replacing short
        # secrets in them would break source identity and offline capture links.
        if isinstance(value, dict):
            return {key: item if key in {'kind', 'status', 'save', 'error', 'verification_scope',
                                                    'management_ip', 'transcript', 'backup', 'log_reference',
                                                    'output', 'reason', 'timestamp', 'digest'}
                    else safe_record(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [safe_record(item) for item in value]
        return clean(value) if isinstance(value, str) else value
    groups = {}
    for row in rows:
        groups.setdefault(row['management_ip'], []).append(row)
    spool = ResultSpool.create(run_root, 'manual_configuration', len(groups), clean=sanitize_text, short_name=True)
    journal = ResultJournal(spool.path / 'events.jsonl', clean=sanitize_text)
    backup = BackupWriter(Path(backups_dir) / spool.path.name, datetime.now(timezone.utc), exact_directory=True)
    store = JsonInventoryStore(inventory_path)
    # Recovery needs source identity/counts, never a replayable command workbook.
    input_rows = [dict(source_row=r['source_row'], management_ip=r['management_ip'],
                       total=len(r['commands']), error=r['error']) for r in rows]
    journal.append(safe_record(dict(kind='input', rows=input_rows, summary=bound, settings=asdict(settings))))
    if on_started:
        on_started(spool.path)
    report_directory = Path(reports_dir) / spool.path.name
    report_directory.mkdir(parents=True, exist_ok=False)
    report_output = report_directory / ('manual_output_' + spool.path.name + '.xlsx')
    # Publish pending rows before any worker connects; later refreshes replace atomically.
    regenerate_report(spool.path, report_output)
    cancelled = Event()
    def checkpoint():
        if cancelled.is_set():
            raise KeyboardInterrupt()
    with interrupt_guard(cancelled), Progress(progress) as reporter, module_logger('manual_configuration', 'execution') as (logger, log_path):
        def event(ip, kind, **values):
            journal.append(safe_record(dict(timestamp=now(), management_ip=ip, kind=kind, log_reference=str(log_path), **values)))
            reporter.emit(ip, kind, **{k: v for k, v in values.items() if k in {'source_row', 'command_index', 'command_total', 'status'}})
            logger.info('Manual configuration stage', extra=dict(management_ip=ip, stage=kind, run_id=spool.path.name))

        def worker(ip):
            stopped = False
            session = None
            transcript = None
            path = None
            try:
                for source in groups[ip]:
                    row = dict(source_row=source['source_row'], management_ip=ip,
                               status='Incomplete', reason='', attempted=0, total=len(source['commands']),
                               last_command=None, save='Not initiated', verification_scope=SCOPE,
                               transcript=str(path.resolve()) if path else '')
                    phase = 'setup'
                    save_sent = False
                    pending = ''
                    try:
                        # Allocate the IP fallback before identification so even
                        # login/setup failures retain a device transcript.
                        if transcript is None:
                            directory = report_directory
                            component = filename_component(ip or 'invalid-input')
                            path = directory / f'{component}_{component}.txt'
                            transcript = path.open('x', encoding='utf-8', newline='\r\n')
                        row['transcript'] = str(path.resolve())
                        event(ip, 'capture', transcript=str(path.resolve()))
                        def record(label, text):
                            transcript.write(clean(text))
                            transcript.flush()
                            os.fsync(transcript.fileno())
                        record('CHECK', '')
                        checkpoint()
                        if stopped:
                            row['reason'] = 'Not attempted: earlier device row failed or unknown'
                        elif source['error']:
                            row['reason'] = source['error']
                            stopped = True
                        else:
                            checkpoint()
                            if session is None:
                                if ip not in credentials:
                                    raise ValueError('Credentials unavailable')
                                event(ip, 'connect', source_row=source['source_row'])
                                session = connect_device(ip, credentials[ip], transport_config)
                            # This context owns a NEW shell every row. No literal
                            # exit is used for cleanup, even from unknown submodes.
                            with DeviceCLI(session, timeout=settings.setup_timeout) as cli:
                                context = DeviceInventoryResolver(store, sanitize_fact=clean).resolve(session, management_ip=ip, cli=cli)
                                desired = report_directory / (filename_component(clean(context.hostname or ip)) + '_' + filename_component(ip or 'invalid-input') + '.txt')
                                if desired != path:
                                    # Exclusive destination claim; preserve the original capture on failure.
                                    try:
                                        with desired.open('xb'):
                                            pass
                                        transcript.close()
                                        try:
                                            path.replace(desired)
                                        except BaseException:
                                            desired.unlink(missing_ok=True)
                                            raise
                                        path = desired
                                    except OSError:
                                        pass
                                    finally:
                                        transcript.close()
                                        transcript = path.open('a', encoding='utf-8', newline='\r\n')
                                    row['transcript'] = str(path.resolve())
                                    event(ip, 'capture', transcript=str(path.resolve()))
                                vendor.adapter(context)  # Before any user configuration writes.
                                phase = 'backup'
                                content = ConfigurationService(timeout=settings.setup_timeout).collect(session, context, cli=cli)
                                for value in secret_values:
                                    content = content.replace(value, '[REDACTED]')
                                saved_backup = backup.write(context.hostname or ip, context.platform, content)
                                event(ip, 'backup', source_row=source['source_row'], backup=str(saved_backup))
                                phase = 'setup'
                                checkpoint()
                                vendor.setup(cli, context, settings.setup_timeout)
                                pending = ''
                                recent = ''
                                received = 0
                                def receive(text):
                                    nonlocal pending, recent, received
                                    received += len(text.encode('utf-8'))
                                    if received > 8 * 1024 * 1024:
                                        raise ValueError('Capture byte limit exceeded')
                                    pending += text
                                    recent = (recent + text)[-65536:]
                                    while '\n' in pending:
                                        line, pending = pending.split('\n', 1)
                                        record('RECEIVE', line.rstrip('\r') + '\n')
                                        event(ip, 'receive', source_row=source['source_row'], text=line)
                                    if len(pending) > 65536:
                                        raise ValueError('Capture line limit exceeded')
                                    if vendor.rejected(normalize_output(recent)):
                                        if pending:
                                            record('RECEIVE', pending)
                                            pending = ''
                                    if vendor.rejected(normalize_output(recent)):
                                        raise ValueError('Vendor rejected command')
                                    checkpoint()
                                phase = 'command capture'
                                for index, command in enumerate(source['commands'], 1):
                                    checkpoint()
                                    row.update(attempted=index, last_command=index)
                                    event(ip, 'command_intent', source_row=source['source_row'], command_index=index, command_total=row['total'], source_line=source.get('command_lines', list(range(1, row['total'] + 1)))[index - 1], command=command)
                                    record('CHECK', '')  # Check durable capture before transmission.
                                    cli.capture_literal(command, first_response=settings.first_response,
                                                        inactivity=settings.inactivity, maximum=settings.maximum, receive=receive)
                                    # A chunk ending at `password:` may be only an echo
                                    # fragment. Classify questions after bounded capture,
                                    # before sending another command; never answer them.
                                    if INTERACTION.search(normalize_output(recent)):
                                        raise ValueError('Unsupported interactive exchange')
                                if pending:
                                    record('RECEIVE', pending)
                                    pending = ''
                                checkpoint()
                                phase = 'finalization'
                                cli.last_response = ''
                                try:
                                    anchor = vendor.finalize(cli, context, settings.setup_timeout)
                                finally:
                                    # Includes partial receive data on synchronization failure.
                                    record('FINALIZATION RECEIVE', cli.last_response)
                                if vendor.rejected(normalize_output(cli.last_response)) or INTERACTION.search(cli.last_response):
                                    raise ValueError('Finalization rejected or interactive')
                                record('CHECK', '')
                                event(ip, 'save_intent', source_row=source['source_row'])
                                checkpoint()
                                phase = 'save'
                                row['save'] = 'Unknown'
                                save_sent = True  # Conservatively Unknown even if sendall fails partially.
                                cli.last_response = ''
                                try:
                                    result = save_configuration(session, context, cli=cli, exec_prompt=anchor, timeout=settings.save_timeout, manual=True)
                                except BaseException:
                                    record('SAVE RECEIVE', cli.last_response)
                                    raise
                                record('SAVE RECEIVE', result['response'])
                                checkpoint()
                                row['save'] = 'Failed' if result.get('explicit_error') else result['status']
                                if result['status'] != 'Saved' or result.get('explicit_error'):
                                    raise ValueError('Save not confirmed or explicitly rejected')
                                phase = 'recording'
                                row.update(status='Completed', reason='')
                    except BaseException as exc:
                        if pending and transcript is not None:
                            try:
                                record('RECEIVE (interrupted)', pending)
                            except BaseException:
                                phase = 'recording'
                            pending = ''
                        stopped = True
                        row['status'] = 'Incomplete'
                        # Never include exception text or raw receive data.
                        detail = str(exc) if str(exc) in {
                            'Credentials unavailable', 'Vendor rejected command', 'Unsupported interactive exchange',
                            'Capture byte limit exceeded', 'Capture line limit exceeded',
                            'Manual entry/save unsupported for identified platform', 'Privileged EXEC required',
                            'Global configuration mode not established', 'Save mode synchronization failed',
                            'Save not confirmed or explicitly rejected', 'Finalization rejected or interactive',
                            'Literal command overall deadline', 'Literal command first response deadline',
                            'Literal command disconnected'} else type(exc).__name__
                        row['reason'] = f'{phase}: {detail}'
                        if save_sent and row['save'] not in {'Saved', 'Failed'}:
                            row['save'] = 'Unknown'
                        if not isinstance(exc, Exception):
                            row['reason'] = f'{phase}: Interrupted'
                    try:
                        event(ip, 'row_result', **{k: v for k, v in row.items() if k != 'management_ip'})
                    except BaseException:
                        # A recording failure must never initiate save, continue
                        # rows or report a successful row. Recovery uses intent.
                        raise
            finally:
                if transcript is not None:
                    transcript.close()
                if session is not None:
                    session.close()
            return dict(management_ip=ip, failed=stopped)

        def persist(outcome):
            try:
                spool.append(outcome, payload=safe_record(outcome.value), target=list(groups)[outcome.position - 1],
                             failed=bool(outcome.error_category or (outcome.value or {}).get('failed')))
            except BaseException:
                cancelled.set()
                raise
            ip = list(groups)[outcome.position - 1]
            try:
                output = regenerate_report(spool.path, report_output, replace=True)
                event(ip, 'report_exported', output=str(output.resolve()))
                if on_output:
                    on_output(output)
            except Exception:
                event(ip, 'report_export_failed', error='Report export failed; durable results retained for offline recovery')
        with spool.collection():
            execute_devices(list(groups), worker, config=execution_config, on_outcome=persist)
    return spool.path


def regenerate_report(run_path, output=None, *, reports_dir='outputs/reports/manual_configuration', management_ip=None, replace=False):
    """Offline recovery from durable input/intents/results; never connects/replays.

    replace=True atomically refreshes an existing workbook; failure retains it.
    Unterminated journal lines are ignored. A save intent without confirmed result
    remains Unknown. Missing rows remain Incomplete, even if collection returned.
    """
    run_path = Path(run_path)
    journal = ResultJournal(run_path / 'events.jsonl')
    # Metadata aggregation is bounded by the 10000-row input limit;
    # command/response data stay in per-device transcripts on disk.
    inputs, results, attempts, saves, captures = [], {}, {}, set(), {}
    for event in journal.records():
        if event['kind'] == 'input':
            inputs = event['rows']
        elif event['kind'] == 'capture':
            captures[event['management_ip']] = event['transcript']
        elif event['kind'] == 'row_result':
            results[event['source_row']] = event
        elif event['kind'] == 'command_intent':
            attempts[event['source_row']] = event['command_index']
        elif event['kind'] == 'save_intent':
            saves.add(event['source_row'])
    if not inputs:
        raise ValueError('Manual run has no durable input snapshot')
    if output is None:
        root = Path(reports_dir)
        root.mkdir(parents=True, exist_ok=True)
        stem = 'manual_output_' + datetime.now().strftime('%Y%m%d_%H%M%S')
        for sequence in range(100000):
            candidate = root / (stem + (f'_{sequence:03d}' if sequence else '') + '.xlsx')
            try:
                stream = candidate.open('xb')
                output = candidate
                break
            except FileExistsError:
                continue
        else:
            raise ValueError('Report allocation exhausted')
    else:
        stream = None
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    # Claim output before constructing streaming XML writers; allocation failure
    # cannot leave unclosed openpyxl generators.
    if replace:
        stream = NamedTemporaryFile(mode='w+b', prefix='.manual-', suffix='.xlsx', dir=output.parent, delete=False)
        temporary = Path(stream.name)
    else:
        stream = stream or output.open('xb')
        temporary = output
    book = None
    try:
        with stream:
            book = Workbook(write_only=True)
            sheet = book.create_sheet('Manual Configuration')
            fields = ['source_row', 'management_ip', 'status', 'reason', 'attempted', 'total', 'last_command', 'save', 'verification_scope', 'transcript']
            sheet.append(fields)
            from openpyxl.cell import WriteOnlyCell
            for source in inputs:
                if management_ip is not None and source['management_ip'] != management_ip:
                    continue
                number = source['source_row']
                result = results.get(number) or dict(source_row=number, management_ip=source['management_ip'], status='Incomplete',
                            reason='Interrupted/recording incomplete' if number in attempts or number in saves else 'Not attempted: run incomplete',
                            attempted=attempts.get(number, 0), total=source['total'], last_command=attempts.get(number),
                            save='Unknown' if number in saves else 'Not initiated', verification_scope=SCOPE, transcript='')
                reference = captures.get(source['management_ip'], '') or result.get('transcript')
                capture = Path(reference) if reference else None
                if capture is not None and not capture.is_absolute():
                    capture = run_path / capture
                cells = []
                for name in fields:
                    cell = WriteOnlyCell(sheet, str(result.get(name, '') if result.get(name) is not None else ''))
                    cell.data_type = 's'  # Formula injection protection for all persisted text.
                    if name == 'transcript':
                        cell.value = str(capture) if capture and capture.is_file() else 'Not captured'
                        if capture and capture.is_file():
                            from urllib.parse import quote
                            try:
                                target = Path(os.path.relpath(capture.resolve(), output.parent.resolve())).as_posix()
                                cell.hyperlink = quote(target, safe='/:')
                            except ValueError:  # Windows cross-drive capture: relative path unavailable.
                                cell.hyperlink = capture.resolve().as_uri()
                            cell.style = 'Hyperlink'
                    cells.append(cell)
                sheet.append(cells)
            sheet.close()
            devices = book.create_sheet('Devices')
            devices.append(['management_ip', 'status', 'completed_rows', 'total_rows', 'capture'])
            grouped = {}
            for source in inputs:
                grouped.setdefault(source['management_ip'], []).append(source)
            for ip, selected in grouped.items():
                completed = sum(results.get(r['source_row'], {}).get('status') == 'Completed' for r in selected)
                status = 'Completed' if completed == len(selected) else 'Incomplete / pending'
                cells = [WriteOnlyCell(devices, value) for value in [ip, status, str(completed), str(len(selected))]]
                for cell in cells:
                    cell.data_type = 's'
                reference = captures.get(ip, '')
                capture = Path(reference) if reference else None
                if capture is not None and not capture.is_absolute():
                    capture = run_path / capture
                link = WriteOnlyCell(devices, capture.name if capture and capture.is_file() else 'Not captured')
                link.data_type = 's'
                if capture and capture.is_file():
                    from urllib.parse import quote
                    try:
                        link.hyperlink = quote(Path(os.path.relpath(capture.resolve(), output.parent.resolve())).as_posix(), safe='/:')
                    except ValueError:
                        link.hyperlink = capture.resolve().as_uri()
                    link.style = 'Hyperlink'
                devices.append(cells + [link])
            devices.close()
            notes = book.create_sheet('Run Notes')
            for text in [SCOPE,
                         'Not saving does not undo running changes.',
                         'Whole-config save may persist unrelated changes.',
                         'Save status describes automatic save only. Explicit user write/save/commit may already have persisted changes before failure.',
                         'Never replay completed or Unknown changes. No automatic retry or rollback.',
                         'Inactivity is not proof of command completion; delayed output may cross command boundaries.']:
                notes.append([text])
            notes.close()
            book.save(stream)
            stream.flush()
            os.fsync(stream.fileno())
        if replace:
            os.replace(temporary, output)
    except BaseException:
        if book is not None:
            for sheet in book.worksheets:
                try:
                    if not sheet.closed:
                        sheet.close()
                    if sheet._writer is not None and Path(sheet._writer.out).exists():
                        sheet._writer.cleanup()
                except Exception:
                    pass  # Preserve the primary export failure and retained run.
        temporary.unlink(missing_ok=True)
        raise
    return output
