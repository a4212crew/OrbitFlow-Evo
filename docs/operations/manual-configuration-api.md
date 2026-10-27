# Manual Configuration Python API

`orbitflow.configuration.manual` is the reusable application service beneath the
console. It executes engineer-authored blocks, not v1/v2 plans. See the
[operator manual](../user_manual/manual-configuration.md) for platform gaps, exact
paths, limits, persistence risks and owner lab checks. Owner-supplied run evidence
is recorded below; fresh EdgeSwitch validation remains pending.

Public functions:

| Function | Contract |
|---|---|
| `create_template(directory='data/input/generated_template')` | Offline; returns an exclusively allocated `Path` named `manual_config_YYYYMMDD_NNN.xlsx`. |
| `load_rows(path)` | Offline; returns source-ordered row dictionaries: `source_row`, `management_ip`, `commands` (literal nonblank list), `error`, and optional `command_lines` (original one-based cell lines). Invalid cells are discarded with a fixed diagnostic; malformed headers or >10000 rows fail the workbook. |
| `summary(rows, execution_config=ExecutionConfig(1), settings=CaptureSettings())` | Offline; returns digest, rows/devices/commands/invalid counts and concurrency. Digest binds exact ordered row content and settings. |
| `execute(rows, *, profile, password, confirmation_digest, credentials, transport_config, execution_config=ExecutionConfig(1), settings=CaptureSettings(), inventory_path='data/inventory/inventory.json', run_root='outputs/runs/manual_configuration', backups_dir='outputs/backups/configuration', progress=None, on_started=None, reports_dir='outputs/reports/manual_configuration', on_output=None)` | Network/apply; verifies local password and exact summary confirmation before allocation or connection. Copies and validates rows; groups same-IP rows, using shared device scheduling and per-row fresh DeviceSession connections and CLI channels. Returns retained run `Path`; refreshes one consolidated workbook through the scheduler completion callback before waiting for other devices. Configuration exceptions produce Incomplete row records; persistence/interrupt failures can propagate with recovery retained. Never retry the run automatically. |
| `regenerate_report(run_path, output=None, *, reports_dir='outputs/reports/manual_configuration', management_ip=None, replace=False)` | Offline; returns an exclusively allocated report `Path`. Defaults under `outputs/reports/manual_configuration/`; explicit existing paths fail unless replace=True requests atomic refresh. Reads durable input/intents/results, never network or replay. |

`CaptureSettings(first_response=10.0, inactivity=1.0, maximum=30.0,
setup_timeout=30.0, save_timeout=60.0)` requires each deadline to be finite and in
(0, 300], with maximum greater than first_response and inactivity.
`ExecutionConfig` permits manual concurrency 1–5 only; default 1, nonpersistent.
Connection pacing uses existing execution config semantics. Input must originate
from `load_rows` or obey exactly its validated schema. Source rows must be unique
integers ≥2, with valid IPs for executable rows, bounded literal commands and fixed
validation errors. No semantic command restrictions apply to this manual sender. Credential-bearing
CLI, wrappers, abbreviations and explicit persistence commands are accepted literally.
Structural errors are fixed categories (IP, cell type, formula, size/count, empty block,
or control character with original cell line); no invalid content is echoed.

`credentials` maps IP to existing `DeviceCredentials`; use
`orbitflow.targets.load_device_credentials(devices_workbook, ips, provider=None)`
for shared workbook/provider precedence. Login/enable credentials are resolved separately. Authored CLI may contain secrets;
protect the manual XLSX. It is never copied to run artifacts.
`transport_config` is the existing `TransportConfig`, with no alternate SSH path.
API callers own externally controlled Teleport validation and secure hidden password
input. The API requires an explicit summary digest; callers must present the summary
and pass it only after affirmative operator confirmation. This is a local intent
gate, not tamper-proof authorization or a remote authentication boundary.

