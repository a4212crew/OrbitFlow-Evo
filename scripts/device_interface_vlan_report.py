"""Generate a read-only Interface/VLAN workbook from approved Excel targets."""

import argparse
from pathlib import Path

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
    parser.add_argument("--inventory-path", type=Path, default=Path("data/live_validation/inventory.json"))
    parser.add_argument("--reports-dir", type=Path, default=Path("reports"))
    parser.add_argument("--log-root", type=Path, default=Path("logs"))
    args = parser.parse_args(argv)
    config = TransportConfig(
        proxy=args.proxy, cluster=args.cluster,
        bastion_host=args.bastion_host, bastion_user=args.bastion_user,
        teleport_key_path=args.teleport_key_path, teleport_cert_path=args.teleport_cert_path,
    )
    return run_report(
        load_targets(args.excel_path, isolate_invalid=True), config,
        inventory_path=args.inventory_path, reports_dir=args.reports_dir, log_root=args.log_root,
    )


if __name__ == "__main__":
    main()
