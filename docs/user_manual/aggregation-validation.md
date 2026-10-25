# Shared aggregation ownership: Issue #149 validation

This is a read-only owner acceptance procedure. Automated synthetic fixtures do
not establish live device support. Run from the repository root in the installed
Python environment, with an authenticated Teleport profile and a locally protected
approved device workbook. Replace example routing and paths with local values.
Keep credentials and raw backups outside Git. No device writes are part of this
procedure. Existing console report/compliance/planning entries call these same
services; no additional menu or confirmation is introduced.

## Expected behavior and public contracts

`VlanState.aggregation` is an optional `AggregationSnapshot`, appended with a
`None` default for positional/API compatibility. Vendor adapters derive sanitized
aggregation from the full configuration already collected for VLAN observation;
VlanService supplies resolved device/platform/family/time metadata. Interface
reporting reuses a complete capture. If unavailable/incomplete, its existing
independent AggregationService read-only command remains available. No global
cache or second relationship parser exists in the workflow layers.

`AggregationSnapshot.owner(name)` returns a canonical confirmed physical parent
or `None`; it never manufactures a parent from a reference. `display_name()`
preserves an actual heading; EdgeSwitch `lag N` and `3/N` join once, preferring an
actual `lag N` heading when both were captured. Bindings, completeness, problems,
configuration command, original headings and sanitized stanzas remain available.
Logical aggregate subinterfaces are separate from physical children.

EdgeSwitch compliance `Interface`, `Config Interface` and `Configuration Owner`
show the actual saved `lag N` heading, including when InterfaceService observes
the parent as `3/N`. Canonical joining retains one parent row and independently
observed admin/oper state; the finding's `observed.interface_name` retains `3/N`.
Without a captured `lag N` heading no such display name is fabricated. The
interface/VLAN report continues to show its observed `3/N` name. Offline export
uses recorded display values, so older retained spools keep their original names.

`evaluate_vlan_compliance(context, interfaces, vlans, policy, ...)` and
`resolve_methodologies(context, interfaces, vlans, ...)` keep their signatures.
They consume shared aggregation and retain family forwarding validation. Older
Python callers/observation spools carrying typed configuration facts but no
aggregation use the shared parser on their preserved headings/excerpts. Such
legacy snapshots cannot prove complete or empty membership; affirmative
relationships remain usable. New collected partial/failed captures cannot prove
standalone ownership or silently pass. Empty/missing evidence remains unknown.

Confirmed physical children remain in Interface Results with Type
`Child Port-Channel`, status `not_applicable`, no missing required VLANs, a reason
naming the parent, and Configuration Owner set to its actual heading. Parent
required-VLAN policy is unchanged. Configuration Health and conflict findings are
independent: a skipped child can still have `wrong_configuration`. ME3600X actual
pseudowire interface rows are excluded only from VLAN compliance; service/BD,
methodology, configuration evidence and other workflow observations remain.

The compliance columns and spool schema remain compatible. Offline export
preserves the recorded result and never reclassifies historical rows. Existing
planning v1, v2 approval/digest checks, execution confirmation and transport/
spooling ownership remain in place. V2 observations optionally persist the shared
aggregation payload; older observation payloads remain readable.

## Exact collection and offline export commands

Linux Bash (the two collection commands are separate runs):

```bash
export PYTHONPATH="$PWD/src"
python scripts/device_vlan_compliance.py run outputs/devices.xlsx --proxy teleport.example.net:443 --cluster example-cluster --bastion-host example-bastion --bastion-user example-user --teleport-key-path "$TELEPORT_KEY_PATH" --teleport-cert-path "$TELEPORT_CERT_PATH" --keep-spool --methodology-report
python scripts/device_interface_vlan_report.py outputs/devices.xlsx --proxy teleport.example.net:443 --cluster example-cluster --bastion-host example-bastion --bastion-user example-user --teleport-key-path "$TELEPORT_KEY_PATH" --teleport-cert-path "$TELEPORT_CERT_PATH"
# Substitute the retained compliance run directory printed by collection.
python scripts/device_vlan_compliance.py export outputs/runs/vlan_compliance/RUN_ID outputs/reports/vlan_compliance/recovered.xlsx --keep-spool
python scripts/device_vlan_compliance.py export outputs/runs/vlan_compliance/RUN_ID outputs/reports/vlan_compliance/methodology-recovered.xlsx --methodology-report --keep-spool
# A retained interface report spool is available after output failure.
python -c "from orbitflow.reporting import export_report_spool; print(export_report_spool('outputs/runs/interface_vlan_report/RUN_ID', 'outputs/reports/interface_vlan/recovered.xlsx', cleanup=False))"
```

