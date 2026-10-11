# Bulk configuration planning v2

The separate `orbitflow.configuration.v2` API implements the 22-template
catalogue from [the approved design](../architecture/configuration/guided-bulk-planning.md).
Existing `orbitflow.configuration` v1 JSON plans, commands, validation and
approval authority remain unchanged.

This workflow proposes configuration and records offline engineer decisions.
It has no device apply/save/commit/rollback implementation. The 21 predefined
templates collect current read-only evidence. Manual CLI never connects or
claims live or semantic validation, including when approved.

## Operator commands

Run with the repository environment and `src` on the Python import path, as
for the existing configuration CLI:

```powershell
python -m orbitflow.configuration.v2.cli input bulk-input.xlsx
```

Introduction links to all 22 function sheets. `Description` is the shortened
worksheet label for Interface Description, keeping names within Excel's
31-character limit. C3850X template sheets resolve the existing inventory
family `C3850` and `c3850_switching` profile. Fill rows beginning at row 3;
header comments identify required fields and examples. Dropdowns describe
actions, encapsulation and modes. Optional blank descriptions preserve text.
Credentials must never be entered into this workbook.

```powershell
python -m orbitflow.configuration.v2.cli plan bulk-input.xlsx --devices devices.xlsx --max-concurrent-devices 1 --proxy TELEPORT_PROXY --cluster TELEPORT_CLUSTER --bastion-host BASTION --bastion-user BASTION_USER
```

The shared Excel target loader reads `devices.xlsx` (override with `--devices`).
Its columns are `management_ip`, `username`, `password`, and optional `secret`.
The template workbook supplies management IP only. Each live IP requires exactly
one complete credential row; missing or duplicate matches produce isolated
unavailable evidence without a connection. API callers can use the shared
`load_device_credentials` provider hook, which takes precedence over Excel,
or supply their existing in-memory credentials directly. Credentials are never
included in the plan or review workbook.

Use `--max-concurrent-devices 1` for sequential processing through the shared
execution layer, or set `[execution] max_concurrent_devices = 1` in the TOML
selected by `--config`. Teleport routing, optional key/certificate paths and
inventory options retain the existing transport contract. Manual-only workbooks
need no connection arguments and perform no credential lookup.

Manual CLI Scope identifies affected resources for review/conflict metadata.
Scope and mode never add a CLI wrapper: literal commands must contain the
required configuration hierarchy.

Outputs are an exclusively created immutable JSON plan and an adjacent XLSX
review workbook. The workbook retains input columns, original entered values,
sheet order and row positions. It adds internal row IDs, sanitized configuration
evidence, proposed CLI, timestamp, validation/consistency status, dependency IDs,
findings, no-op status and Pending/Approve/Reject. Summary includes invalid row
locations; unsafe invalid input text is deliberately omitted. Correct those rows
in the source workbook and plan again. Other valid rows continue.

Review rows and Evidence Details contain only requested interface/service/global
objects and required dependency stanzas. Internal sanitized device-wide facts
remain digest-bound for consistency checks. Evidence Details preserves source filenames, one-based line numbers and exact
sanitized excerpts; oversized main-sheet evidence refers there. The plan digest
binds the sanitized observation, facts, device identities, original inputs,
source-workbook SHA-256, catalogue version, ordering, proposals and initial decisions. Edited decisions are separate intent.
It is not a hash of a raw device backup.

Edit only Engineer Decision cells in this same plan workbook and save it. There
is no standalone review command, second workbook, reviewed JSON or v2 signing
store. These cells record unauthenticated engineer intent, not execution authority.

A future preflight caller loads the immutable JSON with `planning.load` and calls
`workbook.consume_decisions(plan, workbook_path, expected_digest=trusted_digest)`.
The digest must be pinned independently by that caller, not trusted solely from
an editable workbook. The consumer checks the matching source digest, every cell
value, sheet order, dimensions and formulas, allowing only valid decision edits.
It returns an in-memory `DecisionEvaluation` with `source_digest`, decisions,
re-evaluated results, timestamp, `authenticated=False` and
`execution_authorized=False`. It never changes, saves or re-signs a plan.
Rejecting prerequisites blocks dependent requests; stale evidence remains blocked.
Changes to protected content require re-planning. Even a matching SHA-256 proves
content integrity only, not who approved it: future apply must independently
establish authenticated authorization and perform fresh live preflight.

