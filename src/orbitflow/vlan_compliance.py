"""Application workflow: observe once per device, analyze, spool, then export."""

from dataclasses import dataclass
from pathlib import Path
import re
import sys

from orbitflow.capabilities.interfaces import InterfaceService
from orbitflow.capabilities.vlans import VlanService
from orbitflow.compliance import JsonPolicyProvider, evaluate_vlan_compliance
from orbitflow.compliance.vlan import safe_data
from orbitflow.execution import execute_devices, Progress
from orbitflow.inventory import DeviceInventoryResolver, JsonInventoryStore
from orbitflow.logging import module_logger, sanitize_text
from orbitflow.result_spool import ResultSpool
from orbitflow.targets import REQUIRED_COLUMNS
from orbitflow.transport import DeviceCredentials, connect_device
from orbitflow.vendors.common import DeviceCLI


DEFAULT_POLICY = Path(__file__).resolve().parents[2] / "policies/vlan_compliance.json"


@dataclass(frozen=True)
class ComplianceRun:
    spool_path: Path
    device_count: int
    failed_devices: int
    finding_counts: dict[str, int]


def collect_compliance(targets, transport_config, *, policy_provider=None,
                       inventory_path="data/inventory/inventory.json",
                       spool_root="outputs/runs/vlan_compliance", log_root="outputs/logs",
                       execution_config=None, output=None):
    """Return a recoverable JSON result handle, independent of Excel or any UI.

    A provider is loaded once before connecting. One worker owns each target's
    context, session and CLI. Only the executor completion sink writes the spool.
    """
    policy = (policy_provider or JsonPolicyProvider(DEFAULT_POLICY)).load()
    targets = list(targets)
    secrets = {value for target in targets for key, value in target.items()
               if key in {"username", "password", "secret", "token", "otp", "private_key"}
               and isinstance(value, str) and value}
    pattern = re.compile("|".join(re.escape(v) for v in sorted(secrets, key=lambda v: (-len(v), v)))) if secrets else None

    def clean(value):
        text = sanitize_text(value)
        return pattern.sub("[REDACTED]", text) if pattern else text

    status = Progress(output if output is not None else sys.stdout)
    spool = ResultSpool.create(spool_root, "vlan_compliance", len(targets), clean=clean)
    store = JsonInventoryStore(inventory_path)
    counts = dict.fromkeys(("compliant", "non_compliant", "not_applicable", "unable_to_assess"), 0)
    failed_devices = 0
    with module_logger("compliance", "vlan_compliance", log_root=log_root) as (logger, _):
        status(f"VLAN compliance: {len(targets)} devices; spool: {clean(str(spool.path))}")
        logger.info("VLAN compliance collection started")

        def collect(item):
            position, target = item
            ip = target.get("management_ip", "")
            context, interfaces, vlans = None, None, None
            errors = []
            stage = "input"

            def failure(stage, exc):
                errors.append({"management_ip": ip, "stage": stage,
                               "error_category": type(exc).__name__})
                logger.error("Compliance collection stage failed", exc_info=exc,
                             extra={"management_ip": clean(ip), "error_category": type(exc).__name__})
                status(f"[{position}/{len(targets)}]: {stage} failed ({clean(type(exc).__name__)})")

            try:
                if not all(isinstance(target.get(k), str) and target[k].strip() for k in REQUIRED_COLUMNS):
                    raise ValueError("Missing target fields")
                stage = "connect"
                status(f"[{position}/{len(targets)}]: connecting")
                with connect_device(ip, DeviceCredentials(target["username"], target["password"],
                                                         secret=target.get("secret")), transport_config) as session:
                    stage = "inventory"
                    with DeviceCLI(session) as cli:
                        context = DeviceInventoryResolver(store).resolve(session, management_ip=ip, cli=cli)
                        for stage, service in (("interfaces", InterfaceService()), ("vlans", VlanService())):
                            try:
                                result = service.collect(session, context, cli=cli)
                                if stage == "interfaces":
                                    interfaces = result
                                else:
                                    vlans = result
                            except Exception as exc:
                                failure(stage, exc)
                        stage = "disconnect"
            except Exception as exc:
                failure(stage, exc)
            findings = evaluate_vlan_compliance(context, interfaces, vlans, policy,
                                                management_ip=ip, clean=clean)
            status(f"[{position}/{len(targets)}]: evaluated")
            return {"schema_version": 1, "policy_id": policy.policy_id,
                    "findings": findings, "errors": safe_data(errors, clean)}

        def persist(outcome):
            nonlocal failed_devices
            target = targets[outcome.position - 1]
            ip = target.get("management_ip", "")
            if outcome.error_category:
                payload = {"schema_version": 1, "policy_id": policy.policy_id,
                           "findings": evaluate_vlan_compliance(None, None, None, policy,
                                                                 management_ip=ip, clean=clean),
                           "errors": [{"management_ip": ip, "stage": "worker",
                                       "error_category": outcome.error_category}]}
            else:
                payload = outcome.value
            failed = bool(payload["errors"])
            failed_devices += failed
            for finding in payload["findings"]:
                counts[finding["status"]] += 1
            spool.append(outcome, payload=payload, target=ip, failed=failed)

        with spool.collection():
            execute_devices(enumerate(targets, 1), collect, config=execution_config, on_outcome=persist)
        logger.info("VLAN compliance collection completed")
    status(f"VLAN compliance: {len(targets)} devices; {failed_devices} device errors; "
           f"{counts['non_compliant']} non-compliant; {counts['unable_to_assess']} unable to assess")
    return ComplianceRun(spool.path, len(targets), failed_devices, counts)


def run_compliance(targets, transport_config, *, reports_dir="outputs/reports/vlan_compliance",
                   cleanup=True, **kwargs):
    """CLI convenience composition. API consumers may call collect_compliance alone."""
    from orbitflow.compliance_report import export_compliance_spool

    run = collect_compliance(targets, transport_config, **kwargs)
    path = Path(reports_dir) / f"vlan_compliance_{run.spool_path.name}.xlsx"
    export_compliance_spool(run.spool_path, path, cleanup=cleanup)
    return path
