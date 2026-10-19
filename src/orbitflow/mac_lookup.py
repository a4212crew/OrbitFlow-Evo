"""Read-only MAC application, bounded batch reporting and offline recovery."""
from datetime import datetime, timezone
from ipaddress import ip_address
from pathlib import Path
import re
from uuid import uuid4

from orbitflow.capabilities.mac import MacService, normalize_mac, display_interface
from orbitflow.capabilities.bridge_domains import BridgeDomainService
from orbitflow.capabilities.mac_forwarding import enrich
from orbitflow.capabilities.interfaces import InterfaceService
from orbitflow.capabilities.vlans import VlanService
from orbitflow.execution import execute_devices
from orbitflow.result_spool import ResultSpool
from orbitflow.excel_output import write_tables
from orbitflow.inventory import DeviceInventoryResolver, JsonInventoryStore
from orbitflow.logging import module_logger, sanitize_text
from orbitflow.transport import connect_device, DeviceCredentials
from orbitflow.vendors.common import DeviceCLI

MAIN_COLUMNS = ('Device IP', 'Device Name', 'Equipment Type', 'Physical Interface name', 'Port Type', 'Mac address', 'Interface Description')
DETAIL_COLUMNS = ('Observation', 'Device IP', 'MAC', 'Observed Attachment', 'Domain', 'VLANs', 'Original Type', 'Normalized Type', 'Scope', 'Destination Detail', 'Mapping', 'Classification', 'Forwarding Semantics', 'Physical Interface', 'Port Type', 'Selected Device Row', 'Source', 'Raw Attachment')


class TargetResolutionError(ValueError):
    """Fixed safe diagnostic for exact target selection before any connection."""


def validate_vlan(value):
    if isinstance(value, bool) or not str(value).isdecimal() or not 1 <= int(value) <= 4094:
        raise ValueError('VLAN must be 1-4094')
    return int(value)


def resolve_target(targets, address):
    """Exactly one workbook row, using canonical IP equality; never estate fallback."""
    address = ip_address(address)
    matches = []
    for target in targets:
        try:
            if ip_address(target.get('management_ip', '')) == address:
                matches.append(target)
        except ValueError:
            continue
    if not matches:
        raise TargetResolutionError('Requested IP missing from device workbook')
    if len(matches) != 1:
        raise TargetResolutionError('Requested IP is ambiguous in device workbook')
    if not matches[0].get('username') or not matches[0].get('password'):
        raise TargetResolutionError('Requested IP has missing credentials')
    return matches[0]


def collect_device(target, transport_config, store, *, mac=None, vlan=None, xr_location='0/RP0/CPU0'):
    """One connection; optional enrichment failures retain usable MAC observations."""
    if mac is not None:
        mac = normalize_mac(mac)
    if vlan is not None:
        vlan = validate_vlan(vlan)
    MacService(xr_location=xr_location)
    ip = str(ip_address(target['management_ip']))
    errors = []
    with connect_device(ip, DeviceCredentials(target['username'], target['password'], secret=target.get('secret')), transport_config) as session:
        with DeviceCLI(session) as cli:
            context = DeviceInventoryResolver(store).resolve(session, management_ip=ip, cli=cli)
            snapshot = MacService(xr_location=xr_location).collect(session, context, cli=cli)
            interfaces, vlans, bridges = (), None, None
            for stage, service in [('interfaces', InterfaceService()), ('vlans', VlanService()),
                                   *([('bridges', BridgeDomainService())] if context.platform == 'cisco_xr' else [])]:
                try:
                    value = service.collect(session, context, cli=cli)
                    if stage == 'interfaces':
                        interfaces = value
                    elif stage == 'vlans':
                        vlans = value
                    else:
                        bridges = value
                except Exception as exc:
                    errors.append([ip, stage, type(exc).__name__])
    try:
        observations = enrich(snapshot, context, interfaces, vlans, bridges)
    except Exception as exc:
        errors.append([ip, 'mapping', type(exc).__name__])
        observations = enrich(snapshot, context)
    main, details, selected = [], [], 0
    for position, item in enumerate(observations, 1):
        entry, resolution = item.entry, item.resolution
        matches = (mac is None or entry.mac == mac) and (vlan is None or vlan in item.vlans)
        # Supporting sheet includes unselected/unmapped evidence, never as matches.
        details.append([f'{ip}/{position}', ip, entry.mac, display_interface(context.platform, entry.attachment), '; '.join(item.domains),
                        ', '.join(map(str, item.vlans)), entry.original_type, entry.kind, entry.scope,
                        entry.ifindex, item.mapping + ('; selected' if matches else '; not selected'),
                        resolution.classification, resolution.semantics, resolution.physical, resolution.port_type,
                        selected + 1 if matches else '', snapshot.source, entry.attachment])
        if matches:
            selected += 1
            main.append([ip, context.hostname, context.hardware_model or context.device_family, resolution.physical,
                         resolution.port_type, entry.mac, item.description])
    totals = [[ip, 'table', snapshot.total], [ip, 'selection', selected]]
    totals.extend([ip, scope, count] for scope, count in snapshot.scoped_totals)
    bridge_rows = []
    if bridges is not None:
        for domain in bridges.domains:
            for attachment in domain.attachments or (None,):
                if attachment is None:
                    from orbitflow.capabilities.bridge_domains import BridgeAttachment
                    attachment = BridgeAttachment()
                bridge_rows.append([ip, domain.group, domain.name, domain.internal_id, domain.state,
                                    attachment.interface, attachment.neighbor, attachment.pw_id, attachment.state,
                                    attachment.backup, attachment.static_count if attachment.static_count is not None else '',
                                    attachment.bvi_count if attachment.bvi_count is not None else '',
                                    '; '.join(f'{k}: {v}' for k, v in domain.counts), 'show l2vpn bridge-domain'])
    return [main, details, totals, errors, bridge_rows]


