---
name: configuration-management
description: Use for Change Plans, rendering, review/approval, and approved configuration execution, verification, save and reusable execution services.
---

# Configuration Management

Phase 1–2 implementation is in `src/orbitflow/configuration/`; operator entry
points are `python -m orbitflow.configuration.cli` and
`scripts/configuration_plan.py`. Read `docs/architecture/configuration/offline-plans.md`
for the v1 contract. Separate predefined Catalyst/EdgeSwitch execution is implemented
in merged PR #118 (historical implementation). Additional adapters remain
future work. The restrictions below apply to v1 planning, not the separate executor.

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

## Historical approved replacement planning workflow — implementation context follows

The architecture catalogue is `docs/architecture/configuration/guided-bulk-planning.md` (22 function-specific templates). Detailed approved contracts: `docs/architecture/configuration/approved-catalyst-templates.md` (1–8) and `docs/architecture/configuration/approved-me3600x-asr920-edgeswitch-templates.md` (9–16); latter supersedes older generic EVC and EdgeSwitch notes. Templates 17–22 still await detailed owner sign-off. The previous two-stage guided Requests/Parameters workbook, offline-only Gap C, auto methodology matching and special elevated Manual CLI approver design are **superseded**. Issue #88 was closed as not planned and PR #89 was closed unmerged. Do not implement superseded material.

The existing v1 `orbitflow.configuration` behaviour and protections above remain implemented and unchanged. Extend it through a **versioned** API-first planning contract; do not weaken v1 validation, digest/authority or secret controls.

For **predefined templates**: use shared DeviceContext, DeviceSession, device-execution, InterfaceService, VlanService, vendor configuration facts and family audit resolvers for **live, read-only** observation, exact sanitized CLI evidence, timestamps, current VLAN/service/ownership consistency and dependencies. Do not create another SSH, vendor parser, compliance policy or thread pool. Planning produces deterministic CLI with explicit differences, no-ops and reviewable conflicts. Current observation does not authorize later deployment; future apply requires fresh identity/target/prerequisite and session safety, backup, and explicit user intent.

For **legacy offline Manual CLI plans only**: no device connection, no live observation, no claim of semantic validation. Engineer supplies platform, management IP, scope/CLI mode and literal commands. Label impact unknown/not-live-validated. Both predefined and Manual CLI use the same simple offline Pending/Approve/Reject review, **without a special elevated role in this design**. Offline approval never implies future apply authorization.

Excel is a thin adapter: Introduction sheet navigation, one sheet per platform/function, per-row input + evidence + generated CLI + decisions, sheet-left-to-right then row-top-to-bottom same-device order; internal row IDs and a digest-bound immutable Change Plan. Template catalogue, service planner, reviewer and vendor renderer must be reusable through future REST/web interfaces independently of XLSX.

For Templates 9–16 follow the detailed signed-off requirements document: shared ME3600X/ASR920 EVC parser, VLAN ranges/QinQ, separate Push symmetry and push_vlan, split-horizon group 0, always Remove/Recreate CLI, ME parent switchport predicate/ASR inline BD, complete evidence, and EdgeSwitch Add/Change or Remove with independently parsed PVID, membership and tagging (no Replace and missing global VLAN not blocking). The general catalogue documents remaining vendor exceptions. Extend shared normalized parsers without breaking VLAN audit/compliance. Update deterministic tests; do not mutate equipment in this phase.

## Approved 2026-10-12 staged Catalyst v2 milestone

For existing Issue #91 / PR #92, **first implement and validate only Templates 1–8** (C3750X and C3850X VLAN Database, Access Port, Trunk Port, Interface Description). Read [approved-catalyst-templates.md](../../../docs/architecture/configuration/approved-catalyst-templates.md) for the complete approved parser, Excel, CLI, warning, Port-channel, fallback, evidence and test contract. That detailed baseline overrides earlier generic catalogue assertions for these eight templates. Templates 9–22 remain awaiting four-stage engineer review and are **not** approved for this staged implementation.

