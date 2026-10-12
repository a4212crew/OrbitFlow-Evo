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

## Approved replacement configuration workflow — design only, not implemented

The authoritative approved target is `docs/architecture/configuration/guided-bulk-planning.md` (22 function-specific templates). The previous two-stage guided Requests/Parameters workbook, offline-only Gap C, auto methodology matching and special elevated Manual CLI approver design are **superseded**. Issue #88 was closed as not planned and PR #89 was closed unmerged. Do not implement superseded material.

The existing v1 `orbitflow.configuration` behaviour and protections above remain implemented and unchanged. Extend it through a **versioned** API-first planning contract; do not weaken v1 validation, digest/authority or secret controls.

For **predefined templates**: use shared DeviceContext, DeviceSession, device-execution, InterfaceService, VlanService, vendor configuration facts and family audit resolvers for **live, read-only** observation, exact sanitized CLI evidence, timestamps, current VLAN/service/ownership consistency and dependencies. Do not create another SSH, vendor parser, compliance policy or thread pool. Planning produces deterministic CLI with explicit differences, no-ops and reviewable conflicts. Current observation does not authorize later deployment; future apply requires fresh preflight and explicit user intent.

For **Manual CLI only**: no device connection, no live observation, no claim of semantic validation. Engineer supplies platform, management IP, scope/CLI mode and literal commands. Label impact unknown/not-live-validated. Both predefined and Manual CLI use the same simple offline Pending/Approve/Reject review, **without a special elevated role in this design**. Offline approval never implies future apply authorization.

Excel is a thin adapter: Introduction sheet navigation, one sheet per platform/function, per-row input + evidence + generated CLI + decisions, sheet-left-to-right then row-top-to-bottom same-device order; internal row IDs and a digest-bound immutable Change Plan. Template catalogue, service planner, reviewer and vendor renderer must be reusable through future REST/web interfaces independently of XLSX.

The approved catalogue and exact vendor exceptions (ASR920 inline-only; ME3600X BD global-VLAN prerequisite; EdgeSwitch tagging removal; NE05E existing VSI; platform-specific configuration-mode commands and numeric ranges) are in the authoritative design document. Update deterministic tests; do not mutate equipment in this phase.

## Approved 2026-10-12 staged Catalyst v2 milestone

For existing Issue #91 / PR #92, **first implement and validate only Templates 1–8** (C3750X and C3850X VLAN Database, Access Port, Trunk Port, Interface Description). Read [approved-catalyst-templates.md](../../../docs/architecture/configuration/approved-catalyst-templates.md) for the complete approved parser, Excel, CLI, warning, Port-channel, fallback, evidence and test contract. That detailed baseline overrides earlier generic catalogue assertions for these eight templates. Templates 9–22 remain awaiting four-stage engineer review and are **not** approved for this staged implementation.

The owner also superseded the separate v2 review command/module: use **one generated plan Excel workbook** with editable Pending/Approve/Reject values matched to an immutable digest-bound plan JSON, both under `outputs/runs/configuration/` by default. Workbook editing is not security-grade execution authorization. Keep v1 protections. Follow the existing PR revision workflow; tests and operator-controlled read-only device validation precede any merge decision. Do not automatically merge.

## Future creation/removal lifecycle guidance (proposed only)

Read `docs/architecture/configuration/configuration-removal.md` for future removal/retirement planning. Distinguish interface VLAN membership withdrawal from deletion of shared VLAN, bridge-domain or VSI objects. Do not infer removal approval from creation approval; demand reverse-reference evidence and explicit recovery/unknown-state gates. No general destructive executor is implemented.
