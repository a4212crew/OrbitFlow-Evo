"""Local approval authority with transactional, authenticated audit records.

The database and its separate signing key are operator-controlled local state.
This is not user authentication or protection against replacement of both files.
"""

from datetime import datetime, timezone
from contextlib import contextmanager
import hashlib
import hmac
import os
from pathlib import Path
import secrets
import sqlite3

from .plans import ChangePlan, PlanError, canonical, decode, label, require


def timestamp(value):
    require(isinstance(value, datetime) and value.tzinfo is not None and value.utcoffset() is not None,
            "timezone-aware timestamp required")
    return value.astimezone(timezone.utc).isoformat(timespec="microseconds")


class ApprovalStore:
    """Serialize decisions across processes; retain all previous decisions.

    Keep the directory private to authorized operators. A shared signing key
    proves local record integrity, not the identity of the supplied actor label.
    """

    def __init__(self, root="data/configuration"):
        self.root = Path(root)

    def initialize(self):
        self.root.mkdir(parents=True, exist_ok=True)
        # Protect custom authority directories as well as the default data path.
        with (self.root / ".gitignore").open("w", encoding="utf-8") as stream:
            stream.write("*\n!.gitignore\n")
        key_path = self.root / "approval.key"
        require(not (self.root / "approvals.sqlite3").exists() or key_path.exists(), "approval key missing")
        try:
            fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        except FileExistsError:
            pass
        else:
            with os.fdopen(fd, "wb") as stream:
                stream.write(secrets.token_bytes(32))
                stream.flush()
                os.fsync(stream.fileno())
        with self._connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS decisions (sequence INTEGER PRIMARY KEY, body TEXT NOT NULL, signature TEXT NOT NULL)")

    @contextmanager
    def _connect(self):
        db = sqlite3.connect(self.root / "approvals.sqlite3", timeout=10)
        try:
            with db:
                yield db
        finally:
            db.close()

    def _key(self):
        try:
            key = (self.root / "approval.key").read_bytes()
        except OSError:
            raise PlanError("approval authority unavailable") from None
        require(len(key) == 32, "invalid approval key")
        return key

    def _records(self, db):
        key = self._key()
        records = []
        previous = ""
        for sequence, body, signature in db.execute("SELECT sequence, body, signature FROM decisions ORDER BY sequence"):
            require(sequence == len(records) + 1, "approval history corrupt")
            expected = hmac.new(key, body.encode(), hashlib.sha256).hexdigest()
            require(hmac.compare_digest(expected, signature), "approval record tampered")
            record = decode(body)
            require(record["previous"] == previous, "approval history corrupt")
            records.append(record)
            previous = signature
        return records, previous

    def decide(self, plan, status, actor, *, now=None, expires_at=None):
        plan = ChangePlan(plan.content)
        label(actor)
        require(status in ("approved", "rejected", "expired"), "invalid approval decision")
        now = now or datetime.now(timezone.utc)
        issued = timestamp(now)
        if status == "approved":
            require(plan.to_dict().get("status") != "blocked", "blocked plan cannot be approved")
            require(expires_at is not None, "approval expiry required")
            expiry = timestamp(expires_at)
            require(expires_at > now, "approval must expire in the future")
        else:
            expiry = None
        self.initialize()
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            records, previous = self._records(db)
            require(not records or issued >= records[-1]["issued_at"], "approval clock moved backwards")
            record = dict(schema_version=1, digest=plan.digest, status=status, actor=actor,
                          issued_at=issued, expires_at=expiry, previous=previous)
            body = canonical(record)
            signature = hmac.new(self._key(), body.encode(), hashlib.sha256).hexdigest()
            db.execute("INSERT INTO decisions VALUES (?, ?, ?)", (len(records) + 1, body, signature))
        return record

    def verify(self, plan, *, now=None, offline_review=False):
        """Fail closed; time expiry is effective even without an explicit expire event."""
        plan = ChangePlan(plan.content)
        require(offline_review or plan.to_dict()["schema_version"] == 1,
                "v2 approval is offline review only; execution is forbidden")
        current = timestamp(now or datetime.now(timezone.utc))
        require((self.root / "approvals.sqlite3").is_file(), "plan is unapproved")
        try:
            with self._connect() as db:
                records, _ = self._records(db)
        except (sqlite3.Error, KeyError, TypeError):
            raise PlanError("approval authority corrupt") from None
        matches = [record for record in records if record["digest"] == plan.digest]
        require(bool(matches), "plan is unapproved")
        record = matches[-1]
        require(record["status"] == "approved", "plan is not approved")
        require(record["issued_at"] <= current < record["expires_at"], "approval expired or not yet valid")
        return dict(record)
