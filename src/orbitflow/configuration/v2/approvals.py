"""V2 offline review authority; shares signed storage primitives, never v1 gates."""
from datetime import datetime, timezone
import hashlib
import hmac
import sqlite3

from orbitflow.configuration.approvals import ApprovalStore, timestamp
from orbitflow.configuration.plans import canonical, label, require, PlanError
from .planning import BulkPlan


class ReviewStore(ApprovalStore):
    def __init__(self, root="data/configuration/v2"):
        super().__init__(root)

    def decide(self, plan, status, actor, *, now=None, expires_at=None):
        plan = BulkPlan(plan.content)
        label(actor)
        require(status in {"pending", "approved", "rejected", "expired"}, "invalid review decision")
        now = now or datetime.now(timezone.utc)
        issued = timestamp(now)
        if status == "approved":
            require(expires_at is not None and expires_at > now, "future review expiry required")
            require(all(r["decision"] != "Pending" for r in plan.to_dict()["results"]), "pending rows remain")
        expiry = timestamp(expires_at) if status == "approved" else None
        self.initialize()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            records, previous = self._records(db)
            require(not records or issued >= records[-1]["issued_at"], "approval clock moved backwards")
            record = dict(schema_version=2, digest=plan.digest, status=status, actor=actor,
                          issued_at=issued, expires_at=expiry, previous=previous, execution_authorized=False)
            body = canonical(record)
            signature = hmac.new(self._key(), body.encode(), hashlib.sha256).hexdigest()
            db.execute("INSERT INTO decisions VALUES (?, ?, ?)", (len(records) + 1, body, signature))
        return record

    def verify(self, plan, *, now=None):
        plan = BulkPlan(plan.content)
        current = timestamp(now or datetime.now(timezone.utc))
        require((self.root / "approvals.sqlite3").is_file(), "plan is unapproved")
        try:
            with self._connect() as db:
                records, _ = self._records(db)
            matches = [r for r in records if r["schema_version"] == 2 and r["digest"] == plan.digest]
            require(bool(matches), "plan is unapproved")
            record = matches[-1]
            require(record["status"] == "approved" and record["issued_at"] <= current < record["expires_at"], "review rejected or expired")
            return dict(record)
        except (sqlite3.Error, KeyError, TypeError):
            raise PlanError("review authority corrupt") from None
