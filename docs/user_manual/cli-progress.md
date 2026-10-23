# CLI progress and durable results (Issue #144)

Direct batch CLIs and eligible console actions share `orbitflow.terminal_progress`
presentation and the existing device runner and result spool. Device operations,
CLI arguments, confirmation, concurrency, file formats and recovery policies are
unchanged. This revision has deterministic fixture coverage; owner-operated Linux
and Windows terminal/device validation remains pending.

On a sufficiently large VT-capable terminal, the display reserves a row for each
configured worker, including concurrency 1, and rotates at most ten recent events.
Rows identify the input position and canonical device IP when available. Positions
remain distinct even for repeated addresses. Idle workers retain their own rows;
a freed slot accepts the next input immediately. Only high-level fixed stages and
allowlisted execution fields appear. Commands, raw configuration, hostnames and
exception messages never become dashboard events. A generic `processing` stage
means the workflow has not published a more specific stage.

Representative snapshot (values depend on actual outcomes):

```text
Collection records [2/4] | success=1 failed=1 active=2 unknown=0
Worker 1: input 3 (192.0.2.3) | connect | active
Worker 2: input 4 (192.0.2.4) | normalize | active
Recent activity (last 10):
input 2 | failed
input 3 (192.0.2.3) | connect
input 4 (192.0.2.4) | normalize
```

The counter advances once per recorded target outcome, after the spool checkpoint,
including failed outcomes. Row, command and stage events never advance it. A shared
runner without a spool reports **processing** returns; these alone do not establish
collection success. Unknown counts represent outcomes that presentation cannot
classify, and on interruption include missing outcomes. `active` means an owning
worker or execution stage remains active, not that a device is responsive. Wait
updates and elapsed time never establish device liveness. No stage percentage or
export row count is estimated.

Frames refresh at most ten times per second when events arrive; elapsed waiting
refreshes are periodic. There is no device polling for presentation. Rendering is
serialized independently of device work. Small terminals, `TERM=dumb`, and Windows
consoles without detected VT support use a compact carriage-return line. Windows
Terminal (`WT_SESSION`) and ANSICON use the full frame when it fits. No `clear`,
`cls`, curses or Unix-only terminal calls are required. Resizing to a compact
terminal clears the previous frame. Final summaries and paths are complete lines,
including on a narrow terminal.

Redirected/non-TTY output uses initial/final lines and at most one intermediate
snapshot per five seconds per phase. Phase boundaries, saved paths and final
summaries are additional finite lines; it does not print every device/stage event.
For example:

```text
Collection records [0/4] | success=0 failed=0 active=0 unknown=0
Collection records [4/4] | success=3 failed=1 active=0 unknown=0; phase finished.
Collection collected: records=4/4; errors=1; report/export pending; spool: outputs/runs/TASK/RUN
Report/export stages [0/unknown] | success=0 failed=0 active=0 unknown=0
Export consumed: records=4/4; collection/processing errors=1; findings are separate; output: outputs/reports/TYPE/REPORT.xlsx; spool: removed after successful export
Log: outputs/logs/MODULE/YYYY-MM-DD/NAME.log
```

Paths above are illustrative. The terminal prints the actual run/output paths,
including explicit overrides. A collection summary precedes report generation;
`phase finished` does not mean every device succeeded or a workbook was saved.
Compliance collection/processing errors are distinct from compliant/noncompliant
findings in the workbook. Confirmed execution additionally retains its durable
row/device summary with Verified, Failed, Partial and Unknown classifications,
including independent save outcomes.

Interrupted collection prints the recorded fraction and retained spool; unrecorded
outcomes remain unknown. Export failure/interruption reports that no completed
output was established and retains recovery data under existing policies. An
explicit partial export says `partial_consumed`; it does not claim complete
collection. A consumer returning no existing output file says no saved file was
established. Empty collections may export a valid empty report, with 0/0 records.
Cleanup failure retains the run and reports its path; successful cleanup is reported
as removed. Backup workflows print their allocated folder before capture, so the
path remains available after interruption; folder allocation does not imply a
successful capture or failure-workbook export. Protected backup contents are never
printed. Module log paths are reported after presentation closes.

