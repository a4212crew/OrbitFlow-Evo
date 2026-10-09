# Offline Change Plans: implemented v1

Issue #75 implements Phases 1–2 only. `orbitflow.configuration` exposes
`create_plan(request, contexts)`, `ChangePlan`, `save_plan`, `load_plan`, and
`ApprovalStore`. There is no apply API. Inventory snapshots are not proof of
current device state; future execution must refresh identity and preconditions.

## Supported operations and sources

The initial profile supports `ensure_vlan_present` for C3750X (`cisco_ios`,
`c3750x_switching`) and C3850 (`cisco_xe`, `c3850_switching`). VLAN IDs are
2–4094 excluding 1002–1005; names are ASCII identifiers up to 32 characters.
Existing VLANs with different names conflict; already-correct state produces
no commands. Other operations/profiles fail closed.

All four source kinds (`manual`, `spreadsheet`, `template`, `compliance`) use
the same normalized JSON request. This is an interchange/API foundation: raw
workbook parsing, template catalogues and remediation generation are future work.
Producers supply a sanitized reference and immutable source/template/policy
version. Manual sources additionally supply `commands` for each operation,
exactly matching the supported rendering (empty for a no-op).

Example request using a synthetic identity; substitute the ID and expected
identity from the local canonical inventory:

```json
{
  "schema_version": 1,
  "change_id": "CHG-EXAMPLE-001",
  "source": {"kind": "template", "reference": "vlan-create", "version": "1"},
  "intent": "Create customer VLAN",
  "targets": [{
    "inventory_id": "switch-1",
    "expected_hostname": "switch-1",
    "expected_platform": "cisco_xe",
    "operations": [{
      "kind": "ensure_vlan_present", "vlan_id": 3500, "vlan_name": "CUSTOMER",
      "precondition": {"present": false, "name": ""},
      "verification": {"present": true, "name": "CUSTOMER"}
    }]
  }],
  "execution_policy": {
    "dry_run": true, "require_approval": true, "backup_required": true,
    "save_after_verify": true, "max_concurrent_devices": 1,
    "max_devices_per_run": 5, "stop_after_failures": 1,
    "recovery_strategy": "manual", "rollback_available": false,
    "unknown_outcome": "stop_and_escalate"
  }
}
```

Limits are integers from 1 to 100; concurrency cannot exceed the run cap.
Remaining safety fields are fixed in v1. Approval never disables dry-run.

## Identity and serialization

Creation uses existing `DeviceContext` values (CLI reads
`JsonInventoryStore.contexts()`). Missing/failed observations, expected identity
mismatches, duplicate targets and ambiguous hostname, address or serial identities
are rejected. Resolved identity freezes inventory ID, management IP, hostname,
platform, device family, capability profile and serial. Each target owns its
operations and `vlan_database` verification capability. This declares a planned
check; it does not assert live verification occurred.

Artifacts contain exactly `digest` and `plan`. The resolved plan has the same
top-level fields as the request; targets contain `identity`, `operations` and
`verification_capability`. Operations additionally contain deterministic
`commands`. Closed schemas reject unknown/missing fields, duplicate JSON keys,
unsupported versions, conflicts, missing checks, unsafe identifiers, credential
markers and non-allowlisted commands. Never supply credentials in any field;
arbitrary unlabeled secret strings cannot reliably be classified as secrets.
Raw configuration and arbitrary commands are not accepted.

Canonical JSON uses sorted keys, compact separators, ASCII escaping and no
NaN/infinity. Array order preserves operational intent. SHA-256 covers the whole
resolved plan, excluding approval metadata. Immutable `ChangePlan` returns
detached copies. Writes create files exclusively; use a new path/change ID for
revisions. Every load checks schema, semantics and the stored digest.

## Operator workflow

```powershell
python -m orbitflow.configuration.cli create request.json
python -m orbitflow.configuration.cli validate outputs/runs/configuration/CHG-EXAMPLE-001/plan.json
python -m orbitflow.configuration.cli preview outputs/runs/configuration/CHG-EXAMPLE-001/plan.json
python -m orbitflow.configuration.cli approve outputs/runs/configuration/CHG-EXAMPLE-001/plan.json --actor operator --digest <reviewed-sha256> --expires-at 2026-10-09T12:00:00+11:00
python -m orbitflow.configuration.cli verify-approval outputs/runs/configuration/CHG-EXAMPLE-001/plan.json
python -m orbitflow.configuration.cli reject outputs/runs/configuration/CHG-EXAMPLE-001/plan.json --actor operator
python -m orbitflow.configuration.cli expire outputs/runs/configuration/CHG-EXAMPLE-001/plan.json --actor operator
```

Choose a future timezone-aware expiry. `create` accepts `--inventory` and
`--output`; approval commands accept `--authority` (default `data/configuration`).
Errors return status 2 with sanitized messages. Preview shows all resolved content.

## Approval authority

The local authority records approve/reject/expire events transactionally in
SQLite with actor, UTC issue/expiry timestamps, plan digest and a signed history
chain. A separate random key authenticates records. Missing state/key, corrupt
records, mismatched plans, rejection, explicit expiry, time before issuance and
time at/after expiry fail closed. Decisions survive reopening. Time expiry is
enforced at every verification without needing an explicit expire event. New
explicit approval can supersede an earlier decision; history is retained.

Protect the directory with OS permissions and backups. Actor labels are not
authenticated accounts. This authority does not protect against administrators
replacing both key and database, restoring old state or deleting a history tail.
It is not a remote approval service. Keys never appear in plan/audit output.
Default and custom authority directories have Git ignore protection.

Deterministic tests cover the offline lifecycle, profiles, source kinds, no-op
and conflict behavior, identity ambiguity, serialization, credential rejection,
digest changes, expiry, tampering and CLI operation with sockets disabled.
Device apply, live checks and adapter lab qualification remain future work.