Omit the positional JSON destination to use
`outputs/runs/configuration/<full-plan-sha256>/plan.json` and adjacent `plan.xlsx`.
The digest includes the evaluation timestamp, so naming is deterministic for a
particular immutable plan, not identical across new observations. Existing JSON
or companion XLSX causes failure, with no overwrite or automatic suffix. The
optional positional destination remains compatible: relative paths resolve from
the working directory and absolute paths are honored exactly. Missing parents
are created. Files use exclusive creation; a failed workbook export may leave
the JSON for diagnosis, and retry must use a new path or operator cleanup.

## Ordering and readiness

For each device, order is worksheet-left-to-right, then row-top-to-bottom.
Earlier approved, unblocked VLAN creation rows can satisfy later prerequisites;
these remain projected effects, never evidence of existing device state.
Overlapping interface, VLAN or shared bridge-domain requests are explicit
conflicts, including overlaps involving unknown Manual CLI effects. Consolidate
overlapping intent and regenerate; the planner never silently selects a winner.
Device identity collisions across IPs also block readiness.

Missing/unavailable/stale evidence, missing interfaces or parents, aggregate
ownership, ambiguous bindings, unavailable global VLAN/VSI and unresolved
dependencies block readiness while retaining deterministic draft CLI. Known
VLAN renames and service changes carry impact findings. Default evidence lifetime
is one hour; API callers may select 1–86,400 seconds. Readiness describes the
evaluation timestamp only. No approval authorizes later execution; future apply
requires separate authorization and fresh preflight.

ASR920 proposals use inline EVC binding only and flag existing global bindings.
ME3600X requires the bridge-domain VLAN in the global database, not the outer
ingress tag. NCS540 keeps bridge-group/domain names separate from tags and checks
existing L2 attachment relationships. NE05E requires an existing VSI; no QinQ or
VSI creation is offered. EdgeSwitch tagged removal emits `no vlan tagging`
before participation exclusion; Access uses inclusion plus PVID. EdgeSwitch
database proposals enter `vlan database` from privileged EXEC; its interface
proposals use `configure`. Cisco proposals use `configure terminal`; Huawei
uses `system-view`. None includes save or XR commit.

## Revised input columns (catalogue 2.1)

Regenerate input workbooks with the `input` command for the revised schemas.
Catalogue 2.0 plans/workbooks must be regenerated and reviewed; old approvals
cannot authorize changed inputs or CLI. V1 contracts remain unchanged.

- NCS540 L2VPN requires `encapsulation`: `dot1q`, `QinQ` or `untagged`.
  `outer_vlan` is required for dot1q/QinQ and forbidden for untagged;
  `inner_vlan` is required only for QinQ. Untagged renders
  `encapsulation untagged`; attachment names remain independent of tags.
- EVC offers `rewrite`: `None`, `Pop1`, `Pop2`, `Push`. None explicitly
  removes an existing rewrite. Pop1 requires tagged ingress; Pop2 requires
  QinQ. ASR920 Push supports untagged ingress only, requires `push_vlan`, and
  renders `rewrite ingress tag push dot1q <push_vlan> symmetric`.
  ME3600X Push is unavailable. Legacy `pop_tags` remains supported but cannot
  be combined with `rewrite`. Blank rewrite fields never silently accept an
  existing rewrite: retained operations block readiness pending explicit input.
- EdgeSwitch VLAN Port requires interface plus membership or PVID intent.
  `vlans` specifies tagged membership with `action` Add/Remove/Replace;
  optional `mode` defaults to Tagged. `pvid` is independent, including with
  Remove. For a PVID-only change leave action, mode and vlans blank. Replace
  changes tagged membership and preserves unrelated untagged membership.
  `replace_untagged=Yes` explicitly requests its replacement with Replace;
  the default is No. Access selects one VLAN and uses inclusion plus PVID,
  retaining access-conversion impact findings. Existing tagging on the selected
  access VLAN is a blocking conflict; no tagging-disable command is generated.
  Proposed tagging of the final PVID is also blocked. Removal retains
  `no vlan tagging X` before `vlan participation exclude X`.
- C3850X VLAN names preserve spaces and case (up to 32 characters), including
  rename proposals and matching-state no-ops. Unsafe delimiters and secret
  markers remain forbidden; other platform name restrictions are unchanged.

These options are shared by API, XLSX and CLI adapters. Review retains input,
evidence and commands; Approve cannot override missing or unverified evidence.

## API and bounded persistence

The catalogue and typed validation live in `v2.catalogue`. `planning.request`,
`plan`, `evaluate_decisions`, `save` and `load` are independent of XLSX and transport.
`observation.collect` uses shared per-device execution, one DeviceSession/CLI,
inventory resolution, InterfaceService, VlanService and family AuditResolver.
The resolver's explicit planning mode uses platform numeric bounds; default
audit/compliance outputs retain their existing numeric semantics. No competing
CLI parser, transport or worker pool is introduced.