Windows PowerShell:

```powershell
$env:PYTHONPATH = (Join-Path (Get-Location) 'src')
python scripts/device_vlan_compliance.py run .\outputs\devices.xlsx --proxy teleport.example.net:443 --cluster example-cluster --bastion-host example-bastion --bastion-user example-user --keep-spool --methodology-report
python scripts/device_interface_vlan_report.py .\outputs\devices.xlsx --proxy teleport.example.net:443 --cluster example-cluster --bastion-host example-bastion --bastion-user example-user
python scripts/device_vlan_compliance.py export .\outputs\runs\vlan_compliance\RUN_ID .\outputs\reports\vlan_compliance\recovered.xlsx --keep-spool
python scripts/device_vlan_compliance.py export .\outputs\runs\vlan_compliance\RUN_ID .\outputs\reports\vlan_compliance\methodology-recovered.xlsx --methodology-report --keep-spool
python -c "from orbitflow.reporting import export_report_spool; print(export_report_spool('outputs/runs/interface_vlan_report/RUN_ID', 'outputs/reports/interface_vlan/recovered.xlsx', cleanup=False))"
```

Expect `Interface Results`, `Database Results`, `Run Errors`, `Details` in the
compliance workbook, a separate methodology workbook when requested, and
`Interfaces`, `VLAN_Database`, `Run_Errors` in the interface report (conditional
Configuration_Evidence overflow sheet). Compare original and recovered values,
health, owners and source evidence. Do not expect an older spool to acquire new
child-skipping behavior. For intentionally interrupted spools add `--allow-partial`
to compliance export; inspect missing devices and Run Errors. Failed/invalid
rows must not erase successful devices. Normal successful interface export may
clean its spool; do not recollect merely to recreate a deleted spool.

For planning, prepare reviewed synthetic/lab requests using the existing
[planning guide](bulk-configuration-planning.md). Keep the resulting workbook
Pending; do not invoke execution confirmation. Exact read-only plan examples:

```bash
python -m orbitflow.configuration.v2.cli plan outputs/aggregation-input.xlsx outputs/reports/configuration/aggregation-plan.json --devices outputs/devices.xlsx --proxy teleport.example.net:443 --cluster example-cluster --bastion-host example-bastion --bastion-user example-user --teleport-key-path "$TELEPORT_KEY_PATH" --teleport-cert-path "$TELEPORT_CERT_PATH" --max-concurrent-devices 1
```

```powershell
python -m orbitflow.configuration.v2.cli plan .\outputs\aggregation-input.xlsx .\outputs\reports\configuration\aggregation-plan.json --devices .\outputs\devices.xlsx --proxy teleport.example.net:443 --cluster example-cluster --bastion-host example-bastion --bastion-user example-user --max-concurrent-devices 1
```

Use a new output path for each plan; existing destinations are not overwritten.

## Owner family matrix (pending on both Linux and Windows)

Inspect already-existing lab configuration; this procedure never asks an operator
to create or change a LAG. Where a case is unavailable, record Not tested.

| Family | Relationship and evidence checks | Forwarding/compliance checks |
|---|---|---|
| C3750X | Gi/GigabitEthernet and Po/Port-channel aliases, down child, empty parent | Parent trunk/database policy unchanged; wrong child VLAN retained as conflict; child skipped |
| C3850 | Same alias/down/empty checks, exact owner evidence | Existing mode/ALL policy; access child blocker and trunk redirect to parent in v2 |
| ME3600X | channel-group under actual physical stanza, absent/contradictory parent | Parent SI/inline/global BD mappings retained; child conflict independent of skip; pseudowire rows absent only in compliance |
| ASR920 | Multiple parents/down members, no operational count inference | EVC/QinQ/SI-to-BD validation and mapping evidence unchanged |
| NCS540 | BE/Bundle-Ether aliases, bundle id, down children, bundle subinterfaces | Actual l2transport-to-BD attachment/encapsulation validation; no VLAN inference from suffix/name |
| Huawei VRP NE05/NE05E | GE aliases, Eth-Trunk/eth-trunk physical binding, no Local/Partner duplicates | Existing trunk/termination/VSI safeguards and child-service consolidation |
| EdgeSwitch | addport 3/N or lag N, heading lag N vs observed 3/N, zero members | Exactly one compliance parent with Interface/Config Interface/Configuration Owner = actual lag N; admin/oper state matches observed 3/N; physical children retain skip reason, conflict health and evidence; interface/VLAN report still shows 3/N |

