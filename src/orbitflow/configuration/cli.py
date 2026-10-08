"""Offline plan creation, review, and explicit approval; no apply command."""

import argparse
from datetime import datetime
from pathlib import Path
import sqlite3

from orbitflow.inventory.store import JsonInventoryStore
from .approvals import ApprovalStore
from .plans import PlanError, create_plan, decode, load_plan, save_plan


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    create = sub.add_parser("create")
    create.add_argument("request", type=Path)
    create.add_argument("--inventory", type=Path, default=Path("data/inventory/inventory.json"))
    create.add_argument("--output", type=Path)
    for command in ("validate", "preview", "approve", "reject", "expire", "verify-approval"):
        child = sub.add_parser(command)
        child.add_argument("plan", type=Path)
        if command in ("approve", "reject", "expire", "verify-approval"):
            child.add_argument("--authority", type=Path, default=Path("data/configuration"))
        if command in ("approve", "reject", "expire"):
            child.add_argument("--actor", required=True)
        if command == "approve":
            child.add_argument("--digest", required=True, help="Exact digest from the reviewed preview")
            child.add_argument("--expires-at", required=True, help="ISO 8601 timestamp with timezone")
    args = parser.parse_args(argv)
    try:
        if args.command == "create":
            request = decode(args.request.read_text(encoding="utf-8"))
            plan = create_plan(request, JsonInventoryStore(args.inventory).contexts())
            output = args.output or Path("outputs/runs/configuration") / plan.to_dict()["change_id"] / "plan.json"
            save_plan(plan, output)
            print("Created plan " + plan.digest)
        else:
            plan = load_plan(args.plan)
            if args.command == "preview":
                print(plan.preview())
            elif args.command == "validate":
                print("Valid offline plan " + plan.digest)
            elif args.command == "verify-approval":
                ApprovalStore(args.authority).verify(plan)
                print("Approval verified " + plan.digest)
            else:
                expiry = None
                if args.command == "approve":
                    if args.digest != plan.digest:
                        raise PlanError("reviewed digest mismatch")
                    expiry = datetime.fromisoformat(args.expires_at)
                status = {"approve": "approved", "reject": "rejected", "expire": "expired"}[args.command]
                ApprovalStore(args.authority).decide(plan, status, args.actor, expires_at=expiry)
                print(status.capitalize() + " " + plan.digest)
    except PlanError as exc:
        print("Configuration plan refused: " + str(exc))
        return 2
    except (OSError, ValueError, TypeError, KeyError, sqlite3.Error):
        print("Configuration plan refused: invalid input or unavailable local storage")
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