Collection persists sanitized results through caller-owned `ResultSpool` sinks
under `outputs/runs/configuration_observation`. Failures retain fixed status
without exception text. These spools remain available for recovery; use the
existing shared spool lifecycle tools to manage retention. The `observations`
iterator supports per-device API consumption. The single-workbook adapter limits
input to 5,000 occupied rows, row positions through 5,002, observation bundles to
16 MiB and canonical plans to 32 MiB. Larger runs should consume the shared spool
per device or use smaller review batches; workers never retain a full-run result
set. Oversized artifacts fail explicitly instead of silently truncating evidence.

Platform bounds include VLANs 1–4094 (EdgeSwitch 1–4093), Catalyst/ME reserved
1002–1005, EVC service-instance IDs 1–4000, NCS540 subinterfaces 0–2147483647,
and NE05E subinterfaces 1–4094. Inputs are not restricted to compliance's
2–4001 range. References used for vendor limits include the
[EdgeSwitch guide](https://dl.ui.com/guides/edgemax/EdgeSwitch_AdminGuide.pdf),
[ME3600X command reference](https://www.cisco.com/c/en/us/td/docs/switches/metro/me3600x_3800x/software/release/15-3_3_S/command/reference/3800x3600xcr/cli2.html),
[ASR920 EVC guide](https://www.cisco.com/c/en/us/td/docs/routers/asr920/configuration/guide/ce/16-12-1/b-ce-xe-16-12-asr920/b-ce-xe-16-11-asr920_chapter_010.html),
and [NCS540 interface guide](https://www.cisco.com/c/en/us/td/docs/iosxr/ncs5xx/interfaces/77x/b-interfaces-hardware-component-cg-77x-ncs540.pdf).

## Validation status

Deterministic fixtures cover all 22 schemas and representative CLI, read-only
collection reuse/cleanup/failure isolation, Manual CLI no-network behavior,
ordering/dependencies, decisions/digests, secret rejection, workbook round trips,
workbook integrity and v1 regressions. Live smoke tests have **not** been run.
Hardware/release-specific operational validation remains operator-controlled.
Conservative conflicts require revised input/re-observation; approval does not
override unknown evidence or migrate existing services automatically.

## Planning progress and diagnostics

The `plan` command flushes each progress line immediately. With
`--max-concurrent-devices 1`, each target completes before the next starts:

```text
Planning run start; reading input workbook
-: run start; targets=2; run_id=<run-id>; spool=<path>; identity=-
192.0.2.10: connect; identity=-
192.0.2.10: identify; identity=-
192.0.2.10: interface collection; identity=<device-id>
192.0.2.10: VLAN/config collection; identity=<device-id>
192.0.2.10: audit/snapshot; identity=<device-id>
192.0.2.10: completed; identity=<device-id>
192.0.2.11: connect; identity=-
192.0.2.11: failed; identity=- (EvidenceCollectionError)
-: run end; completed=1; failed=1; run_id=<run-id>; identity=-
Planning proposals; rows=2; live targets=2
Exporting immutable plan and decision workbook
```

Concurrent runs may interleave device stages; complete console lines use shared
execution progress serialization. Device failure leaves unavailable evidence and
continues safe peers. Manual-only runs show planning/export progress without
connecting. No raw CLI, configurations, credentials or exception messages appear
in progress. Planning/export failures report `PlanningExportError`.

Matching sanitized JSON operational logs use the shared bounded rotating logger:
`outputs/logs/configuration/YYYY-MM-DD/bulk_planning.log` (UTC date, 2 MiB per
file, three backups). Events include run IDs, spool paths, stage lifecycle,
completion counts and export paths/outcomes. Transport owns detailed connection
diagnostics under `outputs/logs/transport/YYYY-MM-DD/transport.log`; planning
logs report safe categories without duplicating lower-layer tracebacks. Failed
exports retain observation spools for diagnosis/recovery.

Interface Description rows retain recognized existing VLAN membership/tagging
inconsistencies as `EXISTING_VLAN_WARNING` findings with original sanitized
finding detail. They permit ordinary offline approval when no material blockers
remain. VLAN/EVC/L2VPN/service requests retain their consistency blockers.
Missing/stale evidence, unknown declarations, identity/interface ambiguity and
ownership conflicts still block description readiness. Audited facts, evidence,
no-op handling and digest-bound review remain unchanged.
