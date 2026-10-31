"""Read-only configuration backup; sensitive content never enters outcomes/logs."""
from datetime import datetime, timezone
from pathlib import Path
from ipaddress import ip_address
import re
import sys
from threading import Lock
from uuid import uuid4
from tempfile import NamedTemporaryFile
from orbitflow.result_spool import ResultSpool

from paramiko import AuthenticationException, SSHException

from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE

from orbitflow.capabilities.configuration import (
    ConfigurationService, UnsupportedConfigurationPlatform,
    EmptyConfigurationCapture, ConfigurationCommandRejected,
)
from orbitflow.execution import execute_devices, Progress
from orbitflow.inventory import DeviceInventoryResolver, JsonInventoryStore
from orbitflow.logging import module_logger, sanitize_text
from orbitflow.targets import REQUIRED_COLUMNS
from orbitflow.transport import (
    DeviceCredentials, connect_device, TransportError, TunnelError, TeleportError,
    TransportConfigurationError, UnsupportedPlatformError, DeviceConnectionError,
)
from orbitflow.vendors.common import DeviceCLI, InteractiveCLIError
from orbitflow.vendors.privilege import MissingEnableSecret, EnableAuthenticationFailed
from orbitflow.transport.exceptions import ConnectionRetryExhausted, ConnectionCleanupError


FAILURE_COLUMNS = ('Hostname', 'IP Address', 'Equipment Type', 'Platform',
                   'Failure Stage', 'Failure Reason')
FAILURE_REASONS = {
    'input': 'Required target fields are missing or the management IP is invalid.',
    'connect': 'Device connection could not be established.',
    'inventory': 'Device identity could not be resolved.',
    'capture': 'Complete configuration could not be captured.',
    'disconnect': 'Device session cleanup failed.',
    'write': 'Configuration file could not be written.',
    'worker': 'Device worker could not complete.',
}


def failure_reason(stage, error=None):
    """Classify only approved types, never exception messages or class names.

    Explicit causes preserve authentication/timeouts wrapped by shared transport.
    Ignore implicit context, which can describe an unrelated earlier failure.
    """
    chain = []
    while error is not None and all(error is not item for item in chain):
        chain.append(error)
        error = error.__cause__
    mappings = (
        (MissingEnableSecret, 'Enable secret is required for privileged EXEC.'),
        (EnableAuthenticationFailed, 'Enable authentication failed.'),
        (ConnectionRetryExhausted, 'Transient connection failure after two attempts.'),
        (ConnectionCleanupError, 'Connection cleanup failed; retry suppressed.'),
        (AuthenticationException, 'Authentication failed.'),
        (TimeoutError, 'Operation timed out.'),
        (UnsupportedConfigurationPlatform, 'Configuration capture is unsupported for the resolved platform.'),
        (EmptyConfigurationCapture, 'Configuration command returned empty output.'),
        (ConfigurationCommandRejected, 'Configuration command was rejected by the device.'),
        (TransportConfigurationError, 'Transport settings are invalid or incomplete.'),
        (UnsupportedPlatformError, 'Transport is unsupported on this operating system.'),
        (TunnelError, 'Transport tunnel could not be established.'),
        (TeleportError, 'Teleport transport could not be established.'),
        (DeviceConnectionError, 'Device connection failed.'),
        (ConnectionError, 'Network connection failed.'),
        (SSHException, 'SSH transport failed.'),
        (TransportError, 'Device transport failed.'),
        (InteractiveCLIError, 'CLI setup or command exchange failed.'),
    )
    for exception_type, reason in mappings:
        if any(isinstance(item, exception_type) for item in chain):
            return reason
    if stage == 'write':
        if isinstance(chain[0] if chain else None, PermissionError):
            return 'Permission denied while writing the configuration file.'
        if isinstance(chain[0] if chain else None, OSError):
            return 'Filesystem error while writing the configuration file.'
    return FAILURE_REASONS[stage]


def filename_component(value):
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f\x7f]', '_', value).strip().rstrip('. ')
    value = value[:90].rstrip('. ') or 'unknown'
    if re.match(r'^(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)', value, re.I):
        value = '_' + value
    return value


