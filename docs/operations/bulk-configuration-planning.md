> **Compatibility reference:** The canonical current guide is [Bulk configuration planning v2](../user_manual/bulk-configuration-planning.md). This operations path is retained for existing links; consult the canonical manual first.

# Bulk configuration planning v2

## Issue #152 policy correction

Disjoint ME3600X/ASR920 EVCs independently derive safe parent setup from observed
state, including empty parents; compatible setup/descriptions require no sibling
approval. Contradictory descriptions, duplicate SIs, ingress overlap, uncertain
state and aggregation ownership still block. Predefined non-Ubiquiti templates
have no VLAN Database approval/synchronization dependencies and never implicitly
create VLANs. Earlier contrary prerequisite statements below are superseded.
EdgeSwitch genuine prerequisites and immutable approval/fresh execution gates remain.
See [current behavior and validation commands](../user_manual/bulk-configuration-planning.md).

Issue #117 adds a separate [confirmed executor](../user_manual/configuration-execution.md)
and [public execution/capability API reference](configuration-execution-api.md).
The no-apply boundary below continues to describe the planning CLI.

The separate `orbitflow.configuration.v2` API implements the 22-template
catalogue from [the approved design](../architecture/configuration/guided-bulk-planning.md).
Existing `orbitflow.configuration` v1 JSON plans, commands, validation and
approval authority remain unchanged.

The [complete template operator reference](configuration-template-reference.md)
enumerates all 22 worksheets, every input column, conditional requirements,
valid/invalid examples, scenario CLI, evidence/fallback and ordered dependencies.
Templates 1-16 have signed-off detailed contracts; 17-22 are provisional catalogue
behavior, not owner-approved or live-validated. All device validation is pending.

This workflow proposes configuration and records offline engineer decisions.
It has no device apply/save/commit/rollback implementation. The 21 predefined
templates collect current read-only evidence. Manual CLI never connects or
claims live or semantic validation, including when approved.

## User-executable workflow index

Run all commands from the repository root with an activated Python environment and
`PYTHONPATH=src`. Operator-provided Teleport routing, credentials and local output
permissions are prerequisites for live read-only operations.