## Entry-point coverage

| Workflow / action | Progress and final evidence |
|---|---|
| `scripts/device_inventory_refresh.py`; console Inventory | Recorded target attempts, separate workbook export, actual inventory workbook/spool/log paths. |
| `scripts/device_interface_vlan_report.py`; console Interface/VLAN | Per-worker high-level stages, recorded device results, separate export and actual paths. |
| `scripts/device_vlan_compliance.py run`; console standard/methodology | Recorded device results; processing errors remain separate from compliance findings; each workbook export has its own phase. |
| `device_vlan_compliance.py export`; console report regeneration | Offline export stages, canonical record fraction in final summary, partial/retained/removed spool status. |
| `scripts/device_configuration_backup.py`; console Backup | Actual saved/failed captures, allocated folder and final failure workbook; no result spool is invented. |
| `python -m orbitflow.mac_cli search/list/export`; console Search/List | Shared collection, distinct input positions, separate workbook export; retained normalized MAC spool. Single search uses one worker. |
| `python -m orbitflow.configuration.v2.cli input/plan`; console input/planning | Stage activity for offline work; recorded observations for live planning; actual input workbook or immutable JSON/decision-workbook paths. Observation completion does not establish plan export completion. |
| `python -m orbitflow.configuration.execution_cli execute/report`; console execute/regenerate | Stage events only after explicit apply confirmation; once-per-device durable counts, independent export, protected backup/run/log paths. No retry/replay of Unknown changes. |
| Console executed-plan review, environment setup, selection/cancellation | Immediate local views/prompts retain their existing output. No background worker or device counter applies. |
| `scripts/configuration_plan.py` (retired v1 compatibility CLI) | Existing atomic local lifecycle results (digest/decision/preview) remain the result experience. No live device/dashboard applies; preview output is intentionally preserved. |
| `scripts/live_validate_inventory.py`, `live_validate_vlans.py` | Specialist source-configured single-device inspection retains normalized facts and result output. No shared multi-device workers; presentation must not replace the inspected facts. |
| `scripts/live_validate_inventory_batch.py` | Specialist sequential validation retains one success/failure per input and final actual Total/Successful/Failed, Results and Log paths. Its existing sequential validation contract is exempt from multi-worker dashboard rendering. |
| `scripts/live_validate_interfaces.py` | Library helper with explicit output ownership; no standalone CLI main. Caller receives records and the observed list. |
| `scripts/configuration_execution_timings.py` | Offline JSON analysis retains machine-readable stdout, warnings on stderr and existing sample counts; adding a live dashboard would corrupt the JSON interface. |
| `scripts/orchestration_v2/controller.py` | Serial task lifecycle/watch utility retains dry-run, no-work, ready-for-review and stopped/error messages. No device denominator or saved network report applies. Existing subprocess/controller logs remain authoritative; no lifecycle or Git/GitHub operation is added. |

These are presentation-specific exemptions, not new menu exclusions or new device
operations. Specialist validators and development/controller tools remain outside
the operator menu. All direct CLI flags and console selection/cancellation remain
as documented in their individual guides. Library calls retain their output
ownership; presentation is enabled at CLI/menu boundaries. Python-only regeneration
APIs remain quiet unless explicitly used within a presentation context.

For deterministic checks, run:

```bash
PYTHONPATH=src:. python -m pytest tests/test_workflow_progress.py tests/test_terminal_progress.py tests/test_operations_console.py tests/test_device_execution.py tests/test_result_spool.py -q
```

On PowerShell with the repository environment installed, use `python -m pytest`
with the same test paths. Simulated terminal/platform tests do not constitute live
PowerShell/Linux terminal or network validation.
