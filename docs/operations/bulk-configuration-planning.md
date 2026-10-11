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
python -m orbitflow.configuration.v2.cli plan bulk-input.xlsx outputs/runs/configuration/example/plan.json --username OPERATOR --proxy TELEPORT_PROXY --cluster TELEPORT_CLUSTER --bastion-host BASTION --bastion-user BASTION_USER
```

The command prompts privately for the device password and optional enable
secret. Optional arguments are `--config`, `--inventory-path`,
`--teleport-key-path` and `--teleport-cert-path`. API callers may supply separate
in-memory `DeviceCredentials` per IP. Manual-only workbooks need none of these
connection arguments and trigger no password prompts or target connections.

Outputs are an exclusively created immutable JSON plan and an adjacent XLSX
review workbook. The workbook retains input columns, original entered values,
sheet order and row positions. It adds internal row IDs, sanitized configuration
evidence, proposed CLI, timestamp, validation/consistency status, dependency IDs,
findings, no-op status and Pending/Approve/Reject. Summary includes invalid row
locations; unsafe invalid input text is deliberately omitted. Correct those rows
in the source workbook and plan again. Other valid rows continue.

Evidence Details preserves source filenames, one-based line numbers and exact
sanitized excerpts; oversized main-sheet evidence refers there. The plan digest
binds the sanitized observation, facts, device identities, original inputs,
source-workbook SHA-256, catalogue version, ordering, proposals and decisions.
It is not a hash of a raw device backup.

Edit only Engineer Decision cells, then import into a **new** output path:

```powershell
python -m orbitflow.configuration.v2.cli review outputs/runs/configuration/example/plan.json outputs/runs/configuration/example/plan.xlsx outputs/runs/configuration/example/reviewed.json --actor ENGINEER
```

All populated cells and sheet order are checked against the original plan.
Changing input, evidence or proposed CLI requires a new planning run. Review
re-evaluates evidence age and dependencies from the original snapshot. Rejecting
a prerequisite blocks dependent rows and changes the digest. Pending rows may
remain in a saved revision; the authority records that revision as pending.
Resolved review revisions get a signed digest-bound record, including retained
rejected rows. A record of completed review does not mean every row was approved
or that conflicts were resolved.

Authority defaults to `data/configuration/v2`, separately from v1. Use
`--authority` and `--expires-hours` (1–168, default 24) to override. Protect its
SQLite database and signing key with OS access controls. Actor labels are audit
metadata, not authenticated identities. Whole-store rollback is not prevented.

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

## API and bounded persistence

The catalogue and typed validation live in `v2.catalogue`. `planning.request`,
`plan`, `review`, `save` and `load` are independent of XLSX and transport.
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
signed authority and v1 regressions. Live smoke tests have **not** been run.
Hardware/release-specific operational validation remains operator-controlled.
Conservative conflicts require revised input/re-observation; approval does not
override unknown evidence or migrate existing services automatically.