class BackupWriter:
    """Own protected capture allocation; exact_directory supports an owning run.

    Default allocation retains the standalone dated-run layout. Exclusive file
    creation and synchronized naming protect existing captures in either mode.
    """
    def __init__(self, root, started, *, exact_directory=False):
        root = Path(root)
        root.mkdir(mode=0o700 if exact_directory else 0o777, parents=True, exist_ok=True)
        self.path = root if exact_directory else root / (started.strftime('%Y%m%dT%H%M%S_%fZ') + '_' + uuid4().hex)
        self.path.mkdir(mode=0o700, exist_ok=exact_directory)
        # A custom root inside a repository must also ignore sensitive captures.
        (self.path / '.gitignore').write_text('*\n', encoding='utf-8')
        self._lock = Lock()
        self._names = set()

    def write(self, hostname, platform, content):
        stem = filename_component(hostname) + '-' + filename_component(platform)
        with self._lock:
            number = 1
            while True:
                suffix = '' if number == 1 else f'-{number}'
                name = stem + suffix + '.txt'
                number += 1
                if name.casefold() in self._names:
                    continue
                path = self.path / name
                try:
                    stream = path.open('x', encoding='utf-8', newline='')
                except FileExistsError:
                    continue
                self._names.add(name.casefold())
                break
        try:
            with stream:
                stream.write(content)
        except BaseException:
            path.unlink(missing_ok=True)
            raise
        return path


