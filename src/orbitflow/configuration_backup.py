"""Read-only configuration backup; sensitive content never enters outcomes/logs."""
from datetime import datetime, timezone
from pathlib import Path
from ipaddress import ip_address
import re
import sys
from threading import Lock
from uuid import uuid4

from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE

from orbitflow.capabilities.configuration import ConfigurationService
from orbitflow.execution import execute_devices, Progress
from orbitflow.inventory import DeviceInventoryResolver, JsonInventoryStore
from orbitflow.logging import module_logger, sanitize_text
from orbitflow.targets import REQUIRED_COLUMNS
from orbitflow.transport import DeviceCredentials, connect_device
from orbitflow.vendors.common import DeviceCLI


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


def filename_component(value):
    value = re.sub(r'[<>:"/\\|?*\x00-\x1f\x7f]', '_', value).strip().rstrip('. ')
    value = value[:90].rstrip('. ') or 'unknown'
    if re.match(r'^(?:CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\.|$)', value, re.I):
        value = '_' + value
    return value


class BackupWriter:
    """Own filename allocation; exclusive creation also protects existing files."""
    def __init__(self, root, started):
        root = Path(root)
        root.mkdir(parents=True, exist_ok=True)
        self.path = root / (started.strftime('%Y%m%dT%H%M%S_%fZ') + '_' + uuid4().hex)
        self.path.mkdir(mode=0o700)
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


def run_backup(targets, transport_config, *, inventory_path='data/live_validation/inventory.json',
               backups_dir='backups', log_root='logs', output=None, clock=None,
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
    def clean(value):
        text = sanitize_text(value)
        return pattern.sub('[REDACTED]', text) if pattern else text

    writer = BackupWriter(backups_dir, (clock or (lambda: datetime.now(timezone.utc)))())
    store = JsonInventoryStore(inventory_path)
    status = Progress(output if output is not None else sys.stdout)
    completed = failed = 0
    workbook = Workbook(write_only=True)
    sheet = workbook.create_sheet('Failed Devices')
    sheet.append(FAILURE_COLUMNS)

    def failure_row(target, context, stage):
        values = (context.hostname if context else '',
                  context.management_ip if context else target.get('management_ip', ''),
                  (context.hardware_model or context.device_family) if context else '',
                  context.platform if context else '', stage, FAILURE_REASONS[stage])
        return tuple(ILLEGAL_CHARACTERS_RE.sub('', clean(value or '')) for value in values)

    with module_logger('backup', 'configuration_backup', log_root=log_root) as (logger, _):
        logger.info('Configuration backup started')
        status(f'Configuration backup started: {len(targets)} devices')
        def capture(target):
            stage = 'input'
            context = None
            try:
                if not all(isinstance(target.get(field), str) and target[field].strip() for field in REQUIRED_COLUMNS):
                    raise ValueError('Missing required target field')
                ip_address(target['management_ip'])
                stage = 'connect'
                with connect_device(target['management_ip'], DeviceCredentials(target['username'], target['password']), transport_config) as session:
                    stage = 'inventory'
                    with DeviceCLI(session) as cli:
                        context = DeviceInventoryResolver(store, sanitize_fact=clean).resolve(
                            session, management_ip=target['management_ip'], cli=cli)
                        stage = 'capture'
                        content = ConfigurationService(timeout=timeout).collect(session, context, cli=cli)
                    stage = 'disconnect'
                stage = 'write'
                writer.write(clean(context.hostname), context.platform, content)
                return None
            except Exception:
                # Fixed stage categories cannot echo exception text or dynamically
                # constructed exception class names containing sensitive content.
                return failure_row(target, context, stage)

        def record(outcome):
            nonlocal completed, failed
            completed += 1
            row = (failure_row(targets[outcome.position - 1], None, 'worker')
                   if outcome.error_category else outcome.value)
            category = row[4] + '_failed' if row else ''
            if category:
                failed += 1
                cells = []
                for value in row:
                    cell = WriteOnlyCell(sheet, value=value)
                    cell.data_type = 's'
                    cells.append(cell)
                sheet.append(cells)
                logger.error(f'Configuration backup target {outcome.position} failed', extra={'error_category': category})
            else:
                logger.info(f'Configuration backup target {outcome.position} saved')
            status(f'[{outcome.position}/{len(targets)}]: ' + (f'failed ({category})' if category else 'saved'))

        try:
            execute_devices(targets, capture, config=execution_config, on_outcome=record)
            workbook.save(writer.path / 'failed_devices.xlsx')
        finally:
            if not sheet.closed:
                sheet.close()
            workbook.close()
        logger.info('Configuration backup completed')
    status(f'Devices: {completed}; saved: {completed - failed}; failed: {failed}; folder: {clean(str(writer.path))}')
    return writer.path
