"""Operator adapters for v2 input, live read-only planning and workbook decisions."""
from orbitflow.terminal_progress import cli_progress, location, workflow_progress, current_display
import argparse
import sys
import re
from datetime import datetime
from orbitflow.execution import Progress
from orbitflow.logging import module_logger
from pathlib import Path

from orbitflow.configuration.plans import require
from .catalogue import BY_ID
from .planning import plan, save
from .workbook import create_input, read_input, export_plan


def _default_output(requests, *, now=None, root=Path("outputs/reports/configuration")):
    """Reserve a display directory; only the immutable plan digest is authoritative."""
    targets = {(BY_ID[r["template_id"]].family, r["inputs"]["management_ip"])
               for r in requests}
    if targets and all(family == "All" for family, _ in targets):
        descriptor = "Manual-only"
    elif len(targets) == 1:
        family, address = next(iter(targets))
        descriptor = f"{family}-{address}"
    else:
        descriptor = f"multi-device-{len({address for _, address in targets})}"
    # ASCII allowlist, bounded length, no separators/dots/control characters.
    descriptor = re.sub(r"[^A-Za-z0-9_]+", "-", descriptor).strip("-_")[:100] or "targets"
    stamp = (now or datetime.now().astimezone()).strftime("%Y%m%d-%H%M%S")
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    base = f"{stamp}_{descriptor}"
    suffix = 0
    while True:
        directory = root / (base if suffix == 0 else f"{base}-{suffix:02d}")
        try:
            directory.mkdir()  # Atomic reservation across simultaneous CLI processes.
        except FileExistsError:
            suffix += 1
        else:
            return directory / "plan.json"


def _main(argv, logger, progress):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    template = sub.add_parser("input")
    template.add_argument("path", type=Path)
    generate = sub.add_parser("plan")
    generate.add_argument("workbook", type=Path)
    generate.add_argument("output", type=Path, nargs="?", help="JSON destination; default outputs/reports/configuration/<timestamp>_<target>/plan.json; never overwrite")
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
            location('Input workbook saved', args.path)
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
                with workflow_progress('Loading observation records', quiet=current_display.get() is None):
                    observations = bounded_observations(spool)
            progress(f"Planning proposals; rows={len(requests)}; live targets={len(ips)}")
            logger.info("Planning proposals")
            stage = "planning"
            with workflow_progress('Planning requests', quiet=current_display.get() is None):
                result = plan(requests, observations, source="workbook-sha256:" + requests.source_digest)
        args.output = args.output or _default_output(requests)
        require(not args.output.exists() and not args.output.with_suffix(".xlsx").exists(), "output already exists")
        progress("Exporting immutable plan and decision workbook")
        logger.info("Export start: " + str(args.output))
        stage = "plan export"
        with workflow_progress('Saving immutable plan', quiet=current_display.get() is None):
            save(result, args.output)
        location('Immutable plan saved', args.output)
        stage = "workbook export"
        with workflow_progress('Exporting decision workbook', quiet=current_display.get() is None):
            export_plan(result, args.output.with_suffix(".xlsx"))
        location('Decision workbook saved', args.output.with_suffix(".xlsx"))
        logger.info("Export completed: " + str(args.output) + "; review=" + str(args.output.with_suffix(".xlsx")))
        progress(f"Plan {result.digest}; offline review only; device execution is not authorized.")
    except Exception as exc:
        # Class categories only: exception messages/tracebacks may contain secrets.
        from orbitflow.logging import sanitize_text
        category = sanitize_text(type(exc).__name__)
        logger.error(f"Planning command failed; stage={stage}", extra={"error_category": category})
        parser.exit(2, f"Planning failed ({category}); see configuration module logs.\n")


@cli_progress('Planning stages')
def main(argv=None):
    with module_logger("configuration", "bulk_planning") as (logger, _):
        try:
            return _main(argv, logger, Progress(sys.stdout))
        finally:
            logger.info("Planning command ended")


if __name__ == "__main__":
    main()
