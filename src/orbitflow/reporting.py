"""Read-only batch Interface/VLAN reporting over shared device capabilities."""

from datetime import datetime, timezone
from pathlib import Path
import re
import sys

from openpyxl import Workbook
from openpyxl.cell import WriteOnlyCell
from openpyxl.cell.cell import ILLEGAL_CHARACTERS_RE
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

from orbitflow.capabilities.interfaces import InterfaceService
from orbitflow.capabilities.vlans import VlanService
from orbitflow.execution import execute_devices, Progress
from orbitflow.result_spool import ResultSpool
from orbitflow.inventory import DeviceInventoryResolver, JsonInventoryStore
from orbitflow.logging import module_logger, sanitize_text
from orbitflow.targets import REQUIRED_COLUMNS
from orbitflow.transport import DeviceCredentials, connect_device
from orbitflow.vendors.common import DeviceCLI
from orbitflow.vendors.interface_names import canonical_interface_name

INTERFACE_COLUMNS = (
    "Device Name", "Device IP", "Platform", "Device Family", "Interface",
    "Description", "Admin Status", "Oper Status", "Port Type", "Untagged VLAN",
    "Tagged VLANs", "Bridge Domains", "Service Mappings", "Collection Time",
)
DATABASE_COLUMNS = (
    "Device Name", "Device IP", "Platform", "Object Type", "Object ID",
    "Domain ID", "Name", "Collection Time",
)
ERROR_COLUMNS = ("Device IP", "Device Name", "Stage", "Error Category", "Time")


def build_rows(context, interfaces, vlans):
    """Present normalized capability facts for actual InterfaceService identities."""
    key = lambda name: canonical_interface_name(context.platform, name)
    records = {key(record.port_name): record for record in interfaces}
    observations = {} if vlans is None else {
        key(item.interface_name): item for item in vlans.interfaces
    }
    rows = []
    identity = [context.hostname, context.management_ip, context.platform]
    for name, record in sorted(records.items()):
        item = observations.get(name)
        fields = []
        for field in ("port_type", "untagged_vlan", "tagged_vlans", "bridge_domains", "service_mappings"):
            value = getattr(item, field) if item else ""
            if isinstance(value, tuple):
                value = ("; " if field == "service_mappings" else ", ").join(map(str, value))
            fields.append(value)
        rows.append(identity + [context.device_family, record.port_name,
            record.port_description, record.admin_status, record.oper_status,
            *fields, record.collection_time.isoformat()])
    database = [] if vlans is None else [
        identity + [obj.object_type, obj.object_id, obj.domain_id, obj.name,
                    vlans.collection_time.isoformat()]
        for obj in sorted(vlans.objects, key=lambda obj: (obj.object_type, obj.object_id))
    ]
    return rows, database


def write_workbook(path, interfaces, database, errors, *, clean=sanitize_text):
    """Write once using bounded worksheet memory; untrusted values are literal text."""
    workbook = Workbook(write_only=True)
    path = Path(path)
    temporary = path.with_name(path.name + ".tmp")
    try:
        for title, columns, rows in (
            ("Interfaces", INTERFACE_COLUMNS, interfaces),
            ("VLAN_Database", DATABASE_COLUMNS, database),
            ("Run_Errors", ERROR_COLUMNS, errors),
        ):
            sheet = workbook.create_sheet(title)
            sheet.freeze_panes = "A2"

            for index, column in enumerate(columns, 1):
                sheet.column_dimensions[get_column_letter(index)].width = (
                    42 if column in {"Description", "Service Mappings", "Tagged VLANs", "Bridge Domains"}
                    else 28 if column in {"Collection Time", "Time", "Device Name", "Service Binding Name"}
                    else max(18, len(column) + 2)
                )
            for index, row in enumerate(_with_header(columns, rows)):
                cells = []
                for value in row:
                    text = ILLEGAL_CHARACTERS_RE.sub("", str(value) if index == 0 else clean(value))
                    if len(text) > 32767:
                        raise ValueError("Report cell exceeds Excel text limit")
                    cell = WriteOnlyCell(sheet, value=text)
                    cell.data_type = "s"
                    cell.alignment = Alignment(vertical="top", wrap_text=True)
                    if index == 0:
                        cell.font = Font(bold=True, color="FFFFFF")
                        cell.fill = PatternFill("solid", fgColor="24476A")
                    cells.append(cell)
                sheet.append(cells)
            sheet.auto_filter.ref = f"A1:{get_column_letter(len(columns))}{index + 1}"
        path.parent.mkdir(parents=True, exist_ok=True)
        workbook.save(temporary)
        temporary.replace(path)
    finally:
        for sheet in workbook:
            if not sheet.closed:
                sheet.close()
            if sheet._writer and Path(sheet._writer.out).exists():
                sheet._writer.cleanup()
        workbook.close()
        if temporary.exists():
            temporary.unlink()


def _with_header(columns, rows):
    yield columns
    yield from rows