`progress` accepts serialized scalar events through existing `Progress`; subscribers
never access channels and their failures disable display only. `on_started(path)`
receives the retained run directory before network execution, so callers can report
recovery locations even when execution fails. A callback exception before execution
causes no connection. `on_output(Path)` is called serially by the scheduler after each successful consolidated
report refresh (including reports of failed devices), while other workers may still
run. The console presents this path as `Updated consolidated report` and its
parent directory as `Capture folder`; the callback does not supply an individual
capture filename. Export failures append a fixed `report_export_failed` journal event and preserve
results for offline recovery, without retrying network writes or blocking other
device exports. Subscriber exceptions are recorded as publication failures.
`reports_dir` controls capture/report ownership; default run directories are
`reports_dir/YYYYMMDD_HHMMSS`. `regenerate_report` optionally filters one IP; its
default whole-run export includes every input row. It preserves historical capture
references and only links to files that exist. Cross-drive Windows links fall back
to file URIs; otherwise links are relative and portable with their capture directory.
Artifact roots can be overridden; unrelated workflows keep
their existing defaults. Logs use shared `module_logger` ownership and context.

An interactive Python adapter can use this pattern (never hardcode a password):

```python
from getpass import getpass
from orbitflow.environment import load_profile, validate_session
from orbitflow.config import ExecutionConfig
from orbitflow.transport import TransportConfig
from orbitflow.targets import load_device_credentials
from orbitflow.configuration.manual import load_rows, summary, execute, regenerate_report
from orbitflow.configuration.manual_auth import authorize

profile = load_profile()
rows = load_rows('manual.xlsx')
config = ExecutionConfig(1, **profile['execution'])
bound = summary(rows, config)
print(bound)  # Counts and digest only, never profile or credentials.
password = getpass('Manual authorization password: ')
authorize(profile, password)
if input('Confirm manual execution? [y/N]: ').lower() == 'y':
    validate_session(profile)
    credentials = load_device_credentials(profile['paths']['devices'],
                                          [r['management_ip'] for r in rows])
    path = execute(rows, profile=profile, password=password,
                   confirmation_digest=bound['digest'], credentials=credentials,
                   transport_config=TransportConfig(**profile['teleport']),
                   execution_config=config, inventory_path=profile['paths']['inventory'],
                   on_started=lambda path: print('Retained run:', path),
                   on_output=lambda path: print('Batch report refreshed:', path))
```

For offline recovery, Linux Bash:

```bash
PYTHONPATH=src python -c 'from orbitflow.configuration.manual import regenerate_report; import sys; print(regenerate_report(sys.argv[1]))' outputs/runs/manual_configuration/RETAINED_RUN_ID
```

Windows PowerShell:

```powershell
$env:PYTHONPATH = "$PWD\src"
python -c 'from orbitflow.configuration.manual import regenerate_report; import sys; print(regenerate_report(sys.argv[1]))' outputs/runs/manual_configuration/RETAINED_RUN_ID
```

A report includes source row/IP, Completed/Incomplete, precise safe stage/reason,
attempted/total commands, last attempted source command index, save status,
verification scope and transcript reference. No independent configuration verification
is implied. Interrupted/missing row results remain Incomplete; save intent without
confirmed result remains Unknown. Output failures retain evidence for another
**report-only** attempt, never a network replay. API callers must protect retained
records and especially pre-change configuration backups.

Manual finalization synchronizes the exact `end` echo from the current structural
prompt (including changed hostname/submode) or plain echo, then establishes a fresh
privileged EXEC save anchor after receive quiescence. User-block capture remains
prompt-free. Anchored vendor diagnostics classify rejection independently of the
complete sanitized transcript; error words in descriptions/hostnames alone do not
reject a row. Missing synchronization or actual rejection prevents save and later
same-device rows. Predefined/read-only synchronization and partial-save policy are
unchanged.

## Owner-approved usability revision — implemented on this branch

Issue #156 now accepts blank command-cell separator lines while retaining literal nonblank
commands and original line numbers. Manual input selection lists only manual_*.xlsx
newest first, with explicit-path fallback. One consolidated manual_output_YYYYMMDD_HHMMSS.xlsx workbook is allocated before
network execution and atomically refreshed after each device task ends. Its Devices
sheet summarizes devices and Manual Configuration sheet retains every input row in
workbook order. Receive-only <safe-hostname>_<safe-ip>.txt captures live beside it
in outputs/reports/manual_configuration/YYYYMMDD_HHMMSS/. Run and backup directories
use the same short name, with numeric collision suffixes.
Reports link to real captures using portable relative hyperlinks. Structured timing,
row identity and send intents remain in the internal run journal. Legacy recovery
retains real historical capture references; missing captures have no invented link.
This supersedes timestamped/labelled captures, run-directory capture defaults, blank-line
rejection and batch-only export. Existing authorization and device safety rules remain.
No live validation is implied.

