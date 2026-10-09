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

## Future Engineer-Reviewed Templates and Bulk Input (Not Yet Implemented)

Follow `docs/architecture/configuration/interface-methodology-review.md`.
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