For each family also inspect missing parent, contradictory and truncated captures
using sanitized offline fixtures (never induce production capture failure), LAG
subinterfaces, non-LAG interfaces and database results. No interface may be
created from only a service/BD/VSI reference. Down state cannot remove a child.

## Compatibility workflow matrix

| Workflow | Owner read-only review | Deterministic coverage |
|---|---|---|
| Inventory/interfaces | Refresh an approved target and compare real identity/state | inventory and interface capability tests |
| Interface/VLAN reporting | Compare all forwarding fields, schemas, evidence and errors; verify no duplicate full-config capture for complete collection | aggregation, VLAN capability, reporting tests |
| Compliance/methodology | Verify child skip + independent health, exact source lines, unchanged non-LAG/database results | aggregation consumers, VLAN audit/compliance, methodology tests |
| Planning v1/v2 | Offline v1 validation; v2 read-only plans for access child block, trunk owner redirect, description exact target, conflicts and uncertain owners | configuration plans, bulk v2, approved templates/services tests |
| Execution | Review prepared targets/confirmation gates offline only; no confirm/apply command | configuration execution, stages, performance and observation timing tests |
| Backup | Use approved read-only backup workflow; compare protected capture behavior without publishing raw output | configuration backup tests |
| Console | Existing report/compliance/methodology/planning entries, per-run concurrency, error recovery | operations menu tests |
| Spool/transport | Offline exports while disconnected; mixed successful/invalid devices, retained failed output, older spools | result spool, reporting/compliance and transport regressions |

## Automated commands

Run these same commands in Bash or PowerShell after setting PYTHONPATH as above:

```text
python -m pytest tests/test_aggregation.py tests/test_aggregation_consumers.py tests/test_vlan_configuration_audit.py tests/test_vlan_compliance.py tests/test_vlan_capability.py tests/test_device_reporting.py -q
python -m pytest tests/test_methodology_standards.py tests/test_methodology_relationships.py tests/test_bulk_configuration_v2.py tests/test_approved_catalyst_templates.py tests/test_configuration_v2_approved_services.py tests/test_configuration_execution.py -q
python -m pytest -q
```

The development log records actual automated outcomes. Linux execution and owner
live validation of Issue #149 remain pending; automated fixtures are synthetic.

For PR #150's display correction, use the Bash or PowerShell collection and
offline export commands above against the same approved EdgeSwitch target.
Compare the original and recovered `Interface Results` parent and child rows
against the EdgeSwitch matrix entry, then compare the separate report's
`Interfaces` row named `3/N`. Review missing-heading cases with deterministic
fixtures only; do not alter device configuration to produce them. This revision
has no new live validation evidence.

## PR #150 operator-column correction (2026-10-25)

Owner-reported workbooks contained 167 confirmed child rows with matching
parents and not_applicable status; this is reported evidence, not independent
live validation of this revision. Membership, owner headings and child skips
remain unchanged.

The resolver compares ME3600X explicit source switchport mode/native/access and
allowed-list intent before EVC-derived bridge-domain values can be confused with
those controls. Missing comparable controls on a partially configured member
require further evidence; services need not be duplicated onto physical members.
Parent service binding, database and required-VLAN checks remain independent.
Child database findings are emitted only from that child's own explicit commands,
never copied from parent-owned allowed lists or services.

For EdgeSwitch, source-ordered participation exclusion makes residual tags
inactive; EXCLUDED_VLAN_TAGGING_INACTIVE is informational and does not impair
configuration health. Include after exclude reactivates membership. Tags lacking
valid membership without an explicit effective exclusion remain
TAGGED_VLAN_NOT_IN_MEMBERSHIP, including participating VLANs absent from the
database. Explicit member/parent tagging differences still produce conflicts.
Neither a shutdown flag nor an empty/default LAG alone authorizes suppression.
Configured tags and source evidence remain available in both reports.

Sanitized expected-row comparison (other columns/schema unchanged):

| Source shape / row | Before | After |
|---|---|---|
| ME parent trunk allowed none + valid EVC BDs; child matching trunk allowed none | Child conflict from EVC versus switchport VLAN comparison | Child not_applicable, healthy; owner Port-channel1; parent BDs/policy unchanged |
| Same ME parent; child explicit allowed 445 or access mode | Conflict with generic recommendation | Conflict retained; explanation names differing controls/values; recommendation compares controls without copying EVC services |
| ME child trunk mode only, parent has allowed none | Partial evidence could appear as resolved mismatch | Child skip retained; incomplete forwarding evidence finding requests missing participation evidence |
| Edge lag 1 excludes 545 and retains tagging 545 | Compliance wrong_configuration; methodology informational | Both retain EXCLUDED_VLAN_TAGGING_INACTIVE; compliance healthy if no independent errors |
| Edge includes 545 but DB lacks 545 | Invalid membership/tagging | Both errors retained; no compliance pass |
| Edge physical child explicitly differs from lag 1 | Aggregate conflict | Conflict retained with actionable field/value detail; child skip unchanged |

