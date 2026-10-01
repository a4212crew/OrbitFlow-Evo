"""Capture sensitive running-configuration backups from approved Excel targets."""

import argparse
from pathlib import Path

from orbitflow.config import load_execution_config
from orbitflow.configuration_backup import run_backup
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
    parser.add_argument("--backups-dir", type=Path, default=Path("backups"))
    parser.add_argument("--log-root", type=Path, default=Path("logs"))
    parser.add_argument("--config", type=Path, default=Path("orbitflow.toml"))
    parser.add_argument("--timeout", type=float, default=60.0, help="Configuration command timeout in seconds")
    args = parser.parse_args(argv)
    config = TransportConfig(
        proxy=args.proxy, cluster=args.cluster,
        bastion_host=args.bastion_host, bastion_user=args.bastion_user,
        teleport_key_path=args.teleport_key_path, teleport_cert_path=args.teleport_cert_path,
    )
    return run_backup(
        load_targets(args.excel_path, isolate_invalid=True), config,
        execution_config=load_execution_config(args.config), timeout=args.timeout,
        inventory_path=args.inventory_path, backups_dir=args.backups_dir, log_root=args.log_root,
    )


if __name__ == "__main__":
    main()
