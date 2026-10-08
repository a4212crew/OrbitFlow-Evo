"""Generate a read-only Interface/VLAN workbook from approved Excel targets."""

import argparse
from pathlib import Path

from orbitflow.config import load_execution_config
from orbitflow.logging import log_run_failure
from orbitflow.reporting import run_report
from orbitflow.targets import load_targets
from orbitflow.transport import TransportConfig


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("excel_path")
    for option in ("proxy", "cluster", "bastion-host", "bastion-user"):
        parser.add_argument(f"--{option}", required=True)
    parser.add_argument("--teleport-key-path", type=Path)
    parser.add_argument("--teleport-cert-path", type=Path)
    parser.add_argument("--inventory-path", type=Path, default=Path("data/inventory/inventory.json"))
    parser.add_argument("--reports-dir", type=Path, default=Path("outputs/reports/interface_vlan"))
    parser.add_argument("--log-root", type=Path, default=Path("outputs/logs"))
    parser.add_argument("--spool-root", type=Path, default=Path("outputs/runs/interface_vlan_report"))
    parser.add_argument("--config", type=Path, default=Path("orbitflow.toml"))
    args = parser.parse_args(argv)
    try:
        config = TransportConfig(
            proxy=args.proxy, cluster=args.cluster,
            bastion_host=args.bastion_host, bastion_user=args.bastion_user,
            teleport_key_path=args.teleport_key_path, teleport_cert_path=args.teleport_cert_path,
        )
        return run_report(
            load_targets(args.excel_path, isolate_invalid=True), config,
            execution_config=load_execution_config(args.config),
            spool_root=args.spool_root,
            inventory_path=args.inventory_path, reports_dir=args.reports_dir, log_root=args.log_root,
        )
    except Exception as exc:
        if not log_run_failure(exc, log_root=args.log_root):
            print("Run-level diagnostics could not be written.", flush=True)
        raise SystemExit("Interface/VLAN report failed. Check application logs and retained run spool.") from None


if __name__ == "__main__":
    main()