Repeatable owner review: run the exact Bash or PowerShell read-only collection
and offline export commands above using the same approved input workbook.
Use fresh output/run paths and retain the spool. Compare original and recovered
Configuration Findings, Explanation, Recommendation, Type, Status, Configuration
Owner and Configuration Health. Check source excerpts/lines against protected
local captures. Do not publish captures or workbooks containing management
identities. Counts should match for the same input/configuration; investigate
collection errors before comparing counts. Offline exports preserve recorded
findings and do not recompute old spool semantics.

| Repeat check | Expected result |
|---|---|
| ME3600X matching controls + parent services | No conflict solely from child absence of EVC BDs; parent missing-VLAN/service findings retained |
| ME3600X explicit mode/native/allowed mismatch | Specific conflict, child skip, correct owner and evidence; no child-service duplication recommendation |
| ME3600X partial or missing/contradictory relationship | Further evidence/review, no invented owner or silent compliance pass |
| EdgeSwitch excluded/default LAG | Informational only for explicitly excluded tags; actual lag N heading, one row |
| EdgeSwitch active invalid tagging or child mismatch | Error retained independently of required-VLAN status |
| C3750X/C3850, ASR920, NCS540, Huawei | Repeat family matrix above; compare non-LAG/database, forwarding/service findings and ownership |
| All compatibility workflows | Repeat compatibility matrix above; execution reviewed offline only, no device writes |

The existing console entries and API signatures remain unchanged. This correction
adds no operator workflow or menu. Automated fixtures are synthetic; repeat owner
validation and Linux execution remain pending.

## Summary and overflow review checks

This is export/presentation validation; live owner validation remains pending.
The family/workflow matrix and exact read-only collection commands above still
apply (C3750X, C3850, ME3600X, ASR920, NCS540, Huawei VRP, EdgeSwitch). No device
writes are needed. Existing console commands and planning/execution interfaces
are unchanged.

Linux Bash automated and offline checks (repository root):

```bash
export PYTHONPATH="$PWD/src"
python -m pytest tests/test_vlan_compliance.py tests/test_aggregation_consumers.py tests/test_vlan_configuration_audit.py -q
python -m pytest -q
python scripts/device_vlan_compliance.py export outputs/runs/vlan_compliance/RUN_ID outputs/reports/vlan_compliance/summary-review.xlsx --keep-spool
```

Windows PowerShell equivalents:

```powershell
$env:PYTHONPATH = (Join-Path (Get-Location) 'src')
python -m pytest tests/test_vlan_compliance.py tests/test_aggregation_consumers.py tests/test_vlan_configuration_audit.py -q
python -m pytest -q
python scripts/device_vlan_compliance.py export .\outputs\runs\vlan_compliance\RUN_ID .\outputs\reports\vlan_compliance\summary-review.xlsx --keep-spool
```

Replace RUN_ID with the retained run directory. Use the collection commands above
only with owner-approved target workbooks and local Teleport authentication;
then disconnect before offline export. Add `--allow-partial` only to inspect a
known partial run and inspect Run Errors. Do not distribute credentials or raw
unsanitized device output.

1. For each family, check one parent and confirmed child: owner/skip appears once,
   child remains not_applicable and independent conflicts retain wrong_configuration.
   Check long invalid VLAN lists give bounded counts/ranges and actionable source
   review, with exact VLAN lists/comparisons in Details `observed` JSON. Compare
   parent-owned findings separately; partial evidence must still request review.
2. Check EdgeSwitch inactive excluded tagging remains informational; a genuine
   tagging mismatch remains independently wrong_configuration. Verify ME3600X
   source service evidence remains preserved and pseudowires stay excluded only
   from compliance rows. Compare methodology findings using its separate export.
3. Short Explanation/Recommendation/evidence values stay inline. For an overflow
   reference use its Input Position, Finding and exact column-name Field. Sort
   Part as numbers and concatenate JSON Fragment without adding newlines. Compare
   with the sanitized persisted value. Use distinct inputs/findings, even when
   their device IPs repeat. Lowercase `observed`/`evidence` fragments parse as JSON
   and preserve exact lists and source lines. No cell exceeds 30,000 characters.
