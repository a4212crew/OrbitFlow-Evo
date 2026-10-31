# Interface and VLAN report — operator manual

**Script:** `scripts/device_interface_vlan_report.py`. **Purpose:** collect read-only interface and VLAN facts from approved Excel targets and produce an Excel report.

## Prerequisites and safety
Run from the repository root with Python 3.11+, installed `requirements.txt`, `PYTHONPATH=src` if required, and an authenticated `tsh` profile. The input workbook contains approved device targets; credential material must not be committed. Provide all four required Teleport routing options: `--proxy`, `--cluster`, `--bastion-host`, `--bastion-user` (strings). Linux Teleport key/certificate file paths may be required; supply `--teleport-key-path` and `--teleport-cert-path` (optional paths, default unset). No script here performs configuration apply.

## Inputs and defaults
Required positional `excel_path` (Excel file) and the four Teleport routing strings. Optional `--teleport-key-path` and `--teleport-cert-path` (paths, unset); `--inventory-path` (`data/inventory/inventory.json`); `--reports-dir` (`outputs/reports/interface_vlan`); `--log-root` (`outputs/logs`); `--spool-root` (`outputs/runs/interface_vlan_report`); `--config` (`orbitflow.toml`).

## Examples
Linux:
```bash
python scripts/device_interface_vlan_report.py outputs/devices.xlsx --proxy teleport.example.net:443 --cluster example-cluster --bastion-host example-bastion --bastion-user example-user --teleport-key-path "$TELEPORT_KEY_PATH" --teleport-cert-path "$TELEPORT_CERT_PATH"
```
Windows PowerShell:
```powershell
python scripts/device_interface_vlan_report.py .\outputs\devices.xlsx --proxy teleport.example.net:443 --cluster example-cluster --bastion-host example-bastion --bastion-user example-user
```
## Expected outcomes
Creates report output in `outputs/reports/interface_vlan` by default; device failures may be isolated rather than aborting every target. Inspect workbook for interface/VLAN observations and run/error records. Input or run-level errors print `Interface/VLAN report failed. Check application logs and retained run spool.` Detailed report sheet contract remains in the [main executable reference](../../README.md#batch-interface-and-vlan-report). No device configuration changes.

## Interactive console adapter (Issue #123)

This workflow is also available through `python -m orbitflow.menu`; see the [console manual](interactive-operations-console.md) for environment profile, target workbook selection, per-run concurrency, confirmation and output/recovery behavior. Direct CLI flags and service contracts remain supported. Default `orbitflow.toml` execution loading now prefers validated shared profile pacing when present; explicit alternate config files retain their semantics.

Console target selection (Issue #123 revision): after choosing a device workbook, choose all (blank) or unique comma-separated nonempty device row numbers, counted from 1 after the header. Only selected rows are dispatched; concurrency is still prompted every run. See the [console guide](interactive-operations-console.md) for cancellation and fixed actionable failure diagnostics. Direct CLI input selection is unchanged.

## Full-range VLAN rendering and offline recovery (Issue #142)

The existing `Interfaces`, `VLAN_Database`, and `Run_Errors` sheets and original
fields are preserved; Issue #147 adds the three LAG columns described below. In Tagged VLANs and wholly numeric Bridge Domains lists,
consecutive canonical IDs in 1–4094 are rendered as inclusive `a-b` ranges
(runs of at least three). Ordering and duplicate IDs are preserved; numeric
runs are never sorted or merged across intervening values. Mixed named domain
lists remain literal. `ALL`, `NONE`, and blank remain distinct.

Service Mappings uses `identity(a-b)` **only** for consecutive exact pairs:
`identity(2-4094)` expands to `2 -> 2; 3 -> 3; ...; 4094 -> 4094`.
This is a pairwise identity range. Other mappings (including nonidentity,
named services, inner-tag expressions and untagged mappings) remain literal.
For the IOS trunk allowed VLANs `2-4094`, native VLAN `445`, the report shows:

- Untagged VLAN: `445`
- Tagged VLANs: `2-4094`
- Bridge Domains: `445, 2-444, 446-4094`
- Service Mappings: `untagged -> 445; identity(2-4094)`

These are presentation rules over normalized capability data; they do not
change the observation, infer new relationships, or remove the native VLAN
from a normalized tagged list. Expand ranges in order to recover the exact
original lists and identity pairs. Existing normalization rules, including
omission of VLAN 1, are unchanged.

A completed retained spool, including an older spool with expanded strings and
status `output_failed`, can regenerate without Teleport, credentials or device
connections. Run from the repository root, replacing `RUN_ID` with the actual
retained run directory name. Linux:

```bash
export PYTHONPATH=src
python -c "from orbitflow.reporting import export_report_spool; print(export_report_spool('outputs/runs/interface_vlan_report/RUN_ID', 'outputs/reports/interface_vlan/recovered.xlsx', cleanup=False))"
```

Windows PowerShell:

```powershell
$env:PYTHONPATH = 'src'
python -c "from orbitflow.reporting import export_report_spool; print(export_report_spool('outputs/runs/interface_vlan_report/RUN_ID', 'outputs/reports/interface_vlan/recovered.xlsx', cleanup=False))"
```

Public API: `export_report_spool(spool_path, path, *, cleanup=True,
allow_partial=False) -> pathlib.Path`. Paths accept strings or Path objects.
Default `cleanup=True` removes the spool after successful output; use
`cleanup=False` while validating recovery. Default `allow_partial=False`
requires completed collection. `allow_partial=True` explicitly permits an
incomplete collection and retains its spool. Regeneration streams one outcome
at a time and preserves failed-outcome rows in `Run_Errors`.
The interactive console's existing report recovery action uses this same export
path; no new menu action is required.

Compaction also applies during export of older rows. Any remaining cell over
32,767 characters raises `ValueError` identifying sheet, row, column letter and
character count, without exposing its contents. Nothing is silently truncated;
the spool is retained and any existing destination workbook is preserved. Such
fields require investigation using the protected local spool before retrying.

## Validation commands

Linux automated tests:

```bash
PYTHONPATH=src python -m pytest -q tests/test_device_reporting.py tests/test_vlan_capability.py tests/test_result_spool.py tests/test_production_paths.py
```

Windows PowerShell automated tests:

```powershell
$env:PYTHONPATH = 'src'
python -m pytest -q tests/test_device_reporting.py tests/test_vlan_capability.py tests/test_result_spool.py tests/test_production_paths.py
```

For offline validation, run the recovery command above, inspect the expected sheets,
expand the compact ranges, and compare against the retained local spool. For the
owner's 699-outcome case, confirm all 699 outcomes remain accounted for and the
seven failed outcomes retain their error records; partial capability failures
may also retain interface rows. Confirm native VLAN 445 and every service pair
on the affected trunk.

For live read-only validation, use the Linux or Windows collection command in
**Examples** above with operator-approved targets and actual routing options.
Inspect the same fields and error records. This issue's automated fixtures are
synthetic; owner spool recovery remains operator-controlled. Current Issue #147 Windows
automated results and owner live evidence are distinguished below.

## Shared progress presentation (Issue #144)

See [CLI progress and durable results](cli-progress.md) for interactive and redirected
output, phase-specific counters, saved paths, partial/interrupted/export-failure
semantics and the coverage table (including specialist/lifecycle exemptions).
Device/workflow semantics and existing arguments are unchanged. Deterministic
terminal fixtures are separate from pending owner-operated Linux/Windows validation.

## LAG relationships (Issue #147)

The same direct CLI and Interface & VLAN Reporting console Run/recovery actions
now observe explicit aggregation bindings. Seven approved family templates:
C3750X IOS, C3850 IOS-XE, ME3600X IOS, ASR920 IOS-XE, NCS540 IOS-XR,
Huawei VRP and Ubiquiti EdgeSwitch. No new flags or configuration writes.
Inventory family selection and session/transport ownership remain unchanged.

`Interfaces` has 17 columns: the original 14 plus `LAG`, `LAG Relationship`,
`LAG Member` immediately after `Interface`. Full order: Device Name, Device IP,
Platform, Device Family, Interface, LAG, LAG Relationship, LAG Member,
Description, Admin Status, Oper Status, Port Type, Untagged VLAN, Tagged VLANs,
Bridge Domains, Service Mappings, Collection Time. Parent rows show `Yes`, `Parent`,
physical member names exactly as spelled/cased in source `interface ...`
configuration headings, separated by commas. Child rows show `Yes`, `Child`,
the base parent name from its source configuration heading. `Interface` remains
the InterfaceService spelling; canonical IDs still own all joins and references.
If a heading is unavailable, the displayed canonical ID is explicitly marked
`[canonical fallback: configuration heading unavailable]`. Compatible repeated
stanzas share one canonical identity; the lexicographically smallest actual
heading is selected deterministically, with every original header retained in
sanitized evidence. Conflicting bindings remain unknown. Standalone and aggregate subinterface rows have
three blanks. Down/shutdown members remain members. A confirmed empty parent
has blank members; incomplete configuration shows `Unknown` on parent rows and
an `aggregation` error. If that capability fails completely, the LAG columns
remain blank and `Run_Errors` records the stage/category; those blanks are not
proof of standalone status. Other successful capability output survives.
`VLAN_Database` and `Run_Errors` columns are unchanged. Actual InterfaceService
identities still own report rows; service-only references create no rows.

The collector runs `show running-config` on Cisco/EdgeSwitch or
`display current-configuration` on Huawei using the existing shared CLI. It
recognizes `channel-group`, `bundle id`, `eth-trunk` or `addport 3/N` in physical
interface stanzas. Operational summary tables, active counts, descriptions and
LACP health are not membership sources and are not collected in this revision.
A complete configuration terminator (`end` or `return`, or balanced EdgeSwitch
`configure`/`exit` contexts) is needed to prove empty membership; incomplete output and conflicting bindings retain fixed
problem categories without guessing. Missing parent identities are not created
from bindings. EdgeSwitch observed default `3/N` parents do not imply explicit
operator provisioning. Live firmware/format acceptance remains owner-owned.

### Evidence lookup and overflow

Open the comment/note on the `Interface` cell (column E). Each view lists stable
`run-id:input-position:canonical-interface` evidence references. Parent views
reference the base parent, all configured aggregate subinterfaces and physical
members. Child views reference their own stanza and base parent only; siblings
and aggregate subinterfaces are excluded. Logical subinterfaces reference their
own stanza and remain outside physical membership. Find the matching ID in an
Interface comment's `Evidence store`; each selected sanitized stanza is stored
once, usually beside its own real interface. Related stanzas with no observed
row are stored beside the first referencing interface. Original headers and
nested EVC/QoS/service settings remain present after credential sanitization.

If any projection or evidence store exceeds 32,767 characters, comments point
to the conditional consolidated `Configuration_Evidence` sheet. Its columns
are `Device Name`, `Device IP`, `Interface`, `Evidence ID`, `Evidence Part`,
`Total Parts`, `Configuration Evidence`. For each Evidence ID, order by integer
Evidence Part, verify parts 1..Total Parts, then concatenate Configuration
Evidence **without adding separators**. Chunks are at most 30,000 characters
and reconstruct the complete sanitized stanza. A very large reference list also
uses chunks, with an Evidence ID ending in `:references`; reconstruct it the
same way to obtain the comma-separated stanza IDs. Stanzas occur once per device
in the spool and once in the workbook evidence store. Ordinary reports retain
three sheets. Non-evidence overflow still fails atomically, retaining the spool
and previous destination workbook. Existing offline recovery commands above
preserve evidence and never reconnect. Old three-element/14-column spool rows
remain readable and export with three blank LAG columns.

### Python API

`orbitflow.capabilities.aggregation.AggregationService(*, timeout=30,
clock=None).collect(session, context, *, cli=None, interfaces=())` returns an
`AggregationSnapshot`. `timeout` is seconds per command; clock optionally returns
an aware datetime. A resolved DeviceContext is required; no discovery is done.
`interfaces` supplies already-observed InterfaceRecords, including empty/default
parents. Supplying a shared CLI borrows it; omission owns a temporary vendor CLI
and leaves the transport session with the caller. Unsupported platforms/families,
unavailable/rejected configuration and transport failures raise exceptions;
reporting isolates these as aggregation-stage errors. This API performs no apply.

Snapshot fields: device_id, platform, device_family, collection_time (ISO text),
configuration_command, complete, parents, bindings (physical child/base parent),
subinterfaces (logical/base parent), evidence (canonical name/sanitized full
stanza), problems (fixed nonfatal categories), configuration_names (canonical
ID/source-heading display pairs, default empty for older payloads). Identities are canonical join
keys, not inferred operational health. `fields(name)` gives the three report
values; `display_name(key)` returns the recorded heading or qualified fallback;
`references(name)` gives ordered evidence keys for that view.
`build_rows(context, interfaces, vlans, aggregation=None)` still returns
`(interface_rows, database_rows)`; callers should use INTERFACE_COLUMNS rather
than fixed numeric offsets. `None` preserves the preexisting call signature
with blank LAG values. `run_report` arguments and Path result are unchanged.
The report spool retains its first three payload lists and adds an optional
fourth normalized snapshot. Spools are internal recovery artifacts; use
`export_report_spool` rather than modifying their records.

### Automated and owner live validation

Run from repository root with installed requirements. Focused automated tests:

```bash
PYTHONPATH=src python -m pytest -q tests/test_aggregation.py tests/test_device_reporting.py tests/test_result_spool.py tests/test_operations_console.py tests/test_shared_cli.py
PYTHONPATH=src python -m pytest -q
```

Windows PowerShell:

```powershell
$env:PYTHONPATH = 'src'
python -m pytest -q tests/test_aggregation.py tests/test_device_reporting.py tests/test_result_spool.py tests/test_operations_console.py tests/test_shared_cli.py
python -m pytest -q
```

Full-suite validation covers existing interface/VLAN, audit/compliance, planning
v1/v2, backup, inventory, shared execution, transport and CLI/API consumers.
Synthetic tests do not establish live firmware compatibility. The owner-run
evidence and remaining validation limits are recorded below. No devices were contacted by
Codex. After review, the owner can run the following read-only collection with
an owner-controlled workbook containing representative approved targets, after
operator-controlled `tsh` authentication. Substitute routing and key/certificate
paths locally; never commit the workbook or raw logs.

Linux:

```bash
export PYTHONPATH=src
python scripts/device_interface_vlan_report.py outputs/lag-validation-devices.xlsx --proxy teleport.example.net:443 --cluster example-cluster --bastion-host example-bastion --bastion-user example-user --teleport-key-path "$TELEPORT_KEY_PATH" --teleport-cert-path "$TELEPORT_CERT_PATH"
```

Windows PowerShell:

```powershell
$env:PYTHONPATH = 'src'
python .\scripts\device_interface_vlan_report.py .\outputs\lag-validation-devices.xlsx --proxy teleport.example.net:443 --cluster example-cluster --bastion-host example-bastion --bastion-user example-user
```

Expect the timestamped report under outputs/reports/interface_vlan and concise
per-stage progress. Compare membership with operator-known explicit bindings
on each family, including down members and observed empty parents; compare
aggregate subinterfaces separately. Check aliases, parent/child evidence IDs,
full EVC/QoS preservation, secret redaction and unchanged VLAN database/service
mappings. Include a safely unreachable test target to verify device isolation;
inspect aggregation-stage errors before interpreting blank fields. Verify
console Run uses the same columns and retained-spool recovery reproduces them
without reconnecting. Overflow reconstruction is covered synthetically; no
production configuration should be enlarged to trigger it. Record family,
firmware, expected/observed counts and sanitized pass/fail only. No raw PuTTY
logs, tokens, keys or credential-bearing evidence belong in Issues/PRs.
Legacy audit/planning/execution aggregation remains available for separately
owner-operated compatibility tests; it has not been retired or reinterpreted.

### Aggregate forwarding and identity joins

Each aggregate row carries its **own** five normalized VlanService fields:
Port Type, Untagged VLAN, Tagged VLANs, Bridge Domains and Service Mappings.
Reporting never copies physical children's forwarding data onto an aggregate,
or propagates aggregate forwarding data onto children. Missing observations
remain blank; configured-empty/excluded-only states retain capability semantics.
For EdgeSwitch, configuration `interface lag 2` joins an observed `3/2` row;
`Interface` still displays `3/2`, while a child's `LAG Member` displays `lag 2`
when that is the actual base-parent source heading. Physical `0/2` stays separate.

| Observation | LAG | LAG Relationship | LAG Member |
|---|---|---|---|
| Complete populated base parent | Yes | Parent | Physical source-heading names, comma-separated |
| Complete zero-member base parent | Yes | Parent | Blank |
| Incomplete base-parent membership | Yes | Parent | Unknown |
| Explicit physical child, including down/shutdown | Yes | Child | Base-parent source heading |
| Standalone or aggregate subinterface | Blank | Blank | Blank |
| Aggregation capability unavailable | Blank | Blank | Blank; inspect Run_Errors |

`canonical_interface_name(platform, name, *, normalize_aggregation=False)`
provides the aggregate alias join only when explicitly enabled, as reporting
and AggregationSnapshot do. Default legacy MAC/audit/planning keys are unchanged.
Duplicate canonical InterfaceService or VlanService observations, even identical
ones, raise sanitized `ValueError` rather than overwrite. Batch reporting records
stage `normalize`, category `ValueError`; that device contributes no normalized
interface/database rows, while other devices continue. Compatible repeated
configuration evidence stanzas are handled separately and are not duplicate
capability observations.

### Collection failures and recovery

`Run_Errors` columns remain Device IP, Device Name, Stage, Error Category, Time.
A successful batch has a header-only error sheet. Review errors before treating
blank LAG cells as standalone or a blank member list as confirmed empty.
Aggregation categories include `AggregationConfigurationRejected`,
`AggregationConfigurationUnavailable`, `AggregationParserUnsupported` and
`AggregationConfigurationIncomplete` (ValueError subclasses). Transport/CLI
failures retain their categories. Other successful capability observations survive
an aggregation failure; a normalize failure prevents unsafe joins for that device.

FASTPATH supports balanced configure/interface/VLAN/line/access-list/policy/class
contexts and a trailing EXEC prompt. `service unms` and its key setting are global
commands, not nested sections; the final `exit` closes `configure` after inner
sections close. XR final `end` may be indented. Unknown sections, missing closures,
truncation and contradictory relationships remain incomplete/Unknown.

Export is atomic: output failure preserves the destination workbook and retained
spool. Use the offline recovery commands above without recollecting devices.
OneDrive cleanup permission denial was previously reported; real lock resolution
has not been confirmed. Existing bounded retry and cleanup-only manifest safety
remain. A cleanup-started run cannot be replayed as a completed spool; preserve
retained artifacts for protected local inspection rather than deleting unknown files.

### Verified evidence and remaining owner acceptance (2026-10-24)

The owner-supplied private workbook
`device_interface_vlan_report_20261024T113249_512594Z.xlsx` has the expected
17-column Interfaces schema, observed physical and aggregate forwarding data,
and header-only Run_Errors (zero reported run-stage errors). This establishes
owner-operated batch completion without recorded errors for the tested input.
It does **not** establish individual acceptance of all seven platforms, all service
constructs, or universal firmware/transport compatibility. The workbook remains
private and must not be uploaded with raw logs or credentials.

Earlier owner runs included aggregation failures and a separate EdgeSwitch
1.9.2-lite shared-CLI paging timeout. The later successful workbook supersedes
the blanket claim that all live validation is pending; it does not disprove that
timeout or prove every firmware shape. NCS540 service-specific behavior and
per-platform/construct acceptance still require direct owner validation. Linux
commands are supported but were not run during this Windows revision. Overflow
reconstruction, contradictory/partial output and spool retry/atomicity have
synthetic coverage; the latest workbook alone does not prove these edge cases.

At implementation head `98d6e20`, Codex reported Windows full-suite validation:
`$env:PYTHONPATH = 'src'` then `python -m pytest -q`: **3,214 passed in 246.33s**.
Atlas did not independently rerun that suite. This documentation-only revision
does not change executable commands or claim a new full-suite run. Use the exact
focused/full commands and owner read-only Linux/Windows commands above for
repeat validation. Compare each aggregate's five forwarding fields with its own
configuration, plus physical members, empty versus Unknown, source headings,
subinterfaces, evidence and unchanged VLAN_Database; record family/firmware and
sanitized expected/observed results. Do not enlarge production configuration to
trigger evidence overflow.

### Legacy dependency and compatibility boundary

`src/orbitflow/compliance/resolvers.py::AuditResolver.aggregates` and family
resolver paths remain active for VLAN audit/compliance, aggregate parent/member
VLAN inheritance and conflict findings, and configuration planning. The new
AggregationService observes relationships for reporting; it is not a replacement
for audit/planning. No legacy resolver, public CLI/API or configuration execution
workflow is retired, replaced or reinterpreted. Planning v1/v2, audit/compliance,
backup, inventory, execution, transport and existing consumers retain regression
coverage in the full suite. Owner-operated cross-workflow compatibility testing
remains separate; any retirement requires a future owner-authorized Issue and
compatibility proof. Merge requires separate explicit owner approval.

## Shared aggregation ownership (Issue #149)

See [shared ownership and validation](aggregation-validation.md) for child compliance
skipping, original parent headings, unchanged family forwarding checks, public
model compatibility, exact Bash/PowerShell collection and offline export commands,
and the pending owner family/workflow acceptance matrix.


### Fresh collection and retained evidence (2026-10-31)

Continue using the existing Excel inputs, columns and selections. Every normal
collection execution contacts its requested devices again in a distinct run;
prior observations do not repair a failed current collection. Inventory exports
retain explicitly labelled latest-known stable facts after failure. Deliberate
offline export/recovery uses only the selected historical run, without reconnecting;
planning binding, age, trust and authorization restrictions still apply.
See the [audit and owner validation steps](../operations/issue-162-processing-audit.md#fresh-collection-contract-revision-2026-10-31).