def run_lookup(targets, transport_config, *, mac=None, vlan=None, inventory_path='data/inventory/inventory.json',
               reports_dir='outputs/reports/mac_table', spool_root='outputs/runs/mac_table',
               log_root='outputs/logs', execution_config=None, xr_location='0/RP0/CPU0'):
    """Persist bounded per-device outcomes and produce one seven-column workbook."""
    if mac is not None:
        mac = normalize_mac(mac)
    if vlan is not None:
        vlan = validate_vlan(vlan)
    MacService(xr_location=xr_location)  # Validate command parameter before connecting.
    targets = list(targets)
    secrets = {str(t[k]) for t in targets for k in ('username', 'password', 'secret') if t.get(k)}
    pattern = re.compile('|'.join(re.escape(s) for s in sorted(secrets, key=lambda s: (-len(s), s)))) if secrets else None
    def clean(value):
        value = sanitize_text(value)
        return pattern.sub('[REDACTED]', value) if pattern else value
    spool = ResultSpool.create(spool_root, 'mac_table', len(targets), clean=clean)
    store = JsonInventoryStore(inventory_path)
    path = Path(reports_dir) / f'mac_table_{datetime.now(timezone.utc):%Y%m%dT%H%M%S}_{uuid4().hex}.xlsx'
    with module_logger('mac_table', 'mac_table', log_root=log_root) as (logger, _):
        def worker(item):
            _, target = item
            return collect_device(target, transport_config, store, mac=mac, vlan=vlan, xr_location=xr_location)
        def persist(outcome):
            ip = targets[outcome.position - 1].get('management_ip', '')
            payload = outcome.value if not outcome.error_category else [[], [], [], [[ip, 'collection', outcome.error_category]]]
            for detail in payload[1]:
                detail[0] = f'{outcome.position}/{detail[0]}'
            spool.append(outcome, payload=payload, target=ip, failed=bool(payload[3]))
            logger.info('MAC device outcome', extra={'management_ip': clean(ip), 'error_category': 'partial_or_failed' if payload[3] else ''})
        with spool.collection():
            execute_devices(enumerate(targets, 1), worker, config=execution_config, on_outcome=persist)
        export_mac_spool(spool.path, path)
    return path


def export_mac_spool(spool_path, path, *, allow_partial=False):
    """Offline regeneration; retain normalized spool after successful export."""
    spool = ResultSpool(spool_path)
    if spool.manifest['task'] != 'mac_table':
        raise ValueError('Not a MAC table spool')
    def consume(run):
        def rows(index):
            for record in run.records():
                if len(record['payload']) > index:
                    for row in record['payload'][index]:
                        yield [*row, ''] if index == 0 and len(row) == 6 else row
        write_tables(path, [('MAC Addresses', MAIN_COLUMNS, rows(0)), ('Details', DETAIL_COLUMNS, rows(1)),
                            ('Totals', ('Device IP', 'Scope', 'Total'), rows(2)),
                            ('Run Errors', ('Device IP', 'Stage', 'Error Category'), rows(3)),
                            ('Bridge Domains', ('Device IP', 'Group', 'Domain', 'Internal ID', 'Domain State', 'Interface',
                                                'Neighbor', 'PW ID', 'Attachment State', 'Backup', 'Static MAC Count', 'BVI MAC Count', 'Scoped Counts', 'Source'), rows(4))])
        return Path(path)
    return spool.consume(consume, cleanup=False, allow_partial=allow_partial)