4. Re-export the retained spool again while disconnected and compare all sheet
   values. Confirm sheet/column order, normal non-LAG/database results, errors,
   evidence and historical spool recovery remain unchanged. Export does not
   recollect devices, apply policy anew or alter planning/execution approval.

Automated fixtures cover multi-device/multi-finding Explanation, Recommendation
and Configuration Evidence overflow with exact fragment reassembly; short cells,
pre-split sanitation, nearly 4,000 invalid child VLANs, skipped children with genuine
mismatches, partial relationships, inactive tagging and offline spool recovery.
They are deterministic tests, not live validation.


## Planning/execution child-target safety — owner decision, not yet implemented

The owner has approved this future safety invariant: **never change access or
trunk forwarding configuration on a physical Port-channel/LAG member**. A
child-targeted Access Port, Trunk Port or equivalent VLAN Port change must be
blocked even if the shared aggregation snapshot confirms a parent; it must not
silently redirect to the logical parent. If the operator wants to configure the
logical parent, the request must explicitly select that parent. Unresolved or
partial ownership evidence must fail closed for forwarding changes. This is
**not yet the verified behavior of every planning/execution template**.

At PR #150's reviewed head, Catalyst planning rejects an Access Port request
on a known child but can resolve a Trunk Port request from the child to the
parent; fresh Catalyst execution may accept the approved resolved parent after
ownership checks. EdgeSwitch VLAN Port already has a separate child-ownership
blocker. These legacy safety decisions must not be described as retired until
Codex changes implementation and deterministic regressions prove the new rule.

Operator acceptance matrix for a subsequent authorized code revision (read-only
plans and offline preparation only; **never run confirm/apply**):

| Requested target | Requested operation | Expected future decision |
|---|---|---|
| Confirmed physical child | Access Port | Block; no commands/deployment readiness |
| Confirmed physical child | Trunk Port | Block; no redirect or commands/deployment readiness |
| Confirmed EdgeSwitch physical LAG child | VLAN Port access/tagging/PVID change | Block; no redirect or commands/deployment readiness |
| Independently selected logical Port-channel/LAG | Supported forwarding operation | Evaluate normally with full evidence and approval guards; no automatic authorization |
| Physical interface with missing/contradictory/partial LAG ownership | Access/trunk forwarding change | Fail closed, request evidence |
| Confirmed physical child | Interface Description | Preserve existing exact-target description contract; not a forwarding change |
| Standalone physical interface | Supported access/trunk change | Evaluate existing family-specific requirements |

Both Windows PowerShell and Linux Bash may validate the *existing* current
planning implementation without apply using the read-only `python -m
orbitflow.configuration.v2.cli plan` examples earlier in this manual. After any
Codex policy revision, validate each matrix row with sanitized planned inputs,
inspect blockers, `resolved_target`, rendered commands and deployment readiness,
then review fresh execution-target safety in deterministic tests only. Never use
an owner production device to manufacture a Port-channel membership conflict.


### Approved blocker naming and EdgeSwitch description-stanza regression (2026-10-25)

For future child-targeted access, trunk and VLAN-forwarding operations, report
`NOT_ALLOW_ON_CHILD_PORT_CHANNEL` consistently in planning and fresh execution,
without retargeting the operation to the logical aggregate. This is owner-approved
future behavior, **not yet implemented** in the current PR source.

Owner plan row: `EdgeSwitch Description` worksheet row 4 (`0/17`, intended
`OrbitflowTest`) currently returns `INTERFACE_ABSENT_OR_AMBIGUOUS`,
`unresolved`, even though InterfaceService observes exactly one `0/17` and
`AggregationSnapshot` confirms parent `lag 2`. Saved config contains two
complementary `interface 0/17` stanzas, one for `addport 3/2` and one for
interface properties; duplicate source headings are **not** duplicate physical
interfaces. V2 planning counts raw fact stanzas, and execution's fresh check also
rejects more than one declaration. Correct both checks through canonical identity
and merged compatible evidence, retaining fail-closed handling of actually
contradictory declarations or ambiguous/missing observed interfaces.

Expected future read-only validation: description-only `0/17` resolves to
itself, consistency `consistent` with no duplicate-stanza blocker, existing
aggregate/VLAN configuration conflict remains a non-blocking warning for the
description request, and an unapproved Pending decision remains
`deployment_ready=false`. No CLI execution should be used to validate this
change until deterministic planning and fresh-execution tests pass. Independently
selected logical aggregates remain distinct from physical members.