def run_report(targets, transport_config, *, inventory_path="data/live_validation/inventory.json",
               reports_dir="reports", log_root="logs", output=None, clock=None,
               execution_config=None, spool_root=None):
    """Accept the approved list of target dictionaries; isolate failures by stage."""
    output = output if output is not None else sys.stdout
    clock = clock or (lambda: datetime.now(timezone.utc))
    targets = list(targets)
    # Redact known input credentials even if echoed into normalized device text.
    secrets = {value for target in targets for field, value in target.items()
               if field in {"username", "password", "secret", "token", "otp", "private_key"}
               and isinstance(value, str) and value}
    pattern = re.compile("|".join(re.escape(value) for value in sorted(secrets, key=lambda v: (-len(v), v)))) if secrets else None

    def clean(value):
        text = sanitize_text(value)
        return pattern.sub("[REDACTED]", text) if pattern else text

    status = Progress(output)

    started = clock()
    path = Path(reports_dir) / f"device_interface_vlan_report_{started.strftime('%Y%m%dT%H%M%S_%fZ')}.xlsx"
    spool = ResultSpool.create(spool_root or Path(reports_dir) / "runs",
                               "interface_vlan_report", len(targets), clean=clean)
    failure_count = 0
    store = JsonInventoryStore(inventory_path)
    with module_logger("reporting", "interface_vlan_report", log_root=log_root) as (logger, _):
        logger.info("Interface/VLAN batch started")
        status(f"Interface/VLAN batch started: {len(targets)} devices")

        def collect(item):
            position, target = item
            resolver = DeviceInventoryResolver(store)
            interface_service, vlan_service = InterfaceService(), VlanService()
            interface_rows, database_rows, errors = [], [], []
            def failure(ip, name, stage, exc):
                category = type(exc).__name__
                status(f"{label}: {stage} failed ({clean(category)})")
                errors.append([clean(ip), clean(name), stage, category, clock().isoformat()])
                logger.error(f"Report stage failed: {stage}",
                             exc_info=exc,
                             extra={"management_ip": clean(ip), "error_category": category})

            ip, name, stage = target.get("management_ip", ""), "", "input"
            # Escape control characters so a target cannot inject console lines.
            identity = clean(ip).encode("unicode_escape").decode("ascii")
            label = f"[{position}/{len(targets)}] {identity or '(missing target)'}"
            failures_before = len(errors)
            context, interfaces, vlans = None, [], None
            status(f"{label}: input")
            try:
                if not all(isinstance(target.get(field), str) and target[field].strip() for field in REQUIRED_COLUMNS):
                    raise ValueError("Missing required target field")
                stage = "connect"
                status(f"{label}: {stage}")
                with connect_device(ip, DeviceCredentials(target["username"], target["password"], secret=target.get("secret")), transport_config) as session:
                    stage = "inventory"
                    status(f"{label}: {stage}")
                    with DeviceCLI(session) as cli:
                        context = resolver.resolve(session, management_ip=ip, cli=cli)
                        name = context.hostname
                        for stage, service in (("interfaces", interface_service), ("vlans", vlan_service)):
                            status(f"{label}: {stage}")
                            try:
                                result = service.collect(session, context, cli=cli)
                                if stage == "interfaces":
                                    interfaces = result
                                else:
                                    vlans = result
                            except Exception as exc:
                                failure(ip, name, stage, exc)
                        stage = "disconnect"
                        status(f"{label}: {stage}")
            except Exception as exc:
                failure(ip, name, stage, exc)
            if context is not None:
                status(f"{label}: normalize")
                try:
                    rows, objects = build_rows(context, interfaces, vlans)
                    interface_rows.extend(rows)
                    database_rows.extend(objects)
                except Exception as exc:
                    failure(ip, name, "normalize", exc)
            count = len(errors) - failures_before
            status(f"{label}: completed" + (f" with {count} stage failure(s)" if count else ""))
            return interface_rows, database_rows, errors

        def persist(outcome):
            nonlocal failure_count
            target = targets[outcome.position - 1]
            if outcome.error_category:
                category = clean(outcome.error_category)
                logger.error("Report worker failed", extra={"error_category": category})
                payload = ([], [], [[target.get("management_ip", ""), "", "worker", category, clock().isoformat()]])
                status(f"[{outcome.position}/{len(targets)}]: worker failed ({category})")
            else:
                payload = outcome.value
            failure_count += len(payload[2])
            spool.append(outcome, payload=payload, target=target.get("management_ip", ""), failed=bool(payload[2]))

        status(f"Interface/VLAN batch spool: {clean(str(spool.path))}")
        with spool.collection():
            execute_devices(enumerate(targets, 1), collect, config=execution_config, on_outcome=persist)
        status("Interface/VLAN batch: workbook generation")
        try:
            export_report_spool(spool.path, path)
        except Exception as exc:
            status(f"Interface/VLAN batch: workbook generation failed ({clean(type(exc).__name__)})")
            logger.error("Report workbook write failed", exc_info=exc,
                         extra={"error_category": type(exc).__name__})
            raise
        logger.info("Interface/VLAN batch completed")
    status(f"Devices: {len(targets)}; stage failures: {failure_count}; report: {clean(str(path))}")
    return path


def export_report_spool(spool_path, path, *, cleanup=True, allow_partial=False):
    """Regenerate a workbook using persisted normalized data, with no connections."""
    spool = ResultSpool(spool_path)
    if spool.manifest['task'] != 'interface_vlan_report':
        raise ValueError('Not an Interface/VLAN report spool')
    def consume(run):
        def rows(index):
            for record in run.records():
                yield from record['payload'][index]
        write_workbook(path, rows(0), rows(1), rows(2))
        return Path(path)
    return spool.consume(consume, cleanup=cleanup, allow_partial=allow_partial)
