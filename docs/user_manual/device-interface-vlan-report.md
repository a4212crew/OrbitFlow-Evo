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

For offline validation, run the recovery command above, inspect the three sheets,
expand the compact ranges, and compare against the retained local spool. For the
owner's 699-outcome case, confirm all 699 outcomes remain accounted for and the
seven failed outcomes retain their error records; partial capability failures
may also retain interface rows. Confirm native VLAN 445 and every service pair
on the affected trunk.

For live read-only validation, use the Linux or Windows collection command in
**Examples** above with operator-approved targets and actual routing options.
Inspect the same fields and error records. This issue's automated fixtures are
synthetic; owner spool recovery, Windows execution and live-device validation
remain operator-controlled and are not claimed as performed.

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
`LAG Member` immediately after `Interface`. Parent rows show `Yes`, `Parent`,
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
Synthetic tests do not establish live firmware compatibility. Owner live
validation is **pending for all seven families**. No devices were contacted by
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

### First Windows console run revision (2026-10-24)

Owner reported a completed 147-device Windows console export (concurrency 5):
5,384 interface rows, 8,295 VLAN database rows and 96 aggregation errors
(95 EdgeSwitch, one NCS540). Existing observations survived; this run does
not validate the failed aggregation stage. No production transcript is stored.

The revised parser accepts a trailing EXEC prompt after a balanced FASTPATH
`configure`/interface/VLAN `exit` export and an indented XR final `end`.
Missing outer exits, unsupported nested section layouts and truncated stanzas
remain unknown; the parser does not guess closures from a returned prompt.
Explicit member bindings and sanitized parent/child evidence survive incomplete
collection. Supporting operational tables are still not collected.

`Run_Errors` retains its schema, with safe aggregation categories:
`AggregationConfigurationRejected` (recognized CLI rejection),
`AggregationConfigurationUnavailable` (empty response),
`AggregationParserUnsupported` (unsupported family/platform or unrecognized
configuration shape), and `AggregationConfigurationIncomplete` (missing closure,
duplicate/contradictory/malformed relationships). Fixed parser problem labels
are recorded in sanitized diagnostics; raw configuration is never an error
message. These exception types subclass `ValueError` for existing callers.
Other transport/CLI errors retain their existing categories.

The new fixtures are constructed firmware-shaped examples, **not sanitized
captures of the failed live responses**. Minimal sanitized beginning/end snippets
are still required to establish the actual EdgeSwitch nested/trailing sections
and NCS540 termination shape. The two source-level fixes are not confirmation
of the live root causes. Repeat owner read-only validation using the Linux and
Windows commands above, or `python -m orbitflow.menu` > Interface & VLAN Reporting
> Run, select the approved workbook and concurrency 5. Expect existing interface,
VLAN database and service mappings to remain intact; all six observed EdgeSwitch
default parents remain visible, and XR down physical members remain children
while bundle subinterfaces have blank LAG fields. Complete supported configuration
must have no aggregation error; partial output must retain an error and unknown
parent membership, never a false empty list. Revised live validation is pending.

The reported OneDrive permission-denied cleanup is **deferred**, not confirmed
completed. The exported workbook is valid. Existing bounded retries and retained
cleanup-only manifest protection are unchanged; deterministic permission-injection
tests cover file/lock/manifest/final-directory denial and later cleanup. No real
OneDrive lock was reproduced. Preserve the retained run for owner inspection and
when ready, the existing `orbitflow.result_spool.cleanup_stale_runs(root, *,
before)` API accepts the spool root and a timezone-aware datetime cutoff and
returns removed run paths (leased, malformed or unrelated runs are skipped); a cleanup-started run cannot be replayed as a complete spool. Do not delete
unknown files or bypass the spool safety checks.

Revision automated commands (repository root; no devices required):

```bash
PYTHONPATH=src python -m pytest -q tests/test_aggregation.py tests/test_operations_console.py tests/test_device_reporting.py tests/test_result_spool.py
PYTHONPATH=src python -m pytest -q
```

```powershell
$env:PYTHONPATH = "src"
python -m pytest -q tests/test_aggregation.py tests/test_operations_console.py tests/test_device_reporting.py tests/test_result_spool.py
python -m pytest -q
```

Console regressions exercise the real report service, shared execution, borrowed
CLI, aggregation parser, sanitized spool and workbook export for complete and
partial EdgeSwitch/XR configurations; inventory/interface/VLAN observations and
transport responses are deterministic substitutes. They do not validate firmware
or production connectivity. Legacy audit/planning/execution remains unchanged.

Revision Windows automated results: full suite 3,173 passed; subsequent focused
four-file suite 246 passed (including the four new console cases); final
parser-only check 55 passed. Linux commands are documented but were not run in
this Windows workspace. These results do not confirm the failed live firmware
shapes or revised owner live acceptance.


### Configuration-heading display revision (Issue #147 / PR #148)

`LAG Member` now uses configuration-heading names across all seven families,
including `Port-channel1`, `GigabitEthernet1/0/41`, `Bundle-Ether1`,
`Eth-Trunk1` or `lag 2` only when that spelling actually occurs in the source.
No name is inferred from a description or operational display. Aggregate
subinterfaces remain separate. Existing spools without heading metadata remain
exportable; their already-recorded cells are preserved.

FASTPATH completeness recognizes balanced `configure`, interface, VLAN database,
line console/telnet/ssh, IP/IPv6 access-list, policy-map and class blocks.
Compatible repeated interface sections are combined without losing headers or
marking collection incomplete solely for repetition. Unknown block layouts and
contradictory bindings still require review; this is not universal FASTPATH
syntax support. No legacy audit/planning/execution processing changed.

Run the automated and Linux/Windows read-only commands above. In the resulting
workbook compare every parent/child `LAG Member` label directly with the referenced
sanitized configuration heading, including case and abbreviation. Verify the
`Interface` column and row counts match the original InterfaceService output.
For alias repeats, check the selected label exists in evidence and both original
headers survive. Owner live validation remains pending for all seven families.


Final naming-revision automated validation (Windows PowerShell):
`$env:PYTHONPATH = 'src'` then `python -m pytest -q` completed with **3,198 passed**
(243.53 seconds). This includes all seven source-heading/export cases, fallback,
repeat/alias/conflict checks, console integration, overflow/spool recovery and
legacy interface/VLAN/audit/planning/backup/inventory/execution/transport tests.
These synthetic results do not confirm owner live firmware compatibility.
