# Catalyst and EdgeSwitch configuration execution

Issue #117 implements the [approved execution contract](../architecture/configuration/approved-device-execution.md).
This is a configuration-changing workflow for predefined C3750X, C3850 (worksheet
label C3850X) and EdgeSwitch VLAN Database, supported port and Description templates.
Other families and Manual CLI execution remain unsupported. v1 and v2 planning
commands retain their existing behavior. Owner C3750X/EdgeSwitch validation of PR #118
was reported; C3850 and the Issue #125 optimizations still require owner lab validation.

Use the repository Python environment (Python 3.11+, `requirements.txt`) with `src`
on `PYTHONPATH`. Authenticate Teleport interactively and check `tsh status` first.
Linux requires the active Teleport key/certificate through the existing transport;
Windows retains the existing local forwarding transport. Device credentials come
from a separate protected `devices.xlsx` (`management_ip`, `username`, `password`,
optional `secret`); never put credentials in the plan or review workbook.

## Inputs and confirmation

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
precede writes. Each row has fresh state validation; changed CLI, target, no-op
classification or projected result blocks that row instead of rerendering it under
the old confirmation. This conservative behavior may require replanning after drift.
Earlier verified changes are observed before subsequent rows; failed dependencies
are Not executed. Missing/unknown requested EdgeSwitch PVID/Include/tagging database
prerequisites block that port row. They never implicitly create VLANs.

Commands are sent individually. Rejection stops that row; deterministic known-mode
recovery permits safe independent rows to continue. Unsynchronized sessions send no
further commands. A post-send timeout is Unknown, remaining rows are Not executed;
other devices continue. No-op rows still verify freshly and send no configuration.
Down operational state does not fail configured-intent verification. Missing facts
produce Unknown, explicit mismatches Failed. Command rejection remains Failed even
if the subsequent observed state matches. Full-set trunk comparison preserves VLAN 1
and ALL/NONE semantics. EdgeSwitch Current, Configured and Tagging remain independent;
tagged/forbidden overlap alone creates no warning or extra lookup.

Save runs once after attempted configuration, including partial changes if the
session remains usable; wholly no-op/skipped tasks do not save. `write memory`
persists **all running configuration**, including unrelated pending changes.
EdgeSwitch can interrupt management; only its recognized save question is answered
`y`. Return to the original learned privileged EXEC prompt means Saved, without
requiring `[OK]`; explicit errors are recorded separately. Saved is not independent
proof of startup persistence. Timeout/disconnect before prompt return means Unknown;
there is no blind retry. Row verification and save status remain separate.

Each run retains `manifest.json`, `results.jsonl`, `summary.json`, and fsynced
`events.jsonl` under its unique run directory. Events include pre-send intent,
per-command responses/partial evidence, row verification, save, timestamps, categories
and log references. A crash between intent and response must be treated as Unknown.
The incremental journal survives incomplete device outcomes; recovery ignores a
torn final journal line. No automatic resume or rollback is available.

The CLI writes a separate `execution-results.xlsx`. Offline `report` requires only the
retained run and a new output filename; it performs no reconnect/apply/save. Run Summary
contains readable run/device/save/backup metadata. Original template-named sheets retain
row identity, source row, original inputs and decisions, including skipped/unsupported
rows with actual target identity. Main columns: Pre-config, Config Sent, Config Evidence
(post-row), Apply Status, Status Verification, Error, Warning, Save Status and Backup
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
exchange returned, not verified success. Saved still means original EXEC prompt return;
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
audit events, report columns and durable run layout are unchanged. Match `run_id`
and `digest` to `outputs/runs/configuration_execution/RUN_ID/manifest.json` and
`summary.json`; row records also include `row_id`, `template_id` and command index.
Timing records have message `Execution timing`, fixed stage/command category, outcome
and nonnegative seconds. No literal CLI, responses or exception messages enter timings.
Transport and standalone capability diagnostics retain their existing ownership.

Stages cover connection/admission/retry wait, shell setup, identification, initial
preflight, protected backup collection/write, full observation, interface collection,
VLAN/config collection, normalized snapshot/reuse, VLAN lookup, scoped evidence,
pre-row planning/drift checks, mode validation, every approved command and underlying
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

Each session owns one normalized observation manager, bounded to one projection and
8 MiB of serialized projection/input eligibility. Every row preflight and non-database
verification still performs full fresh interface/VLAN/config collection, including
no-op verification; every operational VLAN lookup remains fresh. Complete matching
fresh normalized inputs may reuse only deterministic snapshot/audit computation;
fresh observation timestamps are retained. Writes, mismatches, failed/uncertain
operations and loss of synchronization invalidate retained computation. Changed
facts force recomputation; oversized/incomplete inputs bypass reuse. No raw backup
or device output is cached. Scoped interface/config refresh was investigated but
cannot currently establish equivalent full-set preservation and drift coverage, so
full refreshes are intentionally retained for all eleven executable templates.
Protected backup, pre-row durable evidence, ordered approved commands, full projected
result comparison, dependencies, independent partial-change save and replay protection
remain mandatory. Other device families and Manual CLI apply remain unsupported.

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
python -m pytest tests/test_execution_observation_timing.py tests/test_configuration_execution.py tests/test_shared_cli.py -q
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
python -m pytest tests/test_execution_observation_timing.py tests/test_configuration_execution.py tests/test_shared_cli.py -q
python -m pytest tests/test_configuration_execution_performance.py -q -s
python -m pytest -q
python scripts/configuration_execution_timings.py --help
python scripts/configuration_execution_timings.py outputs/logs/configuration/YYYY-MM-DD/execution.log --run-id RUN_ID
python scripts/configuration_execution_timings.py outputs/logs/configuration/YYYY-MM-DD/execution.log outputs/logs/configuration/YYYY-MM-DD/execution.log.1 --run-id RUN_ID
```

The extraction script is entirely offline and needs only Python's standard library.
Required positional `logs` accepts one or more UTF-8 shared log files; optional
`--run-id` selects an exact manifest ID (default all runs in supplied logs). It prints
JSON per allowlisted stage/category with count/min/median/nearest-rank p95/max seconds.
It ignores malformed/torn/non-timing records and invalid durations; at 100,000 samples
it fails closed with exit 2, as for unreadable input. Empty selection returns `[]`.
It outputs no device text, credentials or raw CLI. Use disjoint retained files to
avoid double-counting; missing rotations make a comparison incomplete.

Owner-only lab comparison: retain a baseline revision's sanitized run/report and
logs, then use separately reviewed fresh lab plans on this revision. Start from
independently reconciled equivalent lab state; never replay completed or uncertain
production changes. Use the existing `execute` commands above after `tsh status`,
with the same explicit concurrency, timeouts and connection pacing, and confirm only
the authorized lab change. Exercise all C3750X/C3850/EdgeSwitch templates, no-op,
trunk Add/Remove/Replace, dependencies, external between-row drift, incomplete
switchport/lookup evidence, rejection, timeout and independent partial save. Inspect
pre-row evidence, exact ordered commands and row/save outcomes before comparing
stage counts/distributions. Baseline revisions without fine timings can supply only
retained counts/elapsed results; do not fabricate stage measurements. Use distinct
new lab plans/confirmations, preserve authority/replay state, and perform report-only
recovery with the documented `report` command. No live configuration or credentials
were used by Codex. Windows deterministic results do not establish Linux or owner
lab performance; all three families require owner validation of these optimizations.
