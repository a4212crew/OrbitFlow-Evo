"""Guided bulk configuration planning. Offline artifacts only; no apply command."""

import argparse
from pathlib import Path
from uuid import uuid4

from orbitflow.inventory.store import JsonInventoryStore
from .jobs import load_manifest, plan, prepare
from .plans import PlanError


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("prepare", "plan"):
        child = sub.add_parser(command)
        child.add_argument("workbook", type=Path)
        child.add_argument("--inventory", type=Path, default=Path("data/inventory/inventory.json"))
        child.add_argument("--output", type=Path)
        if command == "plan":
            child.add_argument("--batch-id")
    validate = sub.add_parser("validate-batch")
    validate.add_argument("manifest", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "validate-batch":
            load_manifest(args.manifest)
            print("Validated offline batch and all bound plans")
        elif args.command == "prepare":
            output = args.output or Path("outputs/runs/configuration") / ("prepare-" + uuid4().hex) / "guided.xlsx"
            result = prepare(args.workbook, JsonInventoryStore(args.inventory).contexts(), output)
            print(f"Prepared {len(result['prepared']['rows'])} input outcomes: {output}")
        else:
            batch_id = args.batch_id or "batch-" + uuid4().hex
            output = args.output or Path("outputs/runs/configuration") / batch_id
            result = plan(args.workbook, JsonInventoryStore(args.inventory).contexts(), output, batch_id)
            load_manifest(output / "manifest.json")
            print(f"Created {len(result['members'])} offline plans and {len(result['results'])} input outcomes: {output}")
            if any(r["status"] in ("blocked", "rejected", "skipped") for r in result["results"]):
                print("Inputs require correction or explicit exclusion review; see consolidated preview")
                return 2
    except (PlanError, OSError, ValueError, TypeError, KeyError):
        print("Configuration job refused: invalid input or unavailable local artifact; no device activity")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
