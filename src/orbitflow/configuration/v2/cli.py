"""Operator adapters for v2 input, live read-only planning and workbook decisions."""
import argparse
import sys
from orbitflow.execution import Progress
from orbitflow.logging import module_logger
from pathlib import Path

from orbitflow.configuration.plans import require
from .catalogue import BY_ID
from .planning import plan, save
from .workbook import create_input, read_input, export_plan


def _main(argv, logger, progress):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    template = sub.add_parser("input")
    template.add_argument("path", type=Path)
    generate = sub.add_parser("plan")
    generate.add_argument("workbook", type=Path)
    generate.add_argument("output", type=Path, nargs="?", help="JSON destination; default outputs/runs/configuration/<plan-digest>/plan.json; never overwrite")
    generate.add_argument("--devices", type=Path, default=Path("devices.xlsx"))
    generate.add_argument("--max-concurrent-devices", type=int)
    for name in ("proxy", "cluster", "bastion-host", "bastion-user"):
        generate.add_argument("--" + name)
    generate.add_argument("--inventory-path", default="data/inventory/inventory.json")
    generate.add_argument("--config", default="orbitflow.toml")
    generate.add_argument("--teleport-key-path", type=Path)
    generate.add_argument("--teleport-cert-path", type=Path)
    args = parser.parse_args(argv)
    stage = "input" if args.command == "input" else "validation"
    try:
        if args.command == "input":
            create_input(args.path)
            return
        if args.output is not None:
            require(args.output.suffix == ".json", "plan output must use .json")
            require(not args.output.exists() and not args.output.with_suffix(".xlsx").exists(), "output already exists")
        if args.command == "plan":
            progress("Planning run start; reading input workbook")
            logger.info("Planning run start")
            stage = "workbook input"
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
                stage = "observation setup"
                credentials = load_device_credentials(args.devices, sorted(ips))
                execution = load_execution_config(args.config)
                if args.max_concurrent_devices is not None:
                    require(args.max_concurrent_devices >= 1, "invalid concurrency limit")
                    execution = replace(execution, max_concurrent_devices=args.max_concurrent_devices)
                config = TransportConfig(args.proxy, args.cluster, args.bastion_host, args.bastion_user,
                                         teleport_key_path=args.teleport_key_path, teleport_cert_path=args.teleport_cert_path)
                stage = "observation"
                spool = collect(requests, credentials, config, inventory_path=args.inventory_path,
                                execution_config=execution, progress=progress)
                observations = bounded_observations(spool)
            progress(f"Planning proposals; rows={len(requests)}; live targets={len(ips)}")
            logger.info("Planning proposals")
            stage = "planning"
            result = plan(requests, observations, source="workbook-sha256:" + requests.source_digest)
        args.output = args.output or Path("outputs/runs/configuration") / result.digest / "plan.json"
        require(not args.output.exists() and not args.output.with_suffix(".xlsx").exists(), "output already exists")
        progress("Exporting immutable plan and decision workbook")
        logger.info("Export start: " + str(args.output))
        stage = "plan export"
        save(result, args.output)
        stage = "workbook export"
        export_plan(result, args.output.with_suffix(".xlsx"))
        logger.info("Export completed: " + str(args.output) + "; review=" + str(args.output.with_suffix(".xlsx")))
        progress(f"Plan {result.digest}; offline review only; device execution is not authorized.")
    except Exception as exc:
        # Class categories only: exception messages/tracebacks may contain secrets.
        from orbitflow.logging import sanitize_text
        category = sanitize_text(type(exc).__name__)
        logger.error(f"Planning command failed; stage={stage}", extra={"error_category": category})
        parser.exit(2, f"Planning failed ({category}); see configuration module logs.\n")


def main(argv=None):
    with module_logger("configuration", "bulk_planning") as (logger, _):
        try:
            return _main(argv, logger, Progress(sys.stdout))
        finally:
            logger.info("Planning command ended")


if __name__ == "__main__":
    main()