The owner also superseded the separate v2 review command/module: use **one generated plan Excel workbook** with editable Pending/Approve/Reject values matched to an immutable digest-bound plan JSON, both under `outputs/runs/configuration/` by default. Workbook editing is not security-grade execution authorization. Keep v1 protections. Follow the existing PR revision workflow; tests and operator-controlled read-only device validation precede any merge decision. Do not automatically merge.

## Future creation/removal lifecycle guidance (proposed only)

Read `docs/architecture/configuration/configuration-removal.md` for future removal/retirement planning. Distinguish interface VLAN membership withdrawal from deletion of shared VLAN, bridge-domain or VSI objects. Do not infer removal approval from creation approval; demand reverse-reference evidence and explicit recovery/unknown-state gates. No general destructive executor is implemented.

## Owner-approved configuration execution milestone — 2026-10-17

**Historical implementation: PR #118 (Issue #117), subsequently merged.**
For apply, verification, save, reusable
summary/confirmation or switchport observation, read
[approved device execution](../../../docs/architecture/configuration/approved-device-execution.md).
It supersedes older proposed global batch-stop/save-only-after-verification policy
for C3750X/C3850 and EdgeSwitch. Preserve existing v1/v2 planning contracts above.
Group ordered rows by IP through shared execution; explicit confirmation is separate
from workbook decisions. Use independent collectors/parsers and vendor adapters,
retain command/evidence/log records, and keep source review artifacts unchanged.
EdgeSwitch missing global VLANs block dependent execution, not planning. Save at
device-task end including partial changes; original EXEC prompt return is the
approved save-completion criterion, with errors recorded separately. No Issue,
apply or merge is authorized merely by this design.

Current execution entry point: `python -m orbitflow.configuration.execution_cli`.
See [execution manual](../../../docs/user_manual/configuration-execution.md) and
[supported standalone APIs](../../../docs/operations/configuration-execution-api.md).
Require matching normalized Cisco Name/EdgeSwitch Port identity. Preserve the
approved C3750X dot1q change and verify relevant preserved settings after execution. Use optional shared
run/row/digest correlation and elapsed timing for standalone capability logs.
The executor is separate from v1/v2 planning; no production validation is implied.

## Execution presentation and progress — reviewed iteration 4

Historical PR #118 implementation (merged); validate current source: `operator_summary` groups
short findings/skips by category and source sheet/row ranges; `render_summary` uses
compact VLAN lists with no nested evidence or primary opaque row IDs. Full bound
preparation and replay protections remain unchanged. Execution display filters only
TAGGED_VLAN_NOT_IN_MEMBERSHIP; source plan/compliance findings stay unchanged.

Default protected captures are RUN/backups with run-relative references; explicit
backups_dir overrides retain ROOT/RUN_ID. Reports use template/input columns, fresh
durable pre-row config, attempted commands, scoped post CLI, concise actual/expected
checks and fallback source, linked complete detail and canonical manifest run_id.
Older missing pre-row evidence is Not captured; offline reporting never connects
or reclassifies historical Unknown outcomes. Do not replay completed owner changes.

