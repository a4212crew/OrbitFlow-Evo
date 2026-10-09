---
name: configuration-management
description: Use for offline Universal Change Plans, deterministic rendering, validation, inventory identity resolution, review and durable approval gates.
---

# Configuration Management

Phase 1–2 implementation is in `src/orbitflow/configuration/`; operator entry
points are `python -m orbitflow.configuration.cli` and
`scripts/configuration_plan.py`. Read `docs/architecture/configuration/offline-plans.md`
for the v1 contract. Live execution and additional adapters are future work.

- Resolve existing `DeviceContext` snapshots; never connect or refresh inventory.
- Closed schemas reject unknown fields. Canonical JSON is immutable content;
  SHA-256 includes provenance, identity, operations, commands, preconditions,
  desired facts and execution safety policy.
- Keep rendering in vendor modules. Initial allowlist is VLAN creation on
  C3750X/cisco_ios and C3850/cisco_xe with matching capability profiles.
  Conflicting existing VLAN names block; already-correct state is a no-op.
- Manual commands must exactly match the allowlisted rendering. Spreadsheet,
  template and compliance producers submit normalized JSON; raw workbook import,
  template catalogues and remediation generation are not implemented.
- Require explicit preconditions and verification facts. Never interpret raw
  configuration here or generate rollback by reversing commands.
- Approval binds the full resolved digest. Revalidate at load and at the gate;
  unknown, rejected, expired, changed or corrupt artifacts fail closed.
- `ApprovalStore` signs transactional local SQLite decisions with a separate
  local key. Protect authority state with OS permissions. Actor labels are audit
  metadata, not authenticated identities. Whole-store rollback is not prevented.
- Reject credential-bearing fields/text/commands before persistence. Use fixed
  diagnostics and shared sanitization; never echo untrusted input errors.
- Default plans: `outputs/runs/configuration/<change-id>/plan.json`.
  Authority: `data/configuration/`; never commit its key or database.
- No transport, device execution, live checks, backup, apply, save or rollback
  belongs to this phase.

Run `python -m pytest tests/test_configuration_plans.py -q` and appropriate shared
inventory/vendor regressions. Cover identity, mutation, expiry, tampering,
credential rejection and no device side effects for changes.

## Future Guided Bulk Configuration Planning — Approved C1–C4 Design (Not Yet Implemented)

Follow `docs/architecture/configuration/guided-bulk-planning.md` for the approved integrated C1–C4 intent-driven Excel workflow and deferred Gap B boundary. Engineers provide device/interface/action, not methodology or template IDs; generate required action-specific fields from a versioned, profile-gated template catalogue. Unique compatible matches may be proposed, ambiguity requires engineer selection, and no compatible template fails closed. Preserve exact per-device order for multiple templates and advanced manual CLI on one interface, validate known effects/conflicts and block any unknown manual-CLI effect from execution authorization. Use a versioned extension to the immutable offline Change Plan contract; never weaken existing v1 allowlists, digest checks or authority rules. C1–C4 do not connect to devices or execute configuration.

Follow `docs/architecture/configuration/interface-methodology-review.md` for methodology facts.
Existing AuditResolver observations feed an engineer-reviewed resolution report;
engineers select approved, versioned templates to **update existing** interfaces
or **configure new** interfaces. No automatic template choice solely by model or
methodology. An approved template version plus its bounded parameters, target,
source snapshot and generated commands form an auditable Change Plan.

- Standard changes may use pre-approved template policy only when target,
  parameters, batch size and constraints match; explicit operator execution
  intent, fresh prechecks and audit remain mandatory.
- Advanced free-form CLI, including Excel-supplied ordered commands, is for
  authorised engineers and needs separately authenticated elevated approval;
  current actor labels alone are insufficient for this future workflow.
- Bulk Excel is a review/input surface, not the authoritative executable plan.
  Preserve row IDs, per-target evidence, exceptions, explicit exclusions,
  stable command order, individual plan digests and parent-batch provenance.
- Do not weaken the current allowlisted v1 CLI/approval gates or imply that
  template import, pre-approval or advanced CLI execution is already available.

## Future creation/removal lifecycle guidance (proposed only)

Read `docs/architecture/configuration/configuration-removal.md` when scoping
removal/retirement planning. Distinguish detach vs delete and link-level changes
vs shared VLAN, bridge-domain, VSI or service-object destruction. Do not treat
pre-approved create/update templates as pre-approved deletion. Demand complete
reverse-reference evidence, default/implicit VLAN semantics, preserved unrelated
service state, narrowly scoped command rendering, and explicit recovery/unknown
outcome gates. Imported RM-series workbook sketches are **not** authorised CLI.
No new destructive operation is supported by current offline v1 or Phase 3.
