"""Run read-only VLAN compliance or regenerate Excel from a retained result spool."""

import argparse
from pathlib import Path

from orbitflow.compliance import JsonPolicyProvider
from orbitflow.compliance_report import export_compliance_spool
from orbitflow.config import load_execution_config
from orbitflow.logging import log_run_failure
from orbitflow.targets import load_targets
from orbitflow.transport import TransportConfig
from orbitflow.vlan_compliance import DEFAULT_POLICY, run_compliance


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="Collect once and evaluate both rule families")
    run.add_argument("excel_path", type=Path)
    for option in ("proxy", "cluster", "bastion-host", "bastion-user"):
        run.add_argument(f"--{option}", required=True)
    for option in ("teleport-key-path", "teleport-cert-path"):
        run.add_argument(f"--{option}", type=Path)
    for option, default in (("policy", DEFAULT_POLICY), ("config", "orbitflow.toml"),
                            ("inventory-path", "data/inventory/inventory.json"),
                            ("reports-dir", "outputs/reports/vlan_compliance"),
                            ("spool-root", "outputs/runs/vlan_compliance"), ("log-root", "outputs/logs")):
        run.add_argument(f"--{option}", type=Path, default=Path(default))
    run.add_argument("--keep-spool", action="store_true")
    export = commands.add_parser("export", help="Recover a report without device connections")
    export.add_argument("spool_path", type=Path)
    export.add_argument("output_path", type=Path)
    export.add_argument("--log-root", type=Path, default=Path("outputs/logs"))
    export.add_argument("--keep-spool", action="store_true")
    export.add_argument("--allow-partial", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "export":
            path = export_compliance_spool(args.spool_path, args.output_path,
                                          cleanup=not args.keep_spool, allow_partial=args.allow_partial)
        else:
            config = TransportConfig(proxy=args.proxy, cluster=args.cluster,
                                     bastion_host=args.bastion_host, bastion_user=args.bastion_user,
                                     teleport_key_path=args.teleport_key_path,
                                     teleport_cert_path=args.teleport_cert_path)
            path = run_compliance(load_targets(args.excel_path, isolate_invalid=True), config,
                                  policy_provider=JsonPolicyProvider(args.policy),
                                  inventory_path=args.inventory_path, reports_dir=args.reports_dir,
                                  spool_root=args.spool_root, log_root=args.log_root,
                                  execution_config=load_execution_config(args.config), cleanup=not args.keep_spool)
    except Exception as exc:
        if not log_run_failure(exc, log_root=args.log_root):
            print("Run-level diagnostics could not be written.", flush=True)
        raise SystemExit("VLAN compliance failed. Check policy/input paths, application/compliance logs, "
                         "and the retained run spool; export can retry without device connections.") from None
    print("Compliance workbook saved. Review Findings and Run_Errors.", flush=True)
    return path


if __name__ == "__main__":
    main()
