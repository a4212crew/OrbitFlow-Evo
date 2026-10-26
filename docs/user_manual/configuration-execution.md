# Approved configuration execution

Issue #154 / PR #155 parent initialization correction (2026-10-26):

ME3600X Template 10 assigns trunk/allowed-none setup once, to the first applicable
proposed EVC row per device/canonical parent in workbook order, including an
all-Pending plan. Later compatible proposals omit both commands; an observed
initialized parent needs neither. Proposed CLI is immutable and digest-bound:
Pending/Approve/Reject changes never reassign setup. Later independent rows may be
approved alone, but require the proposed parent setup to have actually succeeded
or the parent to be initialized independently. Pending/Rejected proposals are not
execution evidence. `PROPOSED_PARENT_SETUP_PREREQUISITE` makes this sequencing
requirement visible without an approval dependency.

The additional ME3600X parent-readiness/drift execution gate is removed. Execution
never inserts, deletes or reallocates CLI. If setup was skipped or failed, later
rows send only their own approved commands under the remaining safety checks;
actual device rejection is recorded and stops that row. Unknown/lost synchronization
stops device writes without blind retry. Identity, ownership, ingress/child drift,
VLAN prerequisites, backup, explicit confirmation, partial save and presence-only
EVC verification remain. ASR920 behavior is unchanged. Synthetic tests do not
establish owner-controlled lab validation, which remains pending.


Issue #117 implements the [approved execution contract](../architecture/configuration/approved-device-execution.md).
This is a configuration-changing workflow for predefined C3750X, C3850 (worksheet
label C3850X) and EdgeSwitch VLAN Database, supported port and Description templates.
Issue #154 adds ME3600X Templates 9–11 and ASR920 Templates 12–13 (owner lab
validation pending). Other families and Manual CLI execution remain unsupported. v1 and v2 planning
commands retain their existing behavior. Owner C3750X/EdgeSwitch validation of PR #118
was reported. Following merged PR #126 (2026-10-18), the owner validated ordered template-stage execution on C3750X and EdgeSwitch: 36/36 selected rows verified, both device saves reported Saved, 10 planned rows skipped, and 131.5 seconds end-to-end including report export. The preceding owner lab run took approximately 277.9 seconds; this single-run comparison is indicative, not a controlled benchmark. C3850, Linux, exhaustive error-path live validation and independently complete rotated timing logs remain outstanding.

Use the repository Python environment (Python 3.11+, `requirements.txt`) with `src`
on `PYTHONPATH`. Authenticate Teleport interactively and check `tsh status` first.
Linux requires the active Teleport key/certificate through the existing transport;
Windows retains the existing local forwarding transport. Device credentials come
from a separate protected `devices.xlsx` (`management_ip`, `username`, `password`,
optional `secret`); never put credentials in the plan or review workbook.

## Inputs and confirmation

### ME3600X and ASR920 (Issue #154)

ME3600X uses IOS/`me3600x_evc`; ASR920 uses IOS-XE/`asr920_evc`.
Supported functions: ME3600X VLAN Database (9), EVC (10), Description (11),
ASR920 EVC (12), Description (13). Existing v2 planner/workbook schemas and
CLI options apply. The console **Execute Approved Plan** action uses the same
service, concurrency selection and single independent execution confirmation.

EVC rows replace the complete child using exact approved remove/recreate commands,
even for matching instances. Forwarding may be interrupted; old optional child
settings omitted from the specification are removed. Review omitted-settings evidence.
Fresh checks reject incompatible parents, unresolved ownership, ingress overlap,
unknown/duplicate children, operational contradictions and target-child changes
(`SERVICE_INSTANCE_DRIFT`). ME3600X planning requires trunk/allowed-none or proposed empty-parent setup;
execution retains the freshly present BD VLAN requirement
(`VLAN_PREREQUISITE_UNAVAILABLE` otherwise). This is an execution prerequisite,
not a VLAN Database approval dependency or implicit creation. ASR920 uses inline
BDs and rejects conflicting global binding evidence.

The child drift comparison is conservative: retained child command settings and
ordering must match the reviewed observation; reordered settings require review
and a fresh plan rather than silent acceptance.

Owner-approved revision (2026-10-26): Templates 10 and 12 use fresh operational
service-instance **presence** verification through `VlanService.service_detail`.
A validated `present` result must identify the exact requested ID and normalized
associated interface. Up and Down both pass; Down is informational. The report
says **Presence verified** and retains operational detail. This does not prove
encapsulation, rewrite, BD, descriptions, preservation or forwarding health.
Reliable absence or contradictory ID/interface fails; timeout, CLI error and
missing/incomplete/ambiguous detail are Unknown. Apply-command rejection still
fails independently. No configuration-tree fallback can establish EVC success.
Fresh pre-apply configuration, ownership, prerequisite and drift gates remain;
other templates retain their existing configured-intent verification. Scoped
running-config pre/post evidence is still retained, including nested `!` output.
Partial-save, unknown-after-send, no retries/rollback/resume and offline recovery
follow the existing lifecycle below. Outputs remain the execution XLSX, durable
per-row pre/post/command evidence and journal in the run, separate protected backups
and sanitized configuration logs; no full backup is copied into XLSX/logs.

Owner lab procedure: use the Linux/Windows `execute` commands below with lab-only
artifacts and credentials. Cover all five templates, create and matching/different
child recreation, untagged/dot1q/QinQ, push/pop, group 0, preserved shutdown/MTU/
policies/siblings, and supplied descriptions. Inspect skipped decisions, responses,
verification and save independently. Test drift/missing-VLAN and controlled rejection/
disconnect only in the lab: expect Failed versus Unknown, safe independent-row
continuation, one partial save when EXEC remains usable and no retry. Disconnect,
then run the offline `report` command below and compare retained outcomes. Keep
the full run and backups. Owner-reported ME3600X lab finding (2026-10-26):
14 selected rows, seven VLAN/description rows verified; seven EVC command sequences
returned and save reported Saved, but `service=False` falsely failed those rows.
Positive detail was reported for Gi0/7 SI 445 and 545. Those historical outcomes
remain immutable. Do not replay completed changes. The revised verifier and ASR920
owner lab validation remain pending.

Deterministic checks (no device access), from the repository Python environment:

```bash
export PYTHONPATH="$PWD/src"
python -m pytest tests/test_configuration_execution_evc.py tests/test_configuration_execution.py tests/test_configuration_execution_stages.py tests/test_configuration_execution_performance.py tests/test_configuration_v2_approved_services.py tests/test_bulk_configuration_v2.py tests/test_operations_console.py tests/test_vlan_capability.py -q
```

```powershell
$env:PYTHONPATH = "$PWD/src"
python -m pytest tests/test_configuration_execution_evc.py tests/test_configuration_execution.py tests/test_configuration_execution_stages.py tests/test_configuration_execution_performance.py tests/test_configuration_v2_approved_services.py tests/test_bulk_configuration_v2.py tests/test_operations_console.py tests/test_vlan_capability.py -q
```

The revision has Linux synthetic test evidence; Windows commands are supplied for
owner/CI use. Earlier Windows evidence remains historical. No production or unattended changes are authorized.

Read-only owner validation after the revision (Linux and Windows): first preserve
the original plan, run directory, backups and report. Offline report regeneration
reads the journal without changing historical outcomes:

```bash
export PYTHONPATH="$PWD/src"
python -m orbitflow.configuration.execution_cli report outputs/runs/configuration_execution/ORIGINAL_RUN outputs/reports/configuration_execution/historical-copy.xlsx
```

