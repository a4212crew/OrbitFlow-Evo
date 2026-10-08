"""Refresh approved Excel targets and export the complete latest-known inventory."""

import argparse
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from orbitflow.config import load_execution_config
from orbitflow.logging import log_run_failure
from orbitflow.inventory_refresh import refresh_inventory_from_excel
from orbitflow.transport import TransportConfig


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("excel_path")
    for option in ("proxy", "cluster", "bastion-host", "bastion-user"):
        parser.add_argument(f"--{option}", required=True)
    parser.add_argument("--teleport-key-path", type=Path)
    parser.add_argument("--teleport-cert-path", type=Path)
    parser.add_argument("--inventory-path", type=Path, default=Path("data/inventory/inventory.json"))
    parser.add_argument("--reports-dir", type=Path, default=Path("outputs/reports/inventory"))
    parser.add_argument("--spool-root", type=Path, default=Path("outputs/runs/inventory_refresh"))
    parser.add_argument("--log-root", type=Path, default=Path("outputs/logs"))
    parser.add_argument("--config", type=Path, default=Path("orbitflow.toml"))
    args = parser.parse_args(argv)
    try:
        config = TransportConfig(
            proxy=args.proxy, cluster=args.cluster,
            bastion_host=args.bastion_host, bastion_user=args.bastion_user,
            teleport_key_path=args.teleport_key_path, teleport_cert_path=args.teleport_cert_path,
        )
        # UUID also separates runs started within the same clock tick.
        filename = f"inventory_{datetime.now(timezone.utc):%Y%m%dT%H%M%S_%fZ}_{uuid4().hex}.xlsx"
        print("Inventory refresh started.", flush=True)
        destination = refresh_inventory_from_excel(
            args.excel_path, config,
            inventory_path=args.inventory_path, export_path=args.reports_dir / filename,
            spool_root=args.spool_root, log_root=args.log_root,
            execution_config=load_execution_config(args.config),
        )
    except Exception as exc:
        if not log_run_failure(exc, log_root=args.log_root):
            print("Run-level diagnostics could not be written.", flush=True)
        # Paths, parser errors and third-party exception messages may contain
        # credentials. Never render them or an exception chain to the terminal.
        raise SystemExit(
            "Inventory refresh/export failed. Check input and configured paths, "
            "application/inventory logs, and any retained run spool."
        ) from None
    print("Inventory workbook saved in the configured reports directory. "
          "Review Run_Attempts for target failures.", flush=True)
    return destination


if __name__ == "__main__":
    main()