| Task | Entry point | Result / guide |
|---|---|---|
| Create a blank 22-template request workbook | `python -m orbitflow.configuration.v2.cli input bulk-input.xlsx` | Local input XLSX; instructions below |
| Collect read-only evidence and propose bulk changes | `python -m orbitflow.configuration.v2.cli plan bulk-input.xlsx --devices devices.xlsx --max-concurrent-devices 1 --proxy TELEPORT_PROXY --cluster TELEPORT_CLUSTER --bastion-host BASTION --bastion-user BASTION_USER` | Immutable `plan.json` and review `plan.xlsx`; no apply |
| Refresh device inventory | `python scripts/device_inventory_refresh.py devices.xlsx --proxy TELEPORT_PROXY --cluster TELEPORT_CLUSTER --bastion-host BASTION --bastion-user BASTION_USER` | Inventory JSON and Excel; see [README](../../README.md#inventory-refresh-and-full-excel-export) |
| Collect interface and VLAN observation report | `python scripts/device_interface_vlan_report.py devices.xlsx --proxy TELEPORT_PROXY --cluster TELEPORT_CLUSTER --bastion-host BASTION --bastion-user BASTION_USER` | Excel report; see [README](../../README.md#batch-interface-and-vlan-report) |
| Collect VLAN compliance | `python scripts/device_vlan_compliance.py run devices.xlsx --proxy TELEPORT_PROXY --cluster TELEPORT_CLUSTER --bastion-host BASTION --bastion-user BASTION_USER` | Compliance spool/report; see [README](../../README.md) |
| Back up device configuration (sensitive) | `python scripts/device_configuration_backup.py devices.xlsx --proxy TELEPORT_PROXY --cluster TELEPORT_CLUSTER --bastion-host BASTION --bastion-user BASTION_USER` | Date-stamped configuration backups and `failed_devices.xlsx`; see [README](../../README.md#device-configuration-backup) |
| Preview next Codex task | `python scripts/orchestration_v2/controller.py --dry-run` | Non-mutating preview |
| Run one queued Codex task | `python scripts/orchestration_v2/controller.py` | Controller-managed worktree, tests and PR; no automatic merge |
| Watch queued Codex tasks | `python scripts/orchestration_v2/controller.py --watch` | Polling controller; no automatic merge |

The batch commands shown use their documented common flags. Use `--help` to
confirm other supported options on the checked-out revision; do not supply
credentials on the command line. `devices.xlsx` requires
`management_ip`, `username`, `password` and optionally `secret`.
The separate **bulk template input** contains no credentials.

## Operator commands

Run with the repository environment and `src` on the Python import path, as
for the existing configuration CLI:

```powershell
python -m orbitflow.configuration.v2.cli input bulk-input.xlsx
```

Introduction provides a concise quick-start and one directory of all 22 templates,
with platform, function, short purpose and blue underlined worksheet links.
Detailed technical guidance remains in field-header and sheet A1 comments and
the template reference. `Description` is the shortened
worksheet label for Interface Description, keeping names within Excel's
31-character limit. C3850X template sheets resolve the existing inventory
family `C3850` and `c3850_switching` profile. Fill rows beginning at row 3;
header comments identify required fields and examples. Dropdowns describe
actions, encapsulation and modes. Optional blank parent/interface descriptions preserve text. EVC rows recreate the complete child, so blank child settings are omitted.
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
locations; original invalid rows remain with sanitized values, field-specific errors
and empty proposed CLI. Correct those rows
in the source workbook and plan again. Other valid rows continue.

Review rows and Evidence Details contain only requested interface/service/global
objects and required dependency stanzas. Internal sanitized device-wide facts
remain digest-bound for consistency checks. Evidence Details preserves source filenames, one-based line numbers and exact
sanitized excerpts; oversized main-sheet evidence refers there. Templates 10/12 show parent-level source settings and only the requested service-instance child, including applicable terminators; all neighboring services remain in immutable JSON and internal conflict checks. Any individual field exceeding Excel's 32,767-character limit uses a deterministic complete-value reference to `plan.json` with plan digest, workbook field location, character count and value hash. No JSON state or evidence is truncated. These references remain protected during decision consumption. The plan digest
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
`outputs/reports/configuration/YYYYMMDD-HHMMSS_<target>/plan.json` and adjacent
`plan.xlsx`. The timestamp uses local run time. A single unambiguous target uses
its template family and sanitized management IP; mixed/multiple targets use
`multi-device-N` (distinct management IP count), and Manual-only runs use
`Manual-only`. Unsafe characters are replaced and descriptors are length bounded.
Directories are reserved atomically; same-name collisions add `-01`, `-02`, etc.
Folder names are display identifiers only: the full original SHA-256 remains in
JSON and XLSX and continues to bind immutable content and review validation.
Existing digest-path artifacts remain readable without migration; new defaults
do not move old artifacts. Live observation spools remain under
`outputs/runs/configuration_observation/`. The
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
is one hour; API callers may select 1â€“86,400 seconds. Readiness describes the
evaluation timestamp only. No approval authorizes later execution; future apply
requires separate authorization and fresh preflight.

ASR920 proposals use inline EVC binding only and flag existing global bindings.
ME3600X requires the bridge-domain VLAN in the global database, not the outer
ingress tag. NCS540 keeps bridge-group/domain names separate from tags and checks
existing L2 attachment relationships. NE05E requires an existing VSI; no QinQ or
VSI creation is offered. EdgeSwitch tagged removal emits `no vlan tagging`
before participation exclusion; Add/Change includes tagged membership and independently sets optional PVID. EdgeSwitch
database proposals enter `vlan database` from privileged EXEC; its interface
proposals use `configure`. Cisco proposals use `configure terminal`; Huawei
uses `system-view`. None includes save or XR commit.

## Approved inputs (catalogue 2.3)

Regenerate older v2 workbooks and plans. Templates 1-8 retain the Catalyst
contract; Templates 9-16 follow the signed-off ME3600X/ASR920/EdgeSwitch
[contract](../architecture/configuration/approved-me3600x-asr920-edgeswitch-templates.md).
Templates 17-22 have no new detailed approval or validation claim in this change.
V1 plans and authority are unchanged.

- EVC requires `service_instance_id`, `encapsulation` (Untagged/Dot1q/QinQ)
  and `bridge_domain`, independently of ingress VLAN IDs. Tagged matches use
  `outer_vlan`; QinQ requires `inner_vlan`. Inclusive comma/range syntax is
  preserved in CLI and expanded for overlap checks; inner `any` becomes `1-4094`.
  `rewrite` is None, Pop 1 symmetric, Pop 2 symmetric, Push dot1q or
  Push dot1q symmetric. Push requires separate `push_vlan`. Unsupported/untested
  combinations block input; consult sheet A1 comments and the template reference
  for the complete valid/invalid matrix and CLI examples.
- Every EVC row renders `no service instance <ID>` followed by complete child
  recreation, even on a match. Optional child description/rewrite/group blanks
  omit those old settings; `interface_description` blank preserves the parent.
  Existing child deletion/omitted settings are visible impact warnings. Group 0
  is distinct from omission. ME3600X requires trunk + allowed vlan none and a
  global VLAN for the BD at deployment. Missing global VLAN alone warns during planning, retains the ID for future pre-apply checks, and never auto-creates it. ASR920 uses inline BD, without ME switchport setup.
  Confirmed compatible empty parents may initialize; routed/owned/incompatible
  parents block. No implicit admin, MTU, STP or policy changes.
- EdgeSwitch VLAN Port uses `action` Add/Change or Remove, `tagged_vlans`
  (single/comma/range), optional `pvid`, optional `description`. Add/Change
  requires tags and/or PVID; PVID-only includes membership when necessary.
  PVID and tagged may be the same VLAN. Remove requires tags and blank PVID,
  untags before exclusion and blocks removal of the current PVID until an
  earlier approved row changes it. Replace, mode, vlans and replace_untagged
  are rejected; use separate ordered Remove then Add/Change rows. Missing
  global VLAN is informational and never auto-created by this template.
- VLAN Database is one ID/name per row: Cisco 1-4094 excluding 1002-1005,
  ASCII names without spaces up to 32; EdgeSwitch 2-4093 and names with spaces
  up to 32. Operational lookup is preferred; complete reliable running-config
  fallback is labeled. Conflicting observations/unknown state block. Equal
  names no-op; different names rename with impact warning.
- Interface Description changes the exact entered physical/aggregate target,
  including explicitly requested physical members, without changing VLAN/EVC,
  PVID, tagging, MTU or admin state. EdgeSwitch renders quoted descriptions.
  Required inputs and valid/invalid examples are in each worksheet's A1 comment.

Current/Configured/Tagging operational EdgeSwitch facts remain distinct. Full
sanitized parent evidence includes unrelated commands, all Cisco children through
`!`, and EdgeSwitch through `exit`. Service operational Down is informational;
unparseable/rejected detail uses annotated reliable config fallback.

## Issue #100 candidate changes — historical validation notes (verify current merge and live-validation state)

**Branch/version warning (2026-10-14):** The changes below are implemented in
[PR #101](https://github.com/a4212crew/OrbitFlow-Evo/pull/101), **not yet in
`main`**. On `main`, the older blocker and prompt behaviour can still occur.
Use the `codex/issue-100` worktree only for authorised read-only validation.
Do not interpret this section as an assertion that main has been updated.

- A pending VLAN Database prerequisite yields `DEPENDENCY_NOT_APPROVED` as a
  **warning**, and the dependent proposal may be `consistent` with no blocker,
  but stays `deployment_ready=false` until prerequisite approval. The dependency
  references, workbook order and downstream authority checks remain.
- An Interface Description operation overlapping another operation on the same
  interface yields `ORDERED_RESOURCE_OVERLAP_WARNING` for **all supported
  device families**, in either workbook order. Genuine incompatible operations,
  identity/ownership/evidence failures and independent safety blockers are not
  waived. Distinct conflicting description-only requests remain blockers.
- Unsupported Catalyst trunk Add/conversion stays blocked, including
  `ADD_REQUIRES_EXPLICIT_BASELINE` and `TRUNK_CONVERSION_BLOCKED`.
- EdgeSwitch CLI identity now accepts the parenthesised angle-bracket hostname
  formats `(<LAB-ES24>) >` and `(<LAB-ES24>) #`, normalizing the identity to
  `LAB-ES24`, while retaining existing plain/annotated forms. A `>` session
  still needs the existing authenticated privilege transition before read-only
  commands. No SSH host-key or identity check is intentionally bypassed.

**Read-only operator verification:** Generate a fresh input workbook and plan
from the PR worktree, with one C3750X pending VLAN + Access + Description case,
and an unsupported trunk Add case. Inspect both JSON and XLSX: warnings,
dependency links, operation order, `consistency`, `deployment_ready`, and
the retained trunk blockers. Separately include the previously timed-out
EdgeSwitch in the credentials workbook and verify identity resolves, then
inspect inventory/Interface/VLAN/compliance evidence and run a separate
configuration backup if authorised. Do not send any Proposed CLI to equipment.
Keep secrets and raw configuration out of Issues and review screenshots.

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

Platform bounds include VLANs 1â€“4094 (EdgeSwitch 2â€“4093), Catalyst/ME reserved
1002â€“1005, EVC service-instance IDs 1â€“4000, NCS540 subinterfaces 0â€“2147483647,
and NE05E subinterfaces 1â€“4094. Inputs are not restricted to compliance's
2â€“4001 range. References used for vendor limits include the
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

## Milestone 1 owner-controlled read-only smoke test

Templates 1-16 are the signed-off implementation scope. Templates 17-22
remain outside this expansion. Mocked tests do not validate a device. Milestone acceptance remains **pending owner
live testing and explicit sign-off** on representative C3750X and C3850X releases.

Activate the repository Python environment first. Use an operator-managed
credentials workbook outside Git, read-only device credentials and existing
Teleport routing. Replace the example addresses and interfaces with confirmed
lab targets; do not put credentials into the template workbook or commands.

```powershell
$env:PYTHONPATH = (Join-Path (Get-Location) 'src')
python -m orbitflow.configuration.v2.cli --help
python -m orbitflow.configuration.v2.cli input catalyst-m1-input.xlsx
```

Fill these example rows beginning at row 3 on **each** family's four worksheets.
Use C3750X address `192.0.2.10` and C3850X address `192.0.2.11` only as placeholders.
Choose existing full interface names and VLANs for the actual test.

| Worksheet function | Example inputs | Inspect |
|---|---|---|
| VLAN Database | `vlan_id=445`, `name=Customer` | Create/rename/No-op against actual operational name; existing global range evidence |
| Access Port | `interface=GigabitEthernet1/0/1`, `vlan_id=445`, optional description | Full proposal or exact No-op, shutdown retained, missing VLAN warning |
| Trunk Port | `interface=GigabitEthernet1/0/2`, `action=Remove`, `vlans=445` | Explicit list or default ALL, resulting exclusions, service warning |
| Description | `interface=GigabitEthernet1/0/3`, `description=Owner smoke test proposal` | Exact-target description-only proposal; full original stanza |

Add separate runs for Add with/without an explicit baseline, Replace, sequential
range/add/remove statements, native VLAN changes, dynamic/residual/routed modes,
and physical Port-channel members. Access and Trunk members block without redirect;
logical-parent trunks require an explicitly selected, evidenced Port-channel;
retain aggregate conflicts;
descriptions must remain on the entered physical or logical target. C3850X must
never propose an encapsulation selector. C3750X new/conversion trunks include it.
Use an additional invalid row (e.g. VLAN 1002 or abbreviated interface) to verify
same-row field errors, retained input and safe continuation. Conflicting rows
must cite both worksheet row positions. Never deploy the generated proposals.

```powershell
python -m orbitflow.configuration.v2.cli plan catalyst-m1-input.xlsx `
  --devices 'C:\Operator\devices.xlsx' --max-concurrent-devices 1 `
  --proxy TELEPORT_PROXY --cluster TELEPORT_CLUSTER `
  --bastion-host BASTION --bastion-user BASTION_USER
Get-ChildItem outputs/reports/configuration -Recurse -Filter plan.xlsx
```

The command reads identity, interface descriptions, running configuration and
`show vlan id <ID>` through one shared session per target. It does not send
proposed configuration commands. A rejected/unparseable lookup produces
`VLAN_LOOKUP_FALLBACK` only when running-config collection was reliable; failure
of both sources blocks unknown state. Operational lookup text stays internal;
Existing Evidence contains scoped sanitized configuration, original statements
and terminating `!`. Operational inactive/suspended state warns without creating
a missing VLAN. Optional fields left blank preserve current values.

Inspect matching `plan.json` and `plan.xlsx` under
`outputs/reports/configuration/<timestamp>_<target>/`; existing destinations are never overwritten.
Compare the workbook with independently observed read-only configuration. If
needed, the operator can run `show vlan id 445` and
`show running-config interface GigabitEthernet1/0/1` in their own session. Keep
raw secret-bearing output private. The same workbook is the only decision
surface; Pending/Approve/Reject never grants apply authority or rewrites JSON.

Record each device family/model/software release, run digest, test cases,
expected/observed results and owner verdict in an operator-controlled validation
record. Include a multi-row run with a failed device or invalid row and successful
peers. Share sanitized evidence only. Explicitly sign off both families before
marking the Catalyst live-validation milestone complete. Templates 9-16 have
their own signed-off contract and still require independent owner live validation.

## Repeat read-only overlap validation (Issue #91)

Create a fresh input workbook in Windows PowerShell (use a new filename if it exists):

```powershell
$env:PYTHONPATH = "src"
python -m orbitflow.configuration.v2.cli input overlap-input.xlsx
python -m orbitflow.configuration.v2.cli plan overlap-input.xlsx --devices devices.xlsx --max-concurrent-devices 1 --proxy TELEPORT_PROXY --cluster TELEPORT_CLUSTER --bastion-host BASTION --bastion-user BASTION_USER
```

Use operator-owned credentials only in the shared devices input. Replace example
IP `192.0.2.10` with an authorized representative device. Run once for each
C3750X/C3850X family, filling its sheets with full interface names:

| Earlier worksheet/row | Example inputs | Later worksheet/row | Example inputs |
|---|---|---|---|
| Access Port row 3 | management_ip=192.0.2.10; interface=GigabitEthernet1/0/1; vlan_id=445; description=Access text | Description row 3 | same IP/interface; description=Final text |
| Trunk Port row 3 | same IP; existing trunk interface; action=Add; vlans=445 | Trunk Port row 4 | same IP/interface; action=Add; vlans=445,545 |
| Trunk Port row 5 | same IP; a different existing trunk; action=Replace; vlans=445,545 | Trunk Port row 6 | same IP/interface as row 5; action=Remove; vlans=545 |

Choose observed safe interfaces and valid VLANs; Add requires an explicit allowed
baseline. Keep the two trunk scenarios on different resolved resources. To check
physical ownership, use a member name on the earlier trunk row and its evidenced
Port-channel on the later row. Repeat the Access/Description example for four
observed pairs. Sheet order is authoritative; row order applies within each sheet.

Inspect both source rows: `ORDERED_RESOURCE_OVERLAP_WARNING`, `Consistency=consistent`
when no other blockers exist, and immutable JSON overlap details with both exact source
references. Confirm final description is Final text; Access CLI still includes
Access text. Compare each row's JSON projected state and workbook CLI with preceding intent.
Add emits all requested VLANs when needed; Remove is assessed against Replace,
with service-impact warnings preserved. A later complete match is No-op/empty CLI.
Existing Evidence remains the original complete sanitized stanza, including `!`.

Also exercise two differing Description rows, Access/Trunk conflict, unavailable
or stale evidence, missing Port-channel owner, and Add without an explicit baseline.
These remain blocked with `ORDERED_RESOURCE_OVERLAP` where resources overlap.
`ADD_REQUIRES_EXPLICIT_BASELINE` stays blocking even if No-op is true; Error Details
explains that Replace is required. Projected output on a blocked row is an
inspection-only proposal, not deployable state. An unrelated invalid input row
must retain its field errors while valid rows continue.

Default output uses `outputs/reports/configuration/<timestamp>_<target>/plan.json` plus
`plan.xlsx`. Check matching digest and protected source references in both artifacts.
Edit only Pending/Approve/Reject in this workbook; decisions do not authorize device
writes. No second review artifacts or review command exist. Rejection re-evaluates
remaining projected intent in memory and does not alter the immutable JSON.

Record device family, observation time, artifact paths/digest, each tested row and
owner assessment of evidence, CLI, No-op, warnings/blockers and final projection.
Explicit owner sign-off after these repeated read-only runs is required before
milestone 1 completion. Do not send proposed configuration to devices.


## Templates 9-16 owner read-only validation pending

Use authorized representative ME3600X, ASR920 and EdgeSwitch releases, the
shared operator-owned credentials input and the planning command above.
Never paste generated configuration back to a device. Read-only checks:

- ME3600X/ASR920: collect full `show running-config` through `end`, and
  `show ethernet service instance id <ID> interface <INTERFACE> detail`.
  Confirm the actual ID/interface headings, fixed/list/range and QinQ/any
  encapsulations, rewrite ethertype annotation/symmetry, BD/group zero,
  explicit scoped absence and Up/Down output. Unrecognized detail layouts
  deliberately use a labeled config fallback. No alternate commands are guessed.
- ME3600X: `show vlan id <ID>`; verify present/inactive/absent/rejected lookup,
  global BD VLAN warnings and explicit database dependencies, compatible empty-parent initialization, normal
  trunk/access/routed/physical-member blockers and unrelated-child retention.
- EdgeSwitch: `show vlan <ID>` plus full `show running-config`. Verify VLAN
  headers/names/absence, inclusive lists, full interface exit, excluded+tagged
  facts and Current/Configured/Tagging tables. Current differences alone do not
  change configured intent. Unknown table layouts remain evidence; planning
  uses reliable config facts. Test Add/Change tags, PVID-only, tagged=PVID,
  absent database informational warnings, ordered PVID change then Remove,
  and description-only physical/LAG targets.
- Inspect both artifacts for original input/evidence, destructive recreation
  and omitted-setting warnings, exact CLI, row references/dependencies,
  stale/unknown blockers and protected digest-bound Pending/Approve/Reject.
  Existing matching EVC still recreates; matching DB/description/membership
  no-ops produce no CLI. No apply, save or commit is available.

All new syntax is deterministically tested only. Hardware forwarding behavior,
release-specific rewrite support, empty-parent setup, service-detail command
variants, default VLAN naming and EdgeSwitch firmware/table variants have not
been independently live validated. Unsupported rewrite combinations fail closed;
embedded quote/backslash input is rejected rather than guessing CLI escaping.
Owner validation and explicit merge approval remain required. No new approval
or firmware support is claimed for Templates 17-22.

### Issue #94 output and evidence revision

Regenerate plan workbooks for the revised output layout. Templates 1–16 display original inputs plus Existing Evidence, Proposed CLI, Live Validation, Consistency, Dependencies, No-op, Validation Status, Error Details, Warnings, Blockers and Engineer Decision. The seven removed detail columns remain digest-bound in immutable JSON; Templates 17–22 retain their columns. Only Pending/Approve/Reject cells may be edited. Protected input/result cells, exact worksheet order and sheet/row decision identity are still verified against regenerated output and the trusted plan digest.

EdgeSwitch VLAN Port and Description on the same interface are compatible in either sheet order without a Pending approval dependency solely for that pair. Existing PVID-removal, ownership, unknown-state and conflicting-intent blockers remain. Port evidence omits global VLAN declarations and show vlan output; database facts still supply warnings internally. ASR920 evidence labels per-interface/per-ID reliable absence separately from unavailable/error lookup and preserves relevant parent settings. Missing ME3600X BD VLAN alone is a warning, with missing IDs retained in JSON for future pre-apply checks; no implicit VLAN creation occurs.

These revisions have deterministic offline coverage. Operator-controlled read-only validation of both EdgeSwitch sheet orders, ASR920 absence/error responses and ME3600X missing-VLAN plans remains required on deployed hardware/firmware. No apply/save workflow is introduced.

EVC ingress conflicts retain the blocking `INGRESS_TAG_OVERLAP` code. The plan
workbook's Error Details identifies the management IP, canonical physical
interface, requested and conflicting service-instance IDs and normalized ingress
selectors. Projected conflicts also identify the originating sheet and row.
Immutable plan JSON carries these explanations and structured `ingress_conflicts`;
review remains bound to the complete plan digest. Resolve the conflicting intent
and regenerate the plan before review; approval cannot bypass this blocker.

On ASR920, independent service instances with disjoint ingress on an existing
compatible physical interface can be reviewed independently even when it has no
EVCs yet (`no ip address` and `shutdown` are supported). Active L3 addressing and
incompatible ownership still block. Shutdown is preserved. Explicit shared parent
description changes retain ordering. ME3600X still requires trunk mode and allowed
VLAN none, with sequencing and approval dependencies for initial conversion.
No device apply is provided.

Independent ASR920 EVC services on an address-free parent (including a shutdown
parent with no existing EVC) may be reviewed separately. Sharing a bridge domain,
including repeated BD 1237, does not create an ordering warning or approval
dependency for distinct SIs with disjoint ingress. Parent descriptions and actual
parent conversions retain ordered review; same-interface ingress overlaps and
duplicate SI intent remain blocked. ME3600X initial trunk conversion still
requires its parent-initialization dependency. Planning preserves shutdown state.


### Issue #149 / PR #150 owner revision (2026-10-25)

The earlier child-to-parent trunk redirect and broad compatible-stanza merge
language is superseded. Confirmed physical child forwarding requests block with
`NOT_ALLOW_ON_CHILD_PORT_CHANNEL`; select the logical parent explicitly instead.
Descriptions remain exact-target. EdgeSwitch completed member stanzas (addport
alone or with the explicitly recognized auto-negotiate attribute) preceding a
completed settings stanza contribute relationship evidence only; the subsequent
settings stanza supplies consistency input. Repeated actual settings remain ambiguous,
missing settings remain unknown, and actual observed duplicates still block.
Original ordered facts/source lines and all addport commands are retained.
Preparation independently rejects historical approved redirects; fresh execution
rechecks ownership. Historical codes/artifacts remain readable without bypassing
current safety. Approval, digest, backup, transport and verification gates persist.
See [owner validation matrix](../user_manual/aggregation-validation.md).
Deterministic regression evidence does not establish live-device acceptance.

The 06:01 UTC owner reproduction is covered by the narrow shared selector:
`auto-negotiate` plus `addport 3/1`, then `exit`, precedes separate completed
`0/49` settings. Only those later settings supply description/VLAN consistency;
all original evidence remains ordered. Unknown or security-relevant commands are
not member metadata. Multiple actual settings or missing closure fail closed.
Typed legacy snapshots with contradictory/malformed bindings also require ownership
review. Planning, preparation/fresh target checks and post-change verification use
the same selector; no approval/digest or spool schema changes. The forwarding child
blocker remains `NOT_ALLOW_ON_CHILD_PORT_CHANNEL`. See the existing validation
matrix for Linux/Windows read-only reproduction; live validation remains pending.
