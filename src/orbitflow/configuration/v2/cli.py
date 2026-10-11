"""Operator adapters for v2 input, live read-only planning and offline review."""
import argparse
from datetime import datetime, timedelta, timezone
from pathlib import Path

from orbitflow.configuration.plans import PlanError, require
from .catalogue import BY_ID
from .planning import plan, save, load
from .workbook import create_input, read_input, export_review, import_review
from .approvals import ReviewStore


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    template = sub.add_parser("input")
    template.add_argument("path", type=Path)
    generate = sub.add_parser("plan")
    generate.add_argument("workbook", type=Path)
    generate.add_argument("output", type=Path)
    generate.add_argument("--devices", type=Path, default=Path("devices.xlsx"))
    generate.add_argument("--max-concurrent-devices", type=int)
    for name in ("proxy", "cluster", "bastion-host", "bastion-user"):
        generate.add_argument("--" + name)
    generate.add_argument("--inventory-path", default="data/inventory/inventory.json")
    generate.add_argument("--config", default="orbitflow.toml")
    generate.add_argument("--teleport-key-path", type=Path)
    generate.add_argument("--teleport-cert-path", type=Path)
    review = sub.add_parser("review")
    review.add_argument("plan", type=Path)
    review.add_argument("workbook", type=Path)
    review.add_argument("output", type=Path)
    review.add_argument("--actor", required=True)
    review.add_argument("--authority", default="data/configuration/v2")
    review.add_argument("--expires-hours", type=int, default=24)
    args = parser.parse_args(argv)
    try:
        if args.command == "input":
            create_input(args.path)
            return
        require(not args.output.exists() and not args.output.with_suffix(".xlsx").exists(), "output already exists")
        require(args.output.suffix == ".json", "plan output must use .json")
        if args.command == "plan":
            requests = read_input(args.workbook)
            ips = {r["inputs"]["management_ip"] for r in requests if BY_ID[r["template_id"]].family != "All"}
            observations = {}
            if ips:
                require(all(getattr(args, k) for k in ("proxy", "cluster", "bastion_host", "bastion_user")), "live routing required")
                from orbitflow.transport import TransportConfig
                from orbitflow.config import load_execution_config
                from .observation import collect, bounded_observations
                from orbitflow.targets import load_device_credentials
                from dataclasses import replace
                credentials = load_device_credentials(args.devices, sorted(ips))
                execution = load_execution_config(args.config)
                if args.max_concurrent_devices is not None:
                    require(args.max_concurrent_devices >= 1, "invalid concurrency limit")
                    execution = replace(execution, max_concurrent_devices=args.max_concurrent_devices)
                config = TransportConfig(args.proxy, args.cluster, args.bastion_host, args.bastion_user,
                                         teleport_key_path=args.teleport_key_path, teleport_cert_path=args.teleport_cert_path)
                spool = collect(requests, credentials, config, inventory_path=args.inventory_path,
                                execution_config=execution)
                observations = bounded_observations(spool)
            result = plan(requests, observations, source="workbook-sha256:" + requests.source_digest)
        else:
            require(1 <= args.expires_hours <= 168, "invalid review expiry")
            result = import_review(load(args.plan), args.workbook)
        save(result, args.output)
        export_review(result, args.output.with_suffix(".xlsx"))
        if args.command == "review":
            status = "pending" if any(r["decision"] == "Pending" for r in result.to_dict()["results"]) else "approved"
            ReviewStore(args.authority).decide(result, status, args.actor,
                expires_at=datetime.now(timezone.utc) + timedelta(hours=args.expires_hours))
        print(f"Plan {result.digest}; offline review only; device execution is not authorized.")
    except PlanError as exc:
        parser.exit(2, f"Planning failed: {exc}\n")


if __name__ == "__main__":
    main()
