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

`execute` prepares without connecting, displays JSON containing the source digest,
identity/IP/family, selected ordered rows, exact CLI, verification commands,
dependencies/blockers, skipped rows, concurrency/timeouts and save behavior. It asks
`Confirm execution? [y/N]:`. Only `y` (case-insensitive) confirms. Any other response
declines without connecting. Review the entire summary before answering.

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
| `--backups-dir PATH` | Default `outputs/backups/configuration`; protected unique backup run |
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

The CLI writes a separate `execution-results.xlsx`. `report` regenerates from retained
files without credentials, reconnecting or reapplying. Sheets: Run Summary (manifest
and approved summary), Execution Results (row identity/decision/no-op/apply/verification/
device save status), Event Details (full literal JSON in numbered 30,000-character
parts). Interrupted command intents appear Unknown; untouched selected rows appear
Not executed. Original plan/review files are never edited. Excel values are literal;
long evidence is continued, not silently truncated. Keep complete run files for audit.

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
python -m pytest tests/test_configuration_plans.py tests/test_bulk_configuration_v2.py tests/test_configuration_v2_approved_services.py tests/test_shared_cli.py tests/test_result_spool.py -q
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
