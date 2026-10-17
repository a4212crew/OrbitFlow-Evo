# Catalyst and EdgeSwitch configuration execution

Issue #117 implements the [approved execution contract](../architecture/configuration/approved-device-execution.md).
This is a configuration-changing workflow for predefined C3750X, C3850 (worksheet
label C3850X) and EdgeSwitch VLAN Database, supported port and Description templates.
Other families and Manual CLI execution remain unsupported. v1 and v2 planning
commands retain their existing behavior. No live/lab execution has been validated.

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

`execute` prepares without connecting and renders a concise operator summary: execution
reference, short plan digest (full digest retained programmatically and in summary.json),
device/change/no-op/skipped counts, concurrency, ordered hostname/IP/family and template/
action counts, source-row warnings and blockers. Offline known state is distinguished
from fresh identity/state/prerequisite/backup checks after confirmation. Full approved
CLI and evidence remain in the reviewed plan and digest-bound preparation result.
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