def run_backup(targets, transport_config, *, inventory_path='data/inventory/inventory.json',
               backups_dir='outputs/backups/configuration', log_root='outputs/logs', output=None, clock=None,
               execution_config=None, timeout=60.0):
    """Consume shared list/Excel targets with bounded, isolated device workers.

    Only safe failure metadata returns from workers. Configuration is written while
    owned by its device worker, never in a result spool or a full-run result set.
    Device type in filenames is the resolved OrbitFlow platform identifier.
    """
    targets = list(targets)
    secrets = {value for target in targets for key, value in target.items()
               if key in {'username', 'password', 'secret', 'token', 'otp', 'private_key'}
               and isinstance(value, str) and value}
    pattern = re.compile('|'.join(re.escape(v) for v in sorted(secrets, key=lambda v: (-len(v), v)))) if secrets else None
    capture_secrets = {target.get(key) for target in targets for key in ('password', 'secret')
                       if isinstance(target.get(key), str) and target[key]}
    capture_pattern = re.compile('|'.join(re.escape(v) for v in sorted(capture_secrets, key=lambda v: (-len(v), v)))) if capture_secrets else None
    def clean(value):
        text = sanitize_text(value)
        return pattern.sub('[REDACTED]', text) if pattern else text

    writer = BackupWriter(backups_dir, (clock or (lambda: datetime.now(timezone.utc)))())
    from orbitflow.terminal_progress import location
    location('Backup folder (capture pending)', clean(str(writer.path)))
    store = JsonInventoryStore(inventory_path)
    status = Progress(output if output is not None else sys.stdout)
    completed = failed = 0
    # This private nested processing run needs the shared collision-safe short
    # name on Windows; capture/report paths and the backup run name stay stable.
    spool = ResultSpool.create(writer.path / '.processing', 'configuration_backup', len(targets),
                               clean=clean, short_name=True)

    def failure_row(target, context, stage, error=None):
        values = (context.hostname if context else '',
                  context.management_ip if context else target.get('management_ip', ''),
                  (context.hardware_model or context.device_family) if context else '',
                  context.platform if context else '', stage, failure_reason(stage, error))
        return tuple(ILLEGAL_CHARACTERS_RE.sub('', clean(value or '')) for value in values)

    with module_logger('backup', 'configuration_backup', log_root=log_root) as (logger, _):
        logger.info('Configuration backup started')
        status(f'Configuration backup started: {len(targets)} devices')
        def capture(target):
            from orbitflow.terminal_progress import worker_stage
            stage = 'input'
            worker_stage(stage)
            context = None
            try:
                if not all(isinstance(target.get(field), str) and target[field].strip() for field in REQUIRED_COLUMNS):
                    raise ValueError('Missing required target field')
                ip_address(target['management_ip'])
                stage = 'connect'
                worker_stage(stage)
                with connect_device(target['management_ip'], DeviceCredentials(target['username'], target['password'], secret=target.get('secret')), transport_config) as session:
                    stage = 'inventory'
                    worker_stage(stage)
                    with DeviceCLI(session) as cli:
                        context = DeviceInventoryResolver(store, sanitize_fact=clean).resolve(
                            session, management_ip=target['management_ip'], cli=cli)
                        stage = 'capture'
                        worker_stage(stage)
                        content = ConfigurationService(timeout=timeout).collect(session, context, cli=cli)
                    stage = 'disconnect'
                stage = 'write'
                worker_stage(stage)
                # Captures retain configuration, but never supplied login/enable
                # credentials, even if a device echoes them into the response.
                if capture_pattern:
                    content = capture_pattern.sub('[REDACTED]', content)
                writer.write(clean(context.hostname), context.platform, content)
                return None
            except Exception as exc:
                return failure_row(target, context, stage, exc)

        def record(outcome):
            nonlocal completed, failed
            completed += 1
            row = (failure_row(targets[outcome.position - 1], None, 'worker')
                   if outcome.error_category else outcome.value)
            spool.append(outcome, payload=dict(failure=list(row) if row else None),
                         target=clean(targets[outcome.position - 1].get('management_ip', '')), failed=bool(row))
            category = row[4] + '_failed' if row else ''
            if row:
                category = {
                    'Enable secret is required for privileged EXEC.': 'enable_secret_missing',
                    'Enable authentication failed.': 'enable_authentication_failed',
                    'Transient connection failure after two attempts.': 'connection_retry_exhausted',
                    'Connection cleanup failed; retry suppressed.': 'connection_cleanup_failed',
                }.get(row[-1], category)
            if category:
                failed += 1
                logger.error(f'Configuration backup target {outcome.position} failed', extra={'error_category': category})
            else:
                logger.info(f'Configuration backup target {outcome.position} saved')
            from orbitflow.terminal_progress import current_display
            display = current_display.get()
            if display is not None:
                display.outcome(outcome.position, bool(category))
            status(f'[{outcome.position}/{len(targets)}]: ' + (f'failed ({category})' if category else 'saved'))

        with spool.collection():
            execute_devices(targets, capture, config=execution_config, on_outcome=record)
        recover_failed_devices(spool.path, writer.path / 'failed_devices.xlsx')
        logger.info('Configuration backup completed')
    status(f'Devices: {completed}; saved: {completed - failed}; failed: {failed}; folder: {clean(str(writer.path))}')
    return writer.path


def recover_failed_devices(run_path, output):
    """Read-only export of retained safe backup failures; never recapture devices.

    run_path is a configuration_backup ResultSpool directory in the backup run's
    .processing folder. output is the exact destination XLSX path. Atomic replace
    preserves an existing report on export failure; complete outcomes are required.
    """
    spool = ResultSpool(run_path)
    if spool.manifest.get('task') != 'configuration_backup':
        raise ValueError('Wrong backup result task')
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    def export(source):
        workbook = Workbook(write_only=True)
        sheet = workbook.create_sheet('Failed Devices')
        sheet.append(FAILURE_COLUMNS)
        temporary = None
        try:
            for record in source.records():
                row = record['payload']['failure']
                if row is not None:
                    cells = []
                    for value in row:
                        cell = WriteOnlyCell(sheet, value=value)
                        cell.data_type = 's'
                        cells.append(cell)
                    sheet.append(cells)
            with NamedTemporaryFile(suffix='.xlsx', dir=output.parent, delete=False) as stream:
                temporary = Path(stream.name)
                workbook.save(stream)
            temporary.replace(output)
            return output
        finally:
            if not sheet.closed:
                sheet.close()
            workbook.close()
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    return spool.consume(export, cleanup=False)
