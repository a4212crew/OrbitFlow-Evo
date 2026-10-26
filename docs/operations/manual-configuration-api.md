# Manual Configuration Python API

`orbitflow.configuration.manual` is the reusable application service beneath the
console. It executes engineer-authored blocks, not v1/v2 plans. See the
[operator manual](../user_manual/manual-configuration.md) for platform gaps, exact
paths, limits, persistence risks and owner lab checks. No live validation is claimed.

Public functions:

| Function | Contract |
|---|---|
| `create_template(directory='data/input/generated_template')` | Offline; returns an exclusively allocated `Path` named `manual_config_YYYYMMDD_NNN.xlsx`. |
| `load_rows(path)` | Offline; returns source-ordered row dictionaries: `source_row`, `management_ip`, `commands` (literal list), `error`. Invalid cells are discarded with a fixed diagnostic; malformed headers or >10000 rows fail the workbook. |
| `summary(rows, execution_config=ExecutionConfig(1), settings=CaptureSettings())` | Offline; returns digest, rows/devices/commands/invalid counts and concurrency. Digest binds exact ordered row content and settings. |
| `execute(rows, *, profile, password, confirmation_digest, credentials, transport_config, execution_config=ExecutionConfig(1), settings=CaptureSettings(), inventory_path='data/inventory/inventory.json', run_root='outputs/runs/manual_configuration', backups_dir='outputs/backups/configuration', progress=None, on_started=None)` | Network/apply; verifies local password and exact summary confirmation before allocation or connection. Copies and validates rows; groups same-IP rows, using shared device scheduling and per-row fresh CLI channels. Returns retained run `Path`. Configuration exceptions produce Incomplete row records; persistence/interrupt failures can propagate with recovery retained. Never retry the run automatically. |
| `regenerate_report(run_path, output=None)` | Offline; returns an exclusively allocated report `Path`. Defaults under `outputs/reports/manual_configuration/`; explicit existing paths fail. Reads durable input/intents/results, never network or replay. |

`CaptureSettings(first_response=10.0, inactivity=1.0, maximum=30.0,
setup_timeout=30.0, save_timeout=60.0)` requires each deadline to be finite and in
(0, 300], with maximum greater than first_response and inactivity.
`ExecutionConfig` permits manual concurrency 1–5 only; default 1, nonpersistent.
Connection pacing uses existing execution config semantics. Input must originate
from `load_rows` or obey exactly its validated schema. Source rows must be unique
integers ≥2, with valid IPs for executable rows, bounded literal commands and fixed
validation errors. Unknown command roots/abbreviations fail closed.

`credentials` maps IP to existing `DeviceCredentials`; use
`orbitflow.targets.load_device_credentials(devices_workbook, ips, provider=None)`
for shared workbook/provider precedence. Credentials never belong in manual XLSX.
`transport_config` is the existing `TransportConfig`, with no alternate SSH path.
API callers own externally controlled Teleport validation and secure hidden password
input. The API requires an explicit summary digest; callers must present the summary
and pass it only after affirmative operator confirmation. This is a local intent
gate, not tamper-proof authorization or a remote authentication boundary.

`progress` accepts serialized scalar events through existing `Progress`; subscribers
never access channels and their failures disable display only. `on_started(path)`
receives the retained run directory before network execution, so callers can report
recovery locations even when execution fails. A callback exception before execution
causes no connection. Artifact roots can be overridden; unrelated workflows keep
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
                   on_started=lambda path: print('Retained run:', path))
    print(regenerate_report(path))
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