## Owner correction — consolidated output (implemented on this branch; lab validation pending)

This revision supersedes earlier per-device workbook examples. One consolidated
workbook contains every input row in order and a device summary, refreshed atomically
at the serialized device-completion boundary. Pending rows never imply success.
New manual run/report/backup directories use YYYYMMDD_HHMMSS with short numeric
collision suffixes. The workbook is manual_output_YYYYMMDD_HHMMSS.xlsx; receive-only
captures beside it are <sanitized-hostname>_<sanitized-ip>.txt with IP fallback.
Durable references follow safe identity renames; historical recovery remains supported.
The console retains the batch count, hidden password and explicit confirmation,
removing explanatory warnings before the password. Execution/save safety is unchanged.

`replace=True` stages a complete workbook in the destination directory, fsyncs it,
then uses atomic replacement. A held destination or export failure preserves the
previous workbook; temporary files are removed. `Manual Configuration` retains row
order, `Devices` summarizes all targets and links captures, and `Run Notes` retains
scope and limitations. The shared spool's opt-in `short_name=True` uses exclusive
UTC timestamp/numeric directory allocation; unrelated callers keep existing names.

## Literal manual CLI correction (2026-10-26)

Implemented on this branch: the manual sender accepts literal commands without
semantic command restrictions. Device diagnostics and unsupported interactions can
still stop Incomplete; no automatic answer, retry or rollback occurs. Fresh-shell
setup/backup, prompt-free capture and successful-row-only automatic save remain.
Secrets are redacted independently of acceptance, including fragmented echoes and
conservative masking of partial credential operands. This exception does not change
predefined schemas or policies. The report `save` column describes automatic save
only; explicit authored persistence may already have executed before failure.
`Not initiated` never asserts unsaved state. See the [owner evidence and fresh lab
checks](../user_manual/manual-configuration.md#superseding-owner-decision--literal-manual-commands-2026-10-26).

## Approved connection correction — Issue #158

The owner-approved correction supersedes Issue #156 statements about sharing a
healthy transport or one connection per IP. Historical source/tests reused one
DeviceSession per IP with a new shell per row. This approved correction was
recorded before implementation on this branch; source/tests establish historical
behavior. Issue #158 now gives each valid executable row a fresh connection through
shared `connect_device`, a fresh shell, identity and protected backup, and closes
its entire transport chain before the next row. One worker per IP, original row
order and one device capture remain. Invalid/stopped rows never connect.
Repeated authentication/tunnel setup adds connection overhead and shared pacing.
Owner run 20261027_064039 showed a second-row setup EOF; its exact failing operation
and server-side cause are unproven. Never replay the completed first row.

Setup failures use fixed sanitized stages: `connection establishment`, `shell
opening`, `initial prompt/session preparation`, `privilege`, `identification`,
`backup` and `config entry`. Categories include Timeout, Connection closed,
Operation failed and Interrupted; approved fixed diagnostics remain available.
No arbitrary exception text or received setup text enters the row reason. Shell
cleanup and every owned transport cleanup are attempted before recording the row.
A cleanup failure stops later same-device rows and adds a fixed cleanup reason; a
row already Completed/Saved retains that evidence. Other devices may continue.
No user command or save is retried. Only the existing shared establishment-only
retry policy applies before a session is returned. Explicit user persistence and
predefined partial-save behavior remain independent.

The backward-compatible shared `DeviceCLI(session, *, timeout=10.0,
setup_stage=None)` constructor accepts an optional callback receiving only the
fixed setup stage strings above (shell, initial preparation and privilege). Existing
callers omit it. The caller still owns the parent DeviceSession. A shell cleanup
failure during failed construction raises `CLICleanupError`; the parent transport
still requires cleanup. Internal vendor manual setup similarly accepts optional
`setup_stage`; read-only and predefined setup policies are unchanged.

Protected skill reconciliation is provided as an exact
[Atlas handoff](issue-158-atlas-handoff.md); `.agents/` was not modified.