```powershell
$env:PYTHONPATH = "$PWD/src"
python -m orbitflow.configuration.execution_cli report outputs/runs/configuration_execution/ORIGINAL_RUN outputs/reports/configuration_execution/historical-copy.xlsx
```

Replace ORIGINAL_RUN with the retained run directory. Expected: recovered XLSX
with the original Failed/Verified/Unknown and Saved outcomes, without reconnection
or reclassification. A missing/corrupt journal fails; do not execute again to
recover a report.

For a fresh presence check, use an owner-controlled lab session with the existing
[transport/validation caller](live-validation.md#cisco-terminal-width-issue-114),
resolved context and borrowed CLI. This is read-only and performs no apply/save:

```python
from orbitflow.capabilities import VlanService
from orbitflow.vendors.interface_names import canonical_interface_name

# Existing operator-owned session/context/cli; use targets from original approved plan.
for interface, sid in [("GigabitEthernet0/7", 445), ("GigabitEthernet0/7", 545)]:
    detail = VlanService().service_detail(session, context, interface, sid, cli=cli)
    print(sid, detail.get("interface"), detail["status"], detail["operational_status"])
    assert detail["status"] == "present"
    assert detail.get("service_instance_id") == sid
    assert detail.get("interface") == canonical_interface_name(context.platform, interface)
```

The examples are the owner-reported ME3600X targets. For ASR920 use its actual
approved interface/ID pairs from retained plan inputs. The capability sends exactly
`show ethernet service instance id 445 interface GigabitEthernet0/7 detail` (and
545 for the second target). Owner CLI sessions on either operating system may run
these same read-only commands directly. Expected: exact ID/Associated Interface,
validated present with Up or Down, safe detail evidence. Missing/ambiguous detail
is Unknown; an explicit wrong target/absence fails. Preserve new validation evidence
separately from historical results. Complete revised live validation remains pending;
any new apply requires separate owner authorization and fresh reviewed artifacts.

Generate the immutable `plan.json` and adjacent review workbook using the
[planning manual](bulk-configuration-planning.md). Change only Engineer Decision
cells to Pending/Approve/Reject. Preserve the original files. Execution validates
the pinned JSON digest, protected workbook cells/dimensions/order, row identities,
decisions and dependencies. Unsupported, blocked, Pending and Reject rows are
listed as skipped. Review intent is unauthenticated and never alone authorizes apply.

`execute` prepares without connecting and renders totals for devices, changes,
no-op rows, skipped rows and concurrency, then one numbered IP/hostname/selected-row
count per device in first-appearance order. A brief warnings/blockers indication
points to preparation findings and configuration logs without listing sources.
One policy line discloses fresh checks, backup before writes, approved execution,
whole-running-configuration save after attempted writes (including partial changes),
and EdgeSwitch management interruption/save answer. Complete intent and findings
remain in digest-bound preparation; no per-row commands or evidence are printed.
It asks `Confirm execution? [y/N]:`; only `y` confirms. Declining opens no connection.

The local confirmation reference binds the exact summary. It is consumed
transactionally before connecting; duplicate confirmation fails without a new run.
The same summary returns the same reference, including after interruption. A changed
plan/selection/settings requires a fresh summary. Confirmation state is a local
replay guard, not authentication, distributed authorization or rollback-proof storage.
Protect `data/configuration/execution/` and retain its database; deleting/restoring
it defeats replay protection. Inspect an interrupted run before preparing new work.

## CLI options

Entry point: `python -m orbitflow.configuration.execution_cli`.

| Command/argument | Type, default and meaning |
|---|---|
| `execute PLAN WORKBOOK` | Required immutable JSON and corresponding reviewed XLSX paths |
| `--expected-digest VALUE` | Required trusted SHA-256 source-plan digest, printed by planning and stored in JSON/Introduction |
| `--devices PATH` | Credentials XLSX, default `devices.xlsx` |
| `--apply-concurrency N` | Positive integer; default **1**, separate from read-only concurrency/TOML |
| `--command-timeout SECONDS` | Finite positive number; default 30; applies to row observation, capture and command exchanges |
| `--save-timeout SECONDS` | Finite positive number; default 300; separate save exchange deadline |
| `--connection-start-interval SECONDS` | Finite nonnegative number; default 1; shared start pacing |
| `--connection-retry-delay SECONDS` | Finite nonnegative number; default 5; shared typed initial-connection retry only |
| `--proxy`, `--cluster`, `--bastion-host`, `--bastion-user` | Required routing strings; no credentials |
| `--teleport-key-path`, `--teleport-cert-path` | Optional paths passed to shared transport; Linux normally supplies active matching identity files |
| `--inventory-path PATH` | Default `data/inventory/inventory.json` |
| `--authority-dir PATH` | Default `data/configuration/execution`; transactional confirmation database |
| `--run-root PATH` | Default `outputs/runs/configuration_execution`; unique shared spool per run |
| `--backups-dir PATH` | Default unset: `RUN/backups/<safe-device-filename>.txt`; explicit PATH uses `PATH/RUN_ID/` |
| `report RUN_PATH OUTPUT.xlsx` | Required retained run directory and new workbook destination; entirely offline; rejects existing output |

There is no `--yes`, HTTP endpoint, rollback, automatic write retry or resume/apply
command. A CLI failure exits 2 with a fixed category and module-log pointer.
Completed runs can contain failed/Unknown rows: inspect their results, not just
the process exit code. `--help` performs no device action.

## Linux example (owner-controlled lab only)

```bash
source .venv/bin/activate
export PYTHONPATH="$PWD/src"
tsh status
python -m orbitflow.configuration.execution_cli execute /secure/change/plan.json /secure/change/plan.xlsx \
  --expected-digest SOURCE_PLAN_SHA256 --devices /secure/devices.xlsx \
  --apply-concurrency 1 --save-timeout 300 \
  --proxy TELEPORT_PROXY --cluster TELEPORT_CLUSTER \
  --bastion-host BASTION --bastion-user BASTION_USER \
  --teleport-key-path /secure/active-key --teleport-cert-path /secure/active-key-cert.pub
# After reading the summary, answer y only for the authorized lab change.
python -m orbitflow.configuration.execution_cli report outputs/runs/configuration_execution/RUN_ID recovered-results.xlsx
```

## Windows PowerShell example (owner-controlled lab only)

```powershell
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH = "$PWD/src"
tsh status
python -m orbitflow.configuration.execution_cli execute C:/secure/change/plan.json C:/secure/change/plan.xlsx `
  --expected-digest SOURCE_PLAN_SHA256 --devices C:/secure/devices.xlsx `
  --apply-concurrency 1 --save-timeout 300 `
  --proxy TELEPORT_PROXY --cluster TELEPORT_CLUSTER `
  --bastion-host BASTION --bastion-user BASTION_USER
# After reading the summary, answer y only for the authorized lab change.
python -m orbitflow.configuration.execution_cli report outputs/runs/configuration_execution/RUN_ID recovered-results.xlsx
```

Replace uppercase routing/digest/run placeholders locally. Inputs use the existing
template schemas; for example C3750X VLAN Database row: management_ip `192.0.2.117`,
vlan_id `445`, name `Customer`, decision `Approve`. Generate artifacts with the
planner rather than hand-authoring result JSON. Protect backup and authority paths
with OS permissions; backups contain sensitive full running configuration.

## Outcomes and recovery

One shared worker owns each IP/session/shell and executes worksheet/row order.
Fresh identity/capability/privilege and state checks plus mandatory protected backup
precede writes. Issue #139 checks fresh target identity and ownership without rerunning planning.
The approved CLI is sent unchanged even when fresh state is already correct. Changes
to commands, no-op classification or projected state from hypothetical fresh planning
are not execution gates; no replacement CLI is generated.
Earlier verified stage changes are observed before subsequent stages; failed dependencies
are Not executed. Missing/unknown requested EdgeSwitch PVID/Include/tagging database
prerequisites block that port row. They never implicitly create VLANs.

Commands are sent individually. Rejection stops that row; bounded vendor
recovery permits safe independent rows to continue. Unsynchronized sessions send no
further commands. A post-send timeout is Unknown, remaining rows are Not executed;
other devices continue. No-op rows still verify against fresh stage facts and send no configuration.
Down operational state does not fail configured-intent verification. Missing facts
produce Unknown, explicit mismatches Failed. Command rejection remains Failed even
if the subsequent observed state matches. Full-set trunk comparison preserves VLAN 1
and ALL/NONE semantics. EdgeSwitch Current, Configured and Tagging remain independent;
tagged/forbidden overlap alone creates no warning or extra lookup.

Save runs once after attempted configuration, including partial changes if the
session remains usable; wholly no-op/skipped tasks do not save. `write memory`
persists **all running configuration**, including unrelated pending changes.
EdgeSwitch can interrupt management; only its recognized save question is answered
`y`. Return to the exact session-validated privileged EXEC anchor means Saved, without
requiring `[OK]`; explicit errors are recorded separately. Saved is not independent
proof of startup persistence. Timeout/disconnect before prompt return means Unknown;
there is no blind retry. Row verification and save status remain separate.

Each run retains `manifest.json`, `results.jsonl`, `summary.json`, and fsynced
`events.jsonl` under its unique run directory. Events include pre-send intent,
per-command responses/partial evidence, row verification, save, timestamps, categories
and log references. Stage final-state attribution and its drift-detection limitation
are described [below](#ordered-template-stages-owner-approved-revision). A crash between intent and response must be treated as Unknown.
The incremental journal survives incomplete device outcomes; recovery ignores a
torn final journal line. No automatic resume or rollback is available.

The CLI writes a separate `execution-results.xlsx`. Offline `report` requires only the
retained run and a new output filename; it performs no reconnect/apply/save. Run Summary
contains readable run/device/save/backup metadata. Original template-named sheets retain
row identity, source row, original inputs and decisions, including skipped/unsupported
rows with actual target identity. Main columns: Pre-config, Config Sent, Config Evidence
(post-stage for new runs), Apply Status, Status Verification, Error, Warning, Save Status and Backup
Reference. Apply (Applied/Rejected/Unknown/No-op/Not executed/Skipped), verification and
save are independent. Config Sent lists actual attempted commands and responses, never
unsent approved proposals. Interrupted send intents remain pending/uncertain.

Pre-config is fresh scoped configuration captured and fsynced before that row's first
write, incorporating earlier same-device changes. Each row retains its own post evidence.
Older runs without pre-row records display **Not captured**; they cannot recover that
missing historical state. Older skipped records without request metadata remain visible
in Legacy Skipped with their retained row ID/reason; missing identity is not invented.
Evidence Details contains readable diagnostic records and complete continuation parts
for cells over 30,000 characters. All cells are literal, sanitized and wrapped. Export
streams diagnostics and retains only per-row event positions across the run; row evidence
is consumed separately (journal rescans trade export time for bounded evidence memory).
Original plan/review files are unchanged; retain the complete run for audit.

Execution defaults to protected `outputs/runs/configuration_execution/RUN_ID/backups/`.
Backup metadata/report references are relative to the run, so moving an intact default
run preserves them. Logs include usable absolute paths, never backup contents. Explicit
`--backups-dir PATH` / `confirm(backups_dir=PATH)` remains supported as an external root
with `PATH/RUN_ID/` allocation; relative metadata then points outside the run (an absolute reference is retained for
Windows overrides on another drive), and moving
only the run cannot preserve external captures. Omit the override for self-contained
runs. Standalone configuration-backup defaults and layout are unchanged.

For short Catalyst switchport responses, the pure parser still reports a missing Access
Mode VLAN as unknown. Only with matching target, Enabled, static access and reliable fresh
exact-interface configuration may verification use one explicit access VLAN fact. Malformed operational VLAN fields are not eligible for fallback. No
defaults are inferred and operational contradictions are never overridden. Results/logs
retain the missing field and fallback warning/source. Description, admin and unrelated
settings remain checked; a confirmed mismatch fails. Missing/ambiguous evidence is Unknown.

Shared sanitized diagnostics: `outputs/logs/configuration/YYYY-MM-DD/execution.log`
and `outputs/logs/switchport/YYYY-MM-DD/switchport.log` (UTC date), plus existing
transport logs. Run/digest/IP/row/command/stage correlate execution events. Full
sensitive backup content and arbitrary exception messages do not enter results/logs.
Standalone parser input is caller-owned; sanitize untrusted text before disclosure.

## Validation and remaining limits

Run deterministic tests from the root on Linux or Windows with the above import-path
setup (no devices or credentials needed):

```text
python -m pytest tests/test_configuration_execution.py -q
python -m pytest tests/test_configuration_plans.py tests/test_bulk_configuration_v2.py tests/test_configuration_v2_approved_services.py tests/test_shared_cli.py tests/test_result_spool.py tests/test_configuration_backup.py -q
python -m pytest -q
python -m orbitflow.configuration.execution_cli execute --help
python -m orbitflow.configuration.execution_cli report --help
```

Owner lab validation must first inspect prepare-only results (Python API below),
then explicitly authorize the single-device `execute` example. Exercise create/rename,
access/trunk Add/Remove/Replace, optional descriptions/native VLANs, Port-channel owner,
EdgeSwitch PVID/tagged Add/Remove, no-op, rejection, partial-change save and report-only
recovery. Compare requested state independently and check saved configuration with
the owner's device procedures. Preserve source hashes and sanitized results. No
production execution or live/lab testing was performed by Codex.

Only the approved observed mode variants are accepted: Cisco config/config-if/
config-vlan/config-vl and EdgeSwitch outer Vlan/Interface N/N/Config. EdgeSwitch global
Config mode and all firmware variants still need representative owner lab evidence.
New collectors reject unsupported family/platform/profile combinations. Other
capabilities retain their existing parser and platform limitations. Local database
rollback, simultaneous external device changes and interruption between send and
durable response cannot be made transactional. A new summary is not permission to
repeat an uncertain write; reconcile equipment first.

Supported standalone Python signatures/examples: [execution API](../operations/configuration-execution-api.md).

Issue #117 review corrections support real EdgeSwitch Interface VLAN headers with
strict table completeness, require matching standalone switchport target headers,
verify the approved C3750X dot1q change while preserving unrelated settings, and
recognize supplied command-not-found/range rejections. C3850 omits the selector.
Save remains prompt-based with errors separate. Optional capability correlation
retains run/row/digest, target/command, elapsed timing and safe failure diagnostics;
see the [API reference](../operations/configuration-execution-api.md). Owner lab validation remains pending.

### Revision validation without replaying completed changes

Owner evidence reports 32 Verified, 3 Unknown, 1 Not executed and 10 skipped across two
devices, with both saves returning. These corrections use fixtures only. Do not replay
those changes for presentation diagnosis. Owner may regenerate the existing report:

```bash
export PYTHONPATH="$PWD/src"
python -m orbitflow.configuration.execution_cli report /secure/retained/RUN_ID /secure/revised-results.xlsx
python -m pytest tests/test_configuration_execution.py -q
python -m pytest -q
```

```powershell
$env:PYTHONPATH = "$PWD/src"
python -m orbitflow.configuration.execution_cli report C:/secure/retained/RUN_ID C:/secure/revised-results.xlsx
python -m pytest tests/test_configuration_execution.py -q
python -m pytest -q
```

Owner read-only validation can call `verify_row` with a fresh normalized baseline and
approved entry (API reference), comparing short switchport output to explicit exact-port
configuration. Recheck Gi1/1/1 description OrbitflowTest1 and access VLANs 445/4001/201
on the respective ports. New backup/pre-row records require a separately authorized
future lab change; old runs cannot gain them through export. No live device work was
performed by Codex.


Pre-revision confirmations are matched using their original metadata shape as well as
the current summary digest. Adding skipped-row presentation identity cannot create a
second executable reference for already claimed/completed/interrupted work. Existing
records return their original fully bound summary/digest; older missing skipped identity
is not invented. The confirmation store must still be retained and protected.

Older warning/category detail is limited to retained fields. Export does not rerun
verification, infer successful fallback or reclassify historical Unknown outcomes.

### Iteration 3 presentation and live progress (Issue #117)

Confirmation groups repeated finding/skip categories with counts and source sheet/row
ranges. VLAN lists use compact inclusive ranges. Nested JSON evidence and opaque row
IDs are absent from the display; material blockers remain visible. The full preparation
and digest/replay rules are unchanged. Execution presentation suppresses only
TAGGED_VLAN_NOT_IN_MEMBERSHIP, including nested EXISTING_VLAN_WARNING findings.
Independent tagged/forbidden facts and the original plan/compliance findings remain.

Template reports show input fields as individual columns before configuration columns.
The legacy Original Inputs and internal Row ID columns are hidden, retained for audit.
Pre-config and Config Evidence contain scoped CLI excerpts; Config Sent lists attempted
commands and exchange outcomes. Status Verification shows status, expected/actual facts,
preservation and fallback source without copying nested evidence or whole-device port
tables. Full detail hyperlinks lead to readable event/continuation rows containing
complete responses, metadata and operational tables. Run Summary includes row verification
and device-save outcome counts. Manifest run_id is authoritative after moving/renaming
an intact run; legacy runs without manifests fall back to the directory name.
Main rows are wrapped at 90 points, configuration/check columns 48 characters wide;
detail text uses a wider column with continuation chunks. Expand row height or follow
Full detail for long excerpts; no assertion that every long value fits the main grid.
Fallback and verification-warning diagnostics retain useful field/source text in shared
sanitized configuration logs.

After `y`, CLI progress is immediate, serialized and flushed. Each line identifies
IP, hostname and stage. Row stages add template sheet/source row; command stages add
index/total. Raw commands, timing/deadline fields, completion counters and correlation
metadata remain in structured callbacks/diagnostics rather than normal console output.
Statuses, error categories and warning pointers remain visible. For example:

```text
192.0.2.117 fixture [connect]
192.0.2.117 fixture [row_preflight] | EdgeSwitch VLAN Database row 3
192.0.2.117 fixture [command_intent] | EdgeSwitch VLAN Database row 3 | command 1/4
192.0.2.117 fixture [waiting]
192.0.2.117 fixture [row_result] | EdgeSwitch VLAN Database row 3 | status=Verified
```

At execution completion, a single outcome line streams actual recorded device and row
outcomes and total elapsed seconds, before report generation. Devices distinguish
Completed, Partial, Failed and Unknown; an uncertain row or save is Unknown, and
verified rows plus a failure are Partial. Row counts retain actual verification
statuses and the skipped selection count. Interruptions/exceptions show observed completed outcomes and mark the remaining
devices/rows Unknown/incomplete, include elapsed time and propagate failure; they never claim
success. Offline report generation prints no execution-duration footer.

Connect/identify/preflight, backup start/completion, row preflight, command exchanges,
verification, save and cleanup start/completion are visible. Run-wide lines use IP `-`; report_generation
and report_complete are also shown by the offline report command. Returned means an
exchange returned, not verified success. Saved still means exact session EXEC-anchor return;
explicit errors remain separate. Timeout/disconnect remains Unknown.

An optional display timer wakes every 5 seconds while a subscribed blocking stage is
active. The console prints a concise waiting stage with available row/command context.
Structured subscribers retain awaited stage, elapsed wait and configured timeout/remaining
budget; no total-stage deadline is invented for compound observation or connection.
Heartbeats do not probe the
device, extend deadlines, retry writes, or prove responsiveness. Save-question labels
are emitted by the device-owning worker; the timer never accesses channels. Subscriber
exceptions disable display only; durable journal failures remain execution failures.
This uses Python threading/contextvars on Linux and Windows, with no additional feature
worker pool. Standalone/API execution is quiet unless a subscriber is supplied.

Workbook QA for this revision uses an equivalent deterministic structural/content
inspection with openpyxl: check actual cell content, compact ranges, full detail and
hyperlink targets, preserved manifest identity, input columns, widths, wrapping and
row heights. No Excel desktop screenshot or Linux-host execution is claimed. Owner
read-only verification and offline report regeneration remain sufficient for reassessing
previously applied access rows; no live apply/save was performed by Codex.


Validation limitation on this Windows host: the controller's nested temporary root
causes two inventory/reporting tests to fail with long-path errors. Extended-length
spelling did not resolve relative-path workbook creation. The gate remains failed;
no controller guard was changed. A separate full deterministic suite can use
`python -m pytest -q --basetemp <short-unused-directory>` under an authorized
temporary root. Pytest owns/clears that directory; use a dedicated new test directory.
This separate run does not change the controller gate's recorded failure.

Recovery validation: executor 133 passed; separate shorter-temp full suite 2,579
passed in 184.13s on Windows. Both nested-temp controller runs had 2,577 passed /
2 failed; do not report those gates as passed. Linux commands are source-verified
only. Exact invocation/evidence is retained in the monthly devlog and revision handoff.


### Issue #119 validation status

Owner lab validation of C3750X and EdgeSwitch execution was reported following PR #118;
C3850 live validation remains outstanding. This presentation follow-up does not replay
those changes or alter historical run results. No live device operations were performed
by Codex. Fresh row collection/verification, per-IP ordering, one backup before writes
and one save after attempted writes remain unchanged.

Source-verified deterministic validation from the repository root (use a fresh dedicated
pytest directory; pytest clears its basetemp):

```powershell
$env:PYTHONPATH = 'src'
python -m pytest tests/test_configuration_execution.py -q
python -m pytest -q --basetemp "$env:TEMP/of119-tests"
python -m orbitflow.configuration.execution_cli execute --help
python -m orbitflow.configuration.execution_cli report --help
```

```bash
export PYTHONPATH=src
python -m pytest tests/test_configuration_execution.py -q
python -m pytest -q --basetemp /tmp/of119-tests
python -m orbitflow.configuration.execution_cli execute --help
python -m orbitflow.configuration.execution_cli report --help
```

These commands require no device access. Linux commands are source-verified; Linux-host
execution and C3850 live validation are not claimed. The controller-required test set is
the full `python -m pytest -q` suite, with its own managed temporary directory.

## Interactive console adapter (Issue #123)

This workflow is also available through `python -m orbitflow.menu`; see the [console manual](interactive-operations-console.md) for environment profile, target workbook selection, per-run concurrency, confirmation and output/recovery behavior. Direct CLI flags and service contracts remain supported. Default `orbitflow.toml` execution loading now prefers validated shared profile pacing when present; explicit alternate config files retain their semantics.

Issue #123 console revision: The console derives/displays the expected digest from the selected validated immutable JSON and still passes it to workbook verification. Choose the trusted original JSON; engineer decisions and separate execution confirmation remain required. Invalid/corrupt or consumed preparation produces fixed guidance; no safety checks are bypassed. See the [console guide](interactive-operations-console.md).


## Execution profiling and safe reuse (Issue #125)

Confirmed execution automatically records monotonic timing records in the existing
UTC-dated `outputs/logs/configuration/YYYY-MM-DD/execution.log`, including when called
from the interactive console. Console presentation, confirmation, public signatures,
existing audit events, report columns and durable run layout are retained; stage
records add provenance without replacing command/row evidence. Match `run_id`
and `digest` to `outputs/runs/configuration_execution/RUN_ID/manifest.json` and
`summary.json`; row records also include `row_id`, `template_id` and command index.
Timing records have message `Execution timing`, fixed stage/command category, outcome
and nonnegative seconds. No literal CLI, responses or exception messages enter timings.
Transport and standalone capability diagnostics retain their existing ownership.

Stages cover connection/admission/retry wait, shell setup, identification, initial
preflight, protected backup collection/write, full observation, interface collection,
VLAN/config collection, normalized snapshot/reuse, VLAN lookup, scoped evidence,
pre-row target checks, mode validation, every approved command and underlying
CLI exchange, post-row verification, independent save, row/device/run totals.
Failed exchanges retain category/outcome; uncertain sends and interrupted totals are
Unknown. A Completed run total means collection finished, not all rows Verified.

`device_wait_seconds` measures blocking CLI receives (including timeout/quiescence),
not a heartbeat or device liveness. `work_seconds` is residual elapsed wall time,
**not CPU time**; connection/authentication, privilege setup and scheduling waits
are not inferred as measured device receive time. Connection admission/retry waits
have separate stages. Parent/child spans overlap: never sum them. Total execution
includes journaling/cleanup; report generation is outside run_total. The run total
records elapsed time only, without aggregating overlapping worker receive waits. Timings use no
extra queries, worker pools, retry, timer or fsync. Existing mandatory journal/fsync
semantics remain unchanged. Logs use shared 2 MiB rotation with three backups; archive
them before rotation for long comparisons. Timing logs are diagnostics, not durable
recovery evidence; retain the fsynced run journal independently.

The executor opts its own supported-family shell into reusing accepted session paging
setup. Prompt/session validation still happens on every collector/mode call; first
trusted setup is still sent and checked. No accepted setting crosses a shell or
platform setup profile, and an unsynchronized exchange cannot reuse that shell.
Standalone callers keep their existing setup behavior. `execution_mode` is local
validation already; it never caused a network round trip and remains intact.

The owner-approved 2026-10-18 revision uses ordered template stages, described
[below](#ordered-template-stages-owner-approved-revision). Fresh full collections
are shared within a stage; no stale snapshot replaces a fresh stage check. The
session-owned projection manager remains bounded to one 8 MiB projection/input;
writes, uncertain results, mismatches and lost synchronization invalidate it.
Standalone observation and `verify_row` remain independent and fresh.

### Offline tests, benchmark and extraction

The benchmark uses real shared collectors/parsers over synthetic in-memory channels,
ten full observation epochs for each family, with baseline/reuse and timing off/on
variants. It prints JSON count/median/p95 measurements and asserts exact read counts;
there are no live sockets or timing thresholds. The separate all-template regressions
compare complete fresh normalized evidence and planner decisions/commands. Host-only
timings are not estimates of live RTT or throughput. These developer diagnostics
implement the Issue's measurement/comparison requirement; they are not a new device
operator workflow and do not need a console menu entry.

PowerShell (from repository root):

```powershell
$env:PYTHONPATH = "$PWD/src"
python -m pytest tests/test_configuration_execution_stages.py tests/test_execution_observation_timing.py tests/test_configuration_execution.py tests/test_shared_cli.py -q
python -m pytest tests/test_configuration_execution_performance.py -q -s
python -m pytest -q
python scripts/configuration_execution_timings.py --help
python scripts/configuration_execution_timings.py outputs/logs/configuration/YYYY-MM-DD/execution.log --run-id RUN_ID
# Include retained rotated files explicitly when needed:
python scripts/configuration_execution_timings.py outputs/logs/configuration/YYYY-MM-DD/execution.log outputs/logs/configuration/YYYY-MM-DD/execution.log.1 --run-id RUN_ID
```

Linux Bash (same offline commands):

```bash
export PYTHONPATH="$PWD/src"
python -m pytest tests/test_configuration_execution_stages.py tests/test_execution_observation_timing.py tests/test_configuration_execution.py tests/test_shared_cli.py -q
python -m pytest tests/test_configuration_execution_performance.py -q -s
python -m pytest -q
python scripts/configuration_execution_timings.py --help
python scripts/configuration_execution_timings.py outputs/logs/configuration/YYYY-MM-DD/execution.log --run-id RUN_ID
python scripts/configuration_execution_timings.py outputs/logs/configuration/YYYY-MM-DD/execution.log outputs/logs/configuration/YYYY-MM-DD/execution.log.1 --run-id RUN_ID
```

The extraction script is entirely offline and needs only Python's standard library.
Required positional `logs` accepts one or more UTF-8 shared log files; optional
`--run-id` selects an exact manifest ID (default all runs in supplied logs). It prints
JSON per run/device family/IP and allowlisted stage/category with
count/min/median/nearest-rank p95/max seconds. `device_family` is the approved bound
identity family, not a claim that fresh identification succeeded; inspect outcomes.
Old logs without this field retain `-`, without guessing a family from other devices.
Use `--group-by run_id device_family management_ip template_id row_id` for row
attribution. Device-level stages retain unknown row/template fields; they are never
allocated proportionally to rows. Missing fields remain `-`. Valid IPs, allowlisted
families/templates and generated hex IDs are printed; custom identifiers are stable
SHA-256 labels, so arbitrary log text cannot be reflected. No hostname is printed.
It ignores malformed/torn/non-timing records and invalid durations; at 100,000 samples
it fails closed with exit 2, as for unreadable input. Empty selection returns `[]`.
Parsing is limited to 65,536-character lines and 100,000 valid samples (including duplicate
records). Duplicate resolved paths and exact timestamped records in overlapping
files are ignored. Copied records without timestamps cannot be deduplicated reliably.
Requested missing files and omitted surviving rotations emit fixed warnings to stderr;
missing files are skipped. No surviving log set can prove retention completeness,
so the CLI always warns about that limitation. Other unreadable input fails with exit 2.
No commands, raw output or arbitrary exception text are printed.

Compare `cli_command` / `configuration_read` counts/distributions to identify physical
configuration-read exchanges per device. `vlan_config_collection`, `full_observation`
and `stage_pre_observation` / `stage_post_observation` contain those exchanges: **do not add their durations or
counts together**. Compare collectors separately within each device, then rows;
missing row IDs do not establish which row incurred a device-level stage.

PowerShell in the Issue #125 worktree (offline, no device access):

```powershell
Set-Location 'C:\Users\a4212\OneDrive\Personal\Lightning Broadband\Projects\Python Project\OrbitFlow-Evo-worktrees\issue-125'
$env:PYTHONPATH = "$PWD/src"
python scripts/configuration_execution_timings.py outputs/logs/configuration/YYYY-MM-DD/execution.log --run-id RUN_ID --group-by run_id device_family management_ip template_id row_id
```

Linux Bash from the checked-out repository:

```bash
python scripts/configuration_execution_timings.py outputs/logs/configuration/YYYY-MM-DD/execution.log --run-id RUN_ID --group-by run_id device_family management_ip template_id row_id
```

### Ordered template stages (owner-approved revision)

**Verification now has a stage boundary. It does not establish continuous whole-device
drift detection between reads, nor individually observed intermediate effects inside
a stage.** Required target/preservation evidence still fails closed. Full collection
is retained for interface stages; no scoped configuration parser or new device command
has been introduced. Unrelated out-of-scope external changes are not globally compared
against a planning baseline. They can remain undetected; changes made and reverted
between reads can escape detection.

Each device worker retains selected worksheet-left-to-right, row-top-to-bottom order.
It forms maximal contiguous stages of the same template with independent normalized
targets. Repeated source/resolved targets (including bundle aliases), dependencies
within a proposed stage, or a different template split the stage. Noncontiguous
appearances never merge. EVC remains planning-only, outside executor support.

One full initial observation follows fresh identity/privilege checks; independent
protected backup completes before writes. This initial observation supplies the first
stage's precheck. Later stages take one fresh full observation. Issue #139 removes
trusted-baseline equality and fresh planner/command/no-op/projected-state comparisons.
Fresh interface records and declarations must uniquely identify both source and
approved resolved target. Catalyst access and trunk requests cannot target physical bundle members;
logical parents must be selected explicitly, with evidenced ownership and no conflicts. Known routed/access/trunk conversion and unresolved methodology hazards
still block port changes. Description stays on its approved physical interface.
EdgeSwitch port ownership and requested database prerequisites remain checked per row.
Ordinary planning warnings create no additional execution gate. Original v1/v2
planning validation and immutable source integrity checks remain unchanged.
All candidate prechecks and fsynced per-row pre-config records precede stage writes.
A failed check blocks that row; trustworthy independent rows may continue.

Approved commands execute sequentially, unchanged, with immediate response and known
mode validation. Rejection stops that row; timeout or lost synchronization leaves
uncertain writes Unknown and blocks further unsafe sends. No retries or rollback.
One post-stage full interface/VLAN/configuration observation supplies all independent
interface targets, with fresh per-target operational switchport checks. VLAN Database
stages need only fresh per-VLAN lookup postchecks; they do not reread configuration.
Trunk full allowed sets, preserved omitted description/native/admin/unrelated settings,
EdgeSwitch PVID/tagging/participation and no-op checks still use existing verifiers.
Overlapping targets are split so each earlier effect is observed before supersession.

`events.jsonl` retains `stage_precheck` (row IDs and normalized observation),
`stage_post_observation`, per-row `pre_row_evidence` and `row_result`, and `stage_result`
before the next stage. Row results and verification include `stage_id`;
`observation_scope` explicitly says `stage final state; independent target`.
These are sanitized normalized facts, not raw configuration or protected backup data.
Row totals include time waiting for sibling rows/shared observation, overlap stage
elapsed time, and must not be added to device/run totals. `row_apply` and
`post_row_verification` isolate row work. Shared observations are attributed to the
stage, never divided into invented per-row physical read times. Failed siblings are
not represented as verified by aggregate success. Interrupted rows remain recoverable
from command intent/result records without reapplying. Save runs once after attempted
writes when the shell is usable, including partial changes; save outcome is separate.

### Deterministic collection comparison and owner lab validation

The additional `template_stage_collection_schedule` benchmark exercises real shared
collectors/parsers over in-memory channels, five host-only samples per variant and
ten independent rows per template. It reproduces the previous collection schedule
and current stage fallback schedule; it sends no writes. Full counts include initial
baseline and independent protected-backup capture. Description reads count the shared
interface table, not switchport checks. Per-target switchport verification remains
unchanged (ten further checks for port templates) and is covered by semantic executor
tests, not this collector-only benchmark. No-op collection follows the same schedule.
Actual multi-stage cost depends on row order, overlap and dependencies. Singletons
and split stages retain full collection and therefore offer smaller savings.

One Windows synthetic run on 2026-10-18 produced the following measurements. They
are host parser/collector timings without device latency, not live performance gains.

| Family / template | Full config reads | Description reads | VLAN lookups | Median / p95 ms (before -> stage) |
|---|---:|---:|---:|---|
| C3750X / vlan database | 12 -> 2 | 11 -> 1 | 30 -> 20 | 11.15/14.36 -> 4.32/4.79 |
| C3750X / access port | 22 -> 3 | 21 -> 2 | 21 -> 2 | 16.21/16.27 -> 3.77/3.89 |
| C3750X / trunk port | 22 -> 3 | 21 -> 2 | 21 -> 2 | 16.39/16.71 -> 3.74/3.79 |
| C3750X / interface description | 22 -> 3 | 21 -> 2 | 0 -> 0 | 14.74/15.09 -> 3.56/3.62 |
| C3850X / vlan database | 12 -> 2 | 11 -> 1 | 30 -> 20 | 11.25/11.61 -> 4.29/4.65 |
| C3850X / access port | 22 -> 3 | 21 -> 2 | 21 -> 2 | 16.39/16.46 -> 3.71/3.86 |
| C3850X / trunk port | 22 -> 3 | 21 -> 2 | 21 -> 2 | 16.37/16.88 -> 3.74/3.76 |
| C3850X / interface description | 22 -> 3 | 21 -> 2 | 0 -> 0 | 14.63/14.85 -> 3.58/3.59 |
| EdgeSwitch / vlan database | 12 -> 2 | 11 -> 1 | 30 -> 20 | 13.73/14.52 -> 5.31/6.29 |
| EdgeSwitch / vlan port | 22 -> 3 | 21 -> 2 | 21 -> 2 | 20.39/21.57 -> 4.53/4.59 |
| EdgeSwitch / interface description | 22 -> 3 | 21 -> 2 | 0 -> 0 | 18.15/18.31 -> 4.25/4.33 |

Use the PowerShell/Bash offline test and benchmark commands above. For stage timing
attribution, both shells support this same offline command:

```text
python scripts/configuration_execution_timings.py outputs/logs/configuration/YYYY-MM-DD/execution.log --run-id RUN_ID --group-by run_id device_family management_ip template_id stage_id row_id
```

Archive all available rotations and retain `outputs/runs/configuration_execution/RUN_ID/`
including its journal, result spool and backups. Compare physical
`cli_command/configuration_read` counts and median/p95, template-stage/device/run
elapsed distributions, row outcomes, independent save status and completeness of
pre/post-stage/per-row records. Never sum nested timings. Missing/rotated records
cannot prove completeness; reconcile the manifest/journal and extractor warnings.

Owner report for run `20261018T070228_939497Z_4f9ab36d0f1a4a46addef898cf433589`
records C3750X 31 full configuration reads (~170.8 s physical read time), EdgeSwitch
22 (~9.3 s), and ~277.9 s run elapsed. This is owner lab baseline evidence; no future
speedup follows from those numbers and nested durations are not additive.

Owner-only validation uses the existing Windows/Linux `execute` examples above after
`tsh status`, fresh independently reconciled lab state, separately reviewed plans and
explicit confirmation. Keep concurrency, pacing and timeouts fixed. Do not replay
completed/uncertain changes or delete replay authority. Exercise all eleven supported
templates, template re-entry, dependencies, alias/target overlap, description
supersession, no-ops, full-set preservation, externally changed targets, incomplete
facts, rejection/timeouts/lost mode, partial-stage save and offline report recovery.
Compare baseline and revision distributions only across equivalent independently
prepared trials. Preserve actual failures and unknowns in the comparison. No new
read-only execution mode exists. Codex used no live devices or credentials; owner
C3750X/C3850/EdgeSwitch stage-execution validation and Linux validation remain pending.


## Flexible execution prompts (Issue #134)

The 2026-10-19 revision accepts abbreviated/changing Cisco host presentation and
arbitrary valid parenthesized configuration submodes on the identified owned shell.
EdgeSwitch accepts `(ES24) (Vlan)#`, `(ES24) (Interface 0/3)#`,
`(ES24) (Something)#`, `(ES24 Something)#` and supported hostname annotations.
The approved plan still controls every command. Execution requires the current exact
command echo and complete unterminated structural prompt, then returns immediately
with zero new per-command delay. Returned means
exchange completion; verification still decides Verified/Failed/Unknown.

Before observation/save, the completed sequence or checked bounded `end`/`exit`
recovery must reach privileged EXEC. Its observed presentation becomes the exact
session EXEC anchor; completed verification reads may refresh that presentation
only at structural privileged EXEC. Save requires that anchor's exact return after its own echo;
a new hostname during save is Unknown. Arbitrary banners ending in `#`, missing
or stale echoes, errors and incomplete responses do not authorize continuation or
write retry. Shared read-only flows and identification retain baseline behavior.

Automated synthetic tests do not connect to devices or perform production writes.
From the repository root, with an existing environment and dependencies installed:

Linux Bash:

```bash
source .venv/bin/activate
export PYTHONPATH="$PWD/src"
python -m pytest tests/test_configuration_execution.py tests/test_configuration_execution_stages.py tests/test_configuration_execution_performance.py tests/test_shared_cli.py tests/test_configuration_backup.py -q
TMPDIR=/var/tmp TEMP=/var/tmp TMP=/var/tmp python -c 'import tempfile; assert tempfile.gettempdir() == "/var/tmp", "OS temp fell back; choose a writable root outside Git"'
# Run only after the root check succeeds.
TMPDIR=/var/tmp TEMP=/var/tmp TMP=/var/tmp python -m pytest -q
```

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH = "$PWD/src"
python -m pytest tests/test_configuration_execution.py tests/test_configuration_execution_stages.py tests/test_configuration_execution_performance.py tests/test_shared_cli.py tests/test_configuration_backup.py -q
# Select an existing writable OS temp root outside every Git checkout.
$testTemp = [System.IO.Path]::GetTempPath()
$env:TMPDIR = $testTemp
$env:TEMP = $testTemp
$env:TMP = $testTemp
python -m pytest -q
```

These commands create local test artifacts only. The Linux full-suite command uses
`/var/tmp` because this sandbox's `/tmp` contains a `.git` entry. On either OS,
choose an existing writable temp root whose ancestors contain no `.git` entry;
the controller deliberately rejects roots inside checkouts. Python can silently
fall back to another temp root if the requested directory is unwritable; check
`python -c "import tempfile; print(tempfile.gettempdir())"` before the full run. Do not remove Git
markers or weaken that check to obtain a pass.

Expected: all tests pass using sanitized fixtures, including the Linux C3750X
`configure terminal` / `SW-ABBREV(config)#` incident, changing modes/hosts, split
chunks, false prompts, lost echo, errors, EOF/timeouts, save and read-only regressions.
Windows execution of these commands remains operator validation unless separately
reported; Linux automated results are recorded in the October devlog.
The initial implementation had 408 focused passes and 3,002 full-suite passes
with 25 orchestration failures. This review revision has **416 focused passes**
and **3,010 full-suite passes with 25 failures** (87.09s). Requesting `/var/tmp`
in this sandbox fell back to `/tmp`: `/var/tmp` is unwritable and `/tmp` has a
`.git` entry rejected by the safeguard. A clean full suite remains unverified;
run it with a writable OS temp root outside Git checkouts.

Owner-controlled live verification of this revision remains pending on Linux
C3750X, C3850 and EdgeSwitch. Existing PR #118/#126 lab history does not validate it:

1. Authenticate Teleport locally; use protected credentials and a fresh authorized
   lab plan/workbook for the supported family. Inspect current device state first;
   never replay an earlier completed or uncertain change to reproduce the incident.
2. Use the existing Linux/PowerShell execution examples above with concurrency 1.
   Review digest, selected rows and whole-running-config save implications. Only
   the owner confirms an authorized lab apply; production apply stays owner-controlled.
3. For Cisco, observe configure-terminal completion with abbreviated presentation
   and subsequent mode transitions. For EdgeSwitch, inspect the actual firmware's
   inline/outer presentation. Do not add arbitrary commands to approved plans merely
   to manufacture an unobserved submode; those cases have synthetic coverage.
4. Check command Returned events, independent row verification, checked EXEC return,
   and separate save status/errors. EdgeSwitch answers only the recognized question
   with `y`. Confirm device state and startup persistence independently as appropriate.
5. For a timeout, disconnect or uncertain write, inspect protected local evidence and
   device state before any new plan. Do not retry/replay writes automatically. Keep
   full evidence local; share only sanitized outcomes with no credentials/private IPs.
   Record OS, family/firmware, prompt presentation class, row/save outcomes and elapsed
   times. Pending evidence must not be described as successful live validation.

This fixes an existing console-exposed execution workflow; no new menu action,
parameter or confirmation flow is introduced.

### Prompt-reader throughput review (PR #135)

The owner's latest clarification supersedes the earlier quiet-guard proposals.
Execution returns immediately on the current exact echo and complete unterminated
vendor prompt. There are no added silence waits, sleeps, retries or timeout
extensions. Synthetic 52-row/five-command tests assert zero added wait and 520
receives for 260 exchanges split into two fragments each. This measures reader
overhead only, not live throughput. Incomplete prompts continue receiving within
the existing deadline. An identical prompt-shaped prefix followed by later bytes
cannot be predicted; the next exchange still requires its own exact echo and
failed exchanges invalidate the session without automatic replay. Rejection,
verification, save and shared read-only behavior retain their independent contracts.
Historical timing comparisons remain in the October devlog and are superseded.

### Iteration 2: completion alternatives and controller evidence

The earlier one-second guard and shorter-wait comparisons are historical proposals,
superseded by the owner's immediate-completion decision above.

The recorded **3,010 passed / 25 failed** run was an inner Codex Linux sandbox
invocation, with requested `/var/tmp` falling back to `/tmp`. It was **not** the
controller gate report. The controller independently calls `run_tests` after Codex
returns, sets `PYTHONPATH=src`, supplies a protected `controller_temp` directory in
`TEMP`/`TMP`/`TMPDIR`, and runs its Python executable with
`-m pytest -q --basetemp <protected-directory>/pytest`. A nonzero exit raises before
commit/push/PR publication. Its PR pass text is generated after that gate; it is
not a copy of the devlog. No controller run stdout/exit report is available in this
worktree to establish whether PR #135's separate outer gate truly passed. The
sandbox failures alone neither prove nor disprove an outer gate pass.

Controller-owned PR clarification, ready to copy:

> Codex sandbox validation previously recorded 3,010 passed / 25 failed due to
> orchestration OS-temp guards; that run was not a full-suite pass. The independent
> controller gate uses a protected OS-temp directory and explicit pytest basetemp.
> Its run output, interpreter/environment, tested revision and zero exit must be
> supplied to substantiate the PR's full-suite pass claim. That evidence is currently
> unavailable to the implementation worker; the outer gate result is unverified here.

No Git markers, temp-root safeguards or controller publication logic were changed.
Use the Bash/PowerShell commands and owner verification steps above; Linux device,
C3850/EdgeSwitch live validation and Windows automated validation remain pending.

Latest iteration-2 Linux sandbox validation: **440 focused tests passed (5.36s)**;
full `PYTHONPATH=src python -m pytest -q`: **3,034 passed / 25 failed (85.49s)**,
exit 1, with orchestration tests blocked by the Git-marked sandbox OS-temp root.
This updates the earlier sandbox counts above; no outer controller gate report
has become available. A full-suite pass must not be inferred from these results.

Latest no-added-wait revision validation (Linux Codex sandbox, Python 3.14):
**410 focused tests passed (5.75s)**. Full `PYTHONPATH=src python -m pytest -q`:
**3,004 passed / 25 failed (87.13s)**, exit 1. The 25 orchestration failures
reject this sandbox OS-temp root under `/tmp` because a Git marker is present
in its ancestry. This is not a controller gate pass; its independent result is
unavailable here. No temp safeguard was changed. Windows automated testing and
owner Linux C3750X/C3850/EdgeSwitch live validation remain pending.


### Simplified approved execution — Issue #139

Confirmed execution consumes original approved CLI, including commands whose effect
is already present at fresh collection. Only rows originally planned as no-op have
no commands. Verification still compares approved intent and preserved settings to
fresh post-stage facts; a difference can fail verification after writes without
having blocked command delivery. Do not interpret this as continuous drift control.

The existing console **Execute Approved Plan** action uses the same service and
single batch confirmation; no new menu action, parameter or profile is needed.
Read-only reporting, planning, inventory, transport and standalone backup APIs retain
their defaults. Command, verification, backup and save results remain distinct in
the durable sanitized journal/report. Rejection stops a row, failed dependencies
block dependent rows, and lost/ambiguous SSH stops that device with no write retry.
Save is once after attempted writes, including partial failure, only from validated
privileged EXEC on a usable owned shell.

Automated fixtures are separate from pending owner/live validation on C3750X,
C3850 and EdgeSwitch. The focused Issue #139 command (Bash with `PYTHONPATH=src`,
or PowerShell after `$env:PYTHONPATH = "$PWD/src"`) is:

```text
python -m pytest tests/test_configuration_execution.py tests/test_configuration_execution_stages.py tests/test_configuration_execution_performance.py tests/test_execution_observation_timing.py tests/test_shared_cli.py tests/test_configuration_backup.py tests/test_operations_console.py tests/test_vlan_capability.py -q
```

Use the Linux/Windows full-suite commands above with a writable OS temporary
directory outside every Git worktree. A nonzero full-suite exit is
FAILED even when all failures arise from that temp guard. The independent controller
gate must be evidenced by its tested revision, command, zero exit and captured output;
this worker cannot claim a future controller gate passed. Do not disable guards.
Atlas final documentation reconciliation after PR review remains pending, including
read-only `.agents/` skill wording; preserve PR #136's #134/#135 validation history.


Issue #139 automated Linux sandbox evidence: **591 focused tests passed (14.23s)**.
Final full suite **FAILED: 3,062 passed / 25 failed (114.12s), exit 1**; all failures
are orchestration tests blocked by the Git-marked OS-temp root. Guards were retained.
The separate clean controller gate is pending; prior #134/#135 owner validation
and PR #136 records do not establish validation of this revision.

#### Issue #139 — owner Linux validation update (2026-10-20)

From the clean `codex/issue-139` worktree at original implementation head `481e712c`, with `PYTHONPATH` pointing at that worktree's `src`, the owner ran the focused suite covering execution, stages, performance, timing, shared CLI, backup and console: **591 passed in 14.56s**. The complete Linux deterministic suite also passed: **3,087 passed in 117.23s**. These are owner-reported automated results and supersede the earlier sandbox-only full-suite failure for the owner's Linux environment; they do **not** establish successful live configuration application or Windows regression results. Existing explicit summary confirmation, protected pre-change backup, interface ownership checks and privileged EXEC-only save remain mandatory. For operator-controlled live validation, use only a newly reviewed, approved test plan on designated devices and never replay an uncertain interrupted run.

## Shared progress presentation (Issue #144)

See [CLI progress and durable results](cli-progress.md) for interactive and redirected
output, phase-specific counters, saved paths, partial/interrupted/export-failure
semantics and the coverage table (including specialist/lifecycle exemptions).
Device/workflow semantics and existing arguments are unchanged. Deterministic
terminal fixtures are separate from pending owner-operated Linux/Windows validation.


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
See [owner validation matrix](aggregation-validation.md).
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

### Parent initialization revision validation (Issue #154 / PR #155)

Offline deterministic checks from the repository root (Linux):

```bash
python -m pytest tests/test_configuration_plans.py tests/test_bulk_configuration_v2.py tests/test_configuration_v2_approved_services.py tests/test_configuration_execution.py tests/test_configuration_execution_evc.py tests/test_configuration_execution_stages.py tests/test_configuration_execution_performance.py tests/test_operations_console.py -q
```

Windows PowerShell, with the project environment activated:

```powershell
python -m pytest tests/test_configuration_plans.py tests/test_bulk_configuration_v2.py tests/test_configuration_v2_approved_services.py tests/test_configuration_execution.py tests/test_configuration_execution_evc.py tests/test_configuration_execution_stages.py tests/test_configuration_execution_performance.py tests/test_operations_console.py -q
```

Expected: deterministic tests pass; synthetic four-row 445/30/31/32 runs retain
exact ordered CLI, one initialization on an initially empty ME parent and zero
on an observed trunk-none parent, independent later approvals, per-row outcomes,
one device save and offline XLSX recovery. Rejection/timeout fixtures check no
unsafe later EVC write. Synthetic tests are not Windows execution or live evidence.

Owner-operated checks on an already authorized lab session are read-only:

```text
show running-config interface GigabitEthernet0/6
show vlan id 445
show ethernet service instance id 445 interface GigabitEthernet0/6 detail
show ethernet service instance id 30 interface GigabitEthernet0/6 detail
show ethernet service instance id 31 interface GigabitEthernet0/6 detail
show ethernet service instance id 32 interface GigabitEthernet0/6 detail
```

Confirm current parent trunk/allowed-none and each exact service identity; Up/Down
is retained as operational evidence. Keep output private and sanitize any review
extract. Do not replay previously applied rows. Any future lab apply requires a
new plan from fresh state, workbook review, summary inspection and owner-controlled
execution confirmation. This revision has no live validation evidence. Existing
**Execute Approved Plan** console integration uses the same corrected service;
no additional menu action or confirmation is required.

## Pending preview revision validation (Issue #154 / PR #155)

Linux deterministic regressions (from repository root):

```bash
export PYTHONPATH=src
python -m pytest tests/test_configuration_execution_evc.py tests/test_configuration_execution.py tests/test_configuration_execution_stages.py tests/test_configuration_execution_performance.py tests/test_bulk_configuration_v2.py tests/test_configuration_v2_approved_services.py tests/test_configuration_plans.py tests/test_operations_console.py tests/test_vlan_capability.py -q
```

Windows PowerShell uses the same pytest command after:

```powershell
$env:PYTHONPATH = "src"
```

Owner offline, read-only validation of existing artifacts (Linux and Windows after
setting PYTHONPATH as above; replace paths and digest with the matching artifacts):

```text
python -c "from orbitflow.configuration.v2.planning import load; from orbitflow.configuration.execution import ExecutionService,operator_summary,render_summary; p=load('plan.json'); s=ExecutionService('outputs/validation/issue154-authority'); r=s.prepare_workbook(p,'plan.xlsx',expected_digest='TRUSTED_PLAN_SHA256'); print(render_summary(operator_summary(r)))"
```

This creates local confirmation authority only; it never calls confirm or connects
to devices. Use a newly exported four-row Pending Gi0/6 plan with distinct SI
445/30/31/32 and disjoint valid ingress selectors in rows 5–8. Inspect the original
all-Pending JSON and workbook: both parent commands appear only in row 5. Edit
decisions to Pending/Approve/Reject/Approve: selected rows 6 and 8 retain their
original CLI with no parent commands. Repeat with row 5 Rejected, then all Approved:
setup stays only on row 5, never reassigned. An already initialized parent produces
no setup on any row. Original JSON/digest must remain unchanged.
Fresh device checks and partial-failure behavior require separate owner-controlled
lab validation using the lab commands above; do not replay historical plans.