`confirm(..., progress=None)` accepts an optional serialized scalar-event subscriber.
No subscriber means quiet/no timer. CLI flushes stages and five-second waiting
snapshots with IP/hostname, row/command counts and elapsed/deadline information where
known. Waiting is not device liveness and Returned is not verified success. The
optional timer never accesses channels, extends deadlines or retries writes. Display
exceptions disable the subscriber; mandatory audit failures remain failures. See
the supported [progress API](../../../docs/operations/configuration-execution-api.md#structured-progress-subscription).


## Approved execution simplification — 2026-10-19 (Issue #139 / PR #140)

Owner-approved scope: confirmed predefined execution for C3750X, C3850X and
EdgeSwitch only. This section supersedes older execution-stage replanning and
trusted-baseline drift-equality language above; it does **not** alter v1/v2
planning, reviewed workbook integrity or execution authorization.

- Apply only digest-bound immutable approved CLI in existing sheet/row and device
  order, with one separate summary-bound operator confirmation and replay protection.
  Do not rerender commands or use fresh planning results to block a command merely
  because its effect is already present or projected state differs.
- Before device writes require fresh identity/capability/privilege, reliable
  normalized source and resolved-target identity, valid Port-channel/bundle ownership,
  known conversion and VLAN prerequisites, verified dependencies, a usable owned SSH
  session and a protected pre-change backup. An actual unsafe dependency or target
  ambiguity still blocks affected writes; ordinary planning warnings are not new gates.
- Preserve contiguous template-stage splitting for overlap/dependencies, consolidated
  post-stage collection and individual per-target switchport/VLAN read-only checks.
  Separate per-row verification from CLI echo/response evidence. A rejected command
  stops its row; continue independent work only with a synchronized session. Lost or
  ambiguous SSH stops writes for that device with truthful Unknown/Not executed status.
- After any attempted write, save once even with partial failures, only from verified
  privileged EXEC on a usable device-owned session. Do not blindly retry or claim
  a failed row was verified because saving succeeded.
- No new ME3600X/ASR920 EVC or Manual CLI apply support is authorized. Preserve
  standalone capability, read-only, inventory, reporting, VLAN compliance and
  backup behavior. See [execution architecture](../../../docs/architecture/configuration/approved-device-execution.md)
  and [operator guide](../../../docs/user_manual/configuration-execution.md).
- PR #140 is under review and not merged as of this documentation change. Its
  synthetic test evidence is distinct from pending owner/live validation. Source
  and tests, not this skill, establish implemented behavior on a given branch.


## Manual Configuration — Issue #156 (owner-approved superseding contract)

This separate workflow supersedes older manual-command restrictions only for the
manual sender; legacy offline Manual CLI plans remain non-executable and predefined
planning/execution policies are unchanged. See
[manual architecture](../../../docs/architecture/configuration/manual-configuration.md)
and [operator guide](../../../docs/user_manual/manual-configuration.md).

- Accept literal engineer CLI, including configure/conf, abbreviations, unknown
  roots, wrappers, credential commands and explicit save/commit. No semantic
  allowlist/denylist; retain structural bounds and redact secrets before persistence.
- Group canonical IP rows in original workbook order, including noncontiguous rows.
  Own one DeviceSession and one exact live DeviceCLI shell per device group; identify,
  establish privilege/paging and take a protected backup once before writes. Never
  close/reopen the shell between rows.
- Start each row from confirmed privileged EXEC, enter supported global config,
  send literal bounded prompt-free blocks, then explicitly synchronize to confirmed
  EXEC after every block. Journal Commands completed / awaiting device save immediately.
  Save automatically exactly once after all device rows succeed and return to EXEC;
  only confirmed save yields Completed/Saved. Any invalid row, setup/write/boundary/
  recording failure stops same-device writes and prevents new automatic save.
  Preserve Unknown after save transmission, prior block evidence and confirmed save
  despite cleanup failure; expose unsafe cleanup. Explicit engineer persistence is
  independent. Never replay/reconnect/resume after writes. Predefined partial-save
  policy is unchanged.
- Ignore blank separators, preserve nonblank CLI and cell-line identity. Numbered
  selection filters manual_*.xlsx, including explicit paths. Hidden admin password
  verification and separate confirmation precede networking; omit pre-password prose.
- Optional manual_configuration_auth.password_hash in the local profile stores
  only a salted work-factor-protected hash, never a plaintext credential. Existing
  profiles remain compatible; manual execution fails closed without authorization.
- Atomically refresh ONE consolidated manual_output timestamp workbook after each
  device finishes, with all source rows, device summary and relative capture links.
  Receive-only hostname/IP captures sit beside it, without app timestamps/row labels
  or synthetic echoes. Manual run/report/backup folders use YYYYMMDD_HHMMSS and
  numeric collision suffixes. Journals retain structured evidence and legacy recovery.
- Source implements IOS/IOS-XE and EdgeSwitch framing; XR/Huawei manual entry/save
  remain unsupported. Owner run 20261026_120437 evidenced ME3600X 12/12 and ASR920
  2/2 confirmed saves; it rejected EdgeSwitch before connection. Later owner acceptance
  is not independent configuration verification. Preserve recorded validation limits.
