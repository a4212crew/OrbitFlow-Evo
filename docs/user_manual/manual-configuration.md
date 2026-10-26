# Manual Configuration (Issue #156)

A separate console and Python API workflow executes literal multiline Excel rows.
It does not execute or convert legacy Manual CLI plans. Predefined plan execution
retains its device-end partial-save policy. Owner-supplied run evidence is recorded below; deterministic validation uses
synthetic sessions. Fresh EdgeSwitch live validation remains pending.

Start from the repository with its dependencies installed. Linux Bash:

```bash
PYTHONPATH=src python -m orbitflow.menu
```

Windows PowerShell:

```powershell
$env:PYTHONPATH = "$PWD\src"
python -m orbitflow.menu
```

In **Environment Setting → Edit environment profile**, configure the existing
Teleport routing, pacing, separate device workbook and inventory path. Authenticate
Teleport externally using `tsh status` / operator-controlled `tsh login` as usual.
Then choose **Set/change manual authorization password**. Enter a new 12–1024
character password twice using hidden input. Changing an existing password also
requires the current password. Only a random 32-byte salt and PBKDF2-HMAC-SHA256
hash with 600,000 iterations are stored in the optional
`manual_configuration_auth.password_hash` profile field. No plaintext password is
stored. Keep the local profile protected by OS permissions; the local gate is not
tamper-proof authentication. Old profiles remain valid without this section;
manual execution fails closed until it is configured. Ordinary environment edits
preserve the hash. Never copy the hash or credentials into reports or tickets.

Choose **Configuration Management → Manual Configuration**:

1. **Generate Manual Input Template** allocates
   `data/input/generated_template/manual_config_YYYYMMDD_NNN.xlsx` exclusively.
2. Fill the active worksheet, with exactly `management_ip` and `command` columns
   in row 1; input starts at row 2. Use Alt+Enter between commands in one cell.
   Connection credentials belong in the separate existing device workbook, whose fields
   are `management_ip`, `username`, `password`, optional `secret` (enable).
3. **Execute Manual Configuration** lists eligible `manual_*.xlsx` files in the profile
   templates directory (newest modification time first, filename order for ties).
   Excel temporary files and directories are excluded. Select a number, the explicit
   file-path option (also requiring `manual_`), or `b` to cancel; invalid selections
   reprompt. An empty directory still offers explicit path and cancellation.
   Select the separate credential workbook. The workflow
   prompts concurrency 1–5 (blank=1; never persisted), shows row/device/command and
   invalid-row counts, verifies the hidden authorization password and requires an
   explicit run-summary confirmation. Declining or a wrong password causes no
   device connection. Teleport validation follows these gates.
4. **Regenerate Manual Report (offline)** takes a retained run directory. It works
   without a profile, credentials or a network session and never replays commands.
5. **Back** returns to Configuration Management.

A command cell can contain, for example:

```text
interface GigabitEthernet1/0/1
 description Customer Site
 exit
```

Each row starts in confirmed global configuration mode. Include the hierarchy
needed by your block. Literal nonblank command whitespace and order are preserved. Leading, interior,
trailing and whitespace-only separator lines are ignored, with LF/CRLF treated
consistently. Original cell line numbers remain in internal command intents. An
entirely empty block reports “Invalid input: command block contains no executable
commands” before networking; only executable lines count. Commands are accepted
without semantic allowlists, denylists, abbreviation or keyword bans: `configure`,
`conf`, wrappers, unknown roots and explicit write/save/commit execute literally.
The device determines validity. Unicode text is accepted; control characters
(including tabs, ESC, bare CR, DEL/C1 and Unicode line separators), formula cells,
nontext cells, invalid IPs and oversized blocks fail with fixed structural categories.
Whitespace-only separator lines are ignored and never transmitted.
Control-character errors identify the original one-based cell line without echoing
input. Each cell is limited to 32,767 characters and 1,000 nonblank commands; a
workbook is limited to 10,000 nonempty rows. Secrets in authored CLI are accepted
and redacted from evidence independently of command acceptance. Protect the source
workbook; it is never copied to run artifacts. Network login/enable credentials
still come from the separate credential workbook. Unsupported interactive questions
stop Incomplete without an automatic answer, including when explicitly authored
save commands ask questions. Session-ending commands can disconnect and leave an
Incomplete outcome. No raw invalid cells are retained in artifacts.

| Platform | Login/identity and backup | Manual entry/save |
|---|---|---|
| Cisco IOS / IOS-XE | Shared transport, enable, inventory and configuration capture | `configure terminal`, confirmed global mode; synchronized `end`, shared `write memory` exchange. Platform-wide framing includes Catalyst, ME3600X and ASR920; individual commands remain engineer responsibility. |
| Ubiquiti EdgeSwitch | Shared transport, enable, inventory and capture | `configure`, confirmed global mode; synchronized `end`, shared `write memory`; only the existing recognized save question receives `y`. |
| Cisco IOS-XR | Shared identity/capture exist | Blocked before user writes: candidate ownership, commit and completion confirmation are not implemented in the shared save contract. |
| Huawei VRP | Shared identity/capture exist | Blocked before user writes: system-view synchronization and save-question/completion handling are not implemented in the shared save contract. |
| Junos / other | No workflow support | Unsupported; no invented driver or command fallback. |

Different IPs use shared bounded device execution. Repeated/noncontiguous IPs keep
workbook order on that device's worker and share its healthy underlying transport
and one transcript, but **never share a live shell**. Each row opens, identifies and
prepares a fresh shell; its channel closes directly after the row even from an
unknown submode. A protected pre-change backup is collected before each row's
user writes. Backup failure blocks that row and later rows on the same device.

User command capture does not inspect prompts or infer modes. Defaults are 10s for
first response, 1s receive inactivity and 30s overall per command. API settings must
be finite positive seconds, at most 300s, with overall greater than first response
and inactivity. Setup defaults to 30s and save to 60s. Capture is limited to 8 MiB
per row and 64 KiB per unterminated line. Inactivity is not proof of completion;
delayed data can cross command boundaries. The continuous device transcript is
authoritative. Supported rejection strings and interaction requests fail the row.
No automatic configuration retries, unknown-question answers or speculative rollback
are performed. Setup and finalization use prompt-aware synchronization.
Finalization accepts the exact `end` echo from the current structural prompt,
including a changed hostname or interface/subinterface/service mode (or a plain
command echo). It waits for receive quiescence before learning a fresh privileged
EXEC anchor for the single save exchange. Missing echoes, trailing output,
rejection, interaction or disconnect prevent save. This manual-only exchange does
not change predefined or read-only synchronization.

Rejection classification uses anchored vendor diagnostics rather than generic
error words anywhere in the capture. Literal echoes such as `description FAILED
LINK`, `description Customer Error Monitor`, and error-like hostnames do not alone
fail a row. Fragmented diagnostics remain detectable across receive chunks. The
complete sanitized receive transcript is retained; no prompt determines user-block
completion.

A row is **Completed** only after capture, durable sanitized evidence, mode
synchronization and a confirmed save with no explicit save error. The report says
**Transcript only — configuration not independently verified**. All failures are
**Incomplete**, with stage/reason, attempted/total commands, source row, last
attempted command index and separate save status. Any failed/unknown row suppresses
new automatic saves and later commands for that device; later rows are Not attempted.
Independent devices may continue. Interrupted transmission of save is **Unknown**;
a save already sent cannot be recalled or retried. Ctrl+C notifies active workers
to stop before further commands/save, while in-flight exchanges finish or time out.
Not saving does not undo running changes. Whole-config save may persist unrelated
changes. **Never automatically replay/resume Completed or Unknown changes.**

Artifacts use collision-safe run/template allocation:

- `outputs/runs/manual_configuration/<run-id>/`: manifest, sanitized fsynced
  `events.jsonl` and bounded shared results spool. Row identity, timing, source-line
  mapping, sanitized command intents and real capture references remain internal.
  Historical captures under old run directories are still recoverable.
- `outputs/backups/configuration/<run-id>/`: existing protected configuration
  backups; treat these as sensitive and never publish them.
- `outputs/reports/manual_configuration/YYYYMMDD_HHMMSS/`: ONE consolidated
  `manual_output_YYYYMMDD_HHMMSS.xlsx` with every input row in original order,
  including repeated IPs, and a concise `Devices` summary. The same workbook is
  atomically refreshed after EACH device finishes while peers continue. The console
  immediately prints `Updated consolidated report: <workbook path>` and
  `Capture folder: <report directory>`; use workbook links for actual named captures. Pending
  rows are Incomplete/Not attempted, never Completed. Captures are named
  `<sanitized-hostname>_<sanitized-ip>.txt`, with IP fallback before identification.
  Safe rename failures retain the fallback and real journal references. Relative
  hyperlinks resolve when the whole report directory is moved. Missing captures
  say `Not captured` without a link. Excel-held files/export failures preserve the
  previous valid workbook and journals for offline regeneration without replay.
  New run and backup folders share the short timestamp, with numeric collision
  suffixes only. Historical long run directories remain recoverable.
  The capture contains only sanitized received terminal text, including genuine
  echoes, prompts and finalization/save output when available. It has UTF-8/CRLF
  Notepad formatting, no application labels/timestamps or synthetic command echoes,
  and no inserted newline per network chunk. Complete lines flush/fsync incrementally;
  an unfinished line is bounded and flushed at block completion/error. Setup/enable
  exchanges remain excluded. The source workbook is unchanged.
- `outputs/logs/manual_configuration/YYYY-MM-DD/`: concise sanitized stage logs.

A recording failure stops further device writes. Retain the run if report writing
fails. Offline recovery ignores an incomplete final journal line, reports missing
row results as Incomplete, and treats a save intent without a durable confirmed
result as Unknown. A missing input snapshot cannot be recovered. Disk failures may
prevent even failure records; recovery never infers success from a returned worker
or an interrupted run. No CLI transcript establishes independent configuration
verification.

## Automated and owner-operated validation

Run these checks from the final controller-produced revision checkout, with its
project dependencies installed. Worker test results do not establish a controller
Git/PR gate or Windows/live validation. Full-suite controller tests require a
writable OS temporary directory outside every Git checkout; this managed worker
has read-only `.git` markers under `/tmp` and its supplied temp root, causing
controller-temp rejection independently of the manual changes.

Linux Bash deterministic checks:

```bash
PYTHONPATH=src python -m pytest tests/test_manual_configuration.py tests/test_operations_console.py tests/test_device_execution.py tests/test_result_spool.py tests/test_configuration_execution.py tests/test_shared_cli.py tests/test_cisco_ios_cli.py tests/test_cli_lifecycle.py tests/test_cisco_terminal_width.py tests/test_edgeswitch_angle_prompt.py tests/test_prompt_banners.py tests/test_configuration_execution_evc.py tests/test_configuration_execution_stages.py -q
PYTHONPATH=src python -m pytest -q
```

Windows PowerShell deterministic checks:

```powershell
$env:PYTHONPATH = "$PWD\src"
python -m pytest tests/test_manual_configuration.py tests/test_operations_console.py tests/test_device_execution.py tests/test_result_spool.py tests/test_configuration_execution.py tests/test_shared_cli.py tests/test_cisco_ios_cli.py tests/test_cli_lifecycle.py tests/test_cisco_terminal_width.py tests/test_edgeswitch_angle_prompt.py tests/test_prompt_banners.py tests/test_configuration_execution_evc.py tests/test_configuration_execution_stages.py -q
python -m pytest -q
```

Owner-operated fresh isolated lab validation remains pending. Use disposable lab
changes with recovery access; never replay previously completed/Unknown changes:

1. Decline confirmation, then use a wrong password on another attempt. Confirm
   zero device connections in operator-controlled connection monitoring.
2. Use two successful noncontiguous rows for one lab IP and one independent IP.
   Confirm fresh shell channels, workbook order, pre-row backups and one confirmed
   save per successful row; inspect the continuous transcripts and report. After
   each device completes, confirm the console immediately names the same existing
   consolidated workbook and its existing capture folder, with no `capture.txt`
   path or per-device workbook claim. Include
   interface/subinterface/service submodes, a hostname change, and descriptions
   containing FAILED/Error in fresh disposable rows. Confirm finalization learns
   the new EXEC anchor and each successful row saves exactly once.
3. Use a syntactically rejected command in a fresh lab run, followed by another
   row for that IP and one safe peer. Confirm no save after the failed block and no
   later writes for that IP; confirm the independent peer completes when safe.
4. Interrupt a fresh lab save after transmission. Retain Unknown, initiate no retry
   and reconcile actual device persistence externally before any new change.
5. Disable network access and regenerate reports from successful, failed and
   interrupted runs. Confirm every source row, Unknown preservation, transcript
   references and no connections. Exercise output-write failure using a controlled
   unavailable destination, then recover to a new filename.

The [public API reference](../operations/manual-configuration-api.md) documents
non-console use. Historical offline Manual CLI workbook/plan/report recovery remains
supported, with unchanged v1/v2 integrity and template identifiers. New planning
input omits its worksheet/navigation; canonical v2 plan layouts retain an empty
legacy slot for compatibility.

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

### Fresh usability lab validation (owner only; pending)

Start a **new**, reviewed lab workbook named `manual_lab.xlsx` using the console
commands above; never select previous Completed/Unknown operations for replay.
Use two lab IPs and noncontiguous repeated rows for the first IP. Include leading,
interior and trailing Alt+Enter separator lines. First decline confirmation, then
try a wrong admin password: observe no connection. On a separately authorized
fresh run, verify each successful duplicate-IP row opens a new shell and saves
individually. Keep the second device busy and verify the same consolidated workbook with the first device completed, the second pending, and its
clickable capture appear before the second finishes. Open the report in Excel on
Windows; move its entire report directory and verify its hyperlink still opens.
On another fresh scenario induce a supported device rejection: verify no row save,
later same-IP rows not attempted, independent-device output available. Separately
interrupt an owner-controlled save after transmission: preserve Unknown, never
retry/replay. Use the offline recovery commands in the API guide to regenerate
reports from retained journals, including a missing historical capture (no link).
Confirm captures contain device receive text only, redacted, without chunk headers.

Run the full deterministic gate separately from focused worker regressions. Linux Bash:

```bash
PYTHONPATH=src python -m pytest -q
PYTHONPATH=src python -m pytest tests/test_orchestration_v2_codex_runner.py tests/test_orchestration_v2_controller.py tests/test_orchestration_v2_lifecycle.py -q
```

Windows PowerShell:

```powershell
$env:PYTHONPATH = "$PWD\src"
python -m pytest -q
python -m pytest tests/test_orchestration_v2_codex_runner.py tests/test_orchestration_v2_controller.py tests/test_orchestration_v2_lifecycle.py -q
```

Report worker and controller results separately. This Codex sandbox marks its writable
OS-temp roots with protected `.git` directories; controller tests correctly refuse
those roots through the existing external-temp guard. Run the controller gate in its
normal controller environment. Do not remove those markers or relax the guard.
Linux synthetic tests do not establish native Windows/Excel or device validation.

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

## Superseding owner decision — literal manual commands (2026-10-26)

Approved correction for Issue #156 / PR #157: the manual sender accepts literal
engineer-authored CLI, including configure/conf, vendor abbreviations, unknown roots,
wrappers, credentials and explicit write/save/commit. Only structural input and
transport bounds apply. Device diagnostics determine rejection; unsupported questions
receive no automatic answer. Fresh-shell identity, enable, paging, backup and initial
global configuration entry remain required. User capture remains prompt-free.

Automatic save occurs only after successful capture and finalization. An explicit
engineer persistence command may already have saved before a subsequent failure;
“Not initiated” describes automatic save only, never proof that changes are unsaved.
No retry or rollback. Command acceptance and secret disclosure are separate: redact
SEND intent and buffered receive echoes/output before persistence; retain no source
workbook in run artifacts. Predefined planning/schema restrictions remain unchanged.
This supersedes older manual command restrictions above. This correction was reconciled as approved design before implementation; it is now
implemented on this branch. Automated evidence is recorded in the monthly devlog;
fresh owner EdgeSwitch validation remains pending.

Owner-supplied evidence: run 20261026_120437 showed ME3600X 12/12 and ASR920 2/2
with confirmed save, consolidated refreshes and named captures. EdgeSwitch input was
rejected before connection. This establishes neither EdgeSwitch live execution nor
independent configuration verification. Never replay those successful commands.

### Fresh EdgeSwitch correction validation (owner only)

Use the Bash/PowerShell menu and automated commands above against the final reviewed
head. Create a **new disposable** `manual_edgeswitch_lab.xlsx`; do not replay the
successful ME3600X/ASR920 rows from run 20261026_120437. Review unused lab VLANs and
ports, then author this sequence with blank separator lines and lab-specific values:

```text
exit

vlan database
vlan 3100-3102
exit
configure
interface 0/1
 description Disposable lab
```

Repeat the lab IP in a later noncontiguous row with a separately reviewed disposable
change, plus an independent lab device. First decline confirmation and try a wrong
password: verify no connection. On an authorized fresh run confirm exact nonblank
sends, fresh shell per row, per-row automatic save and immediate consolidated report
refresh with working relative capture links. In a separate fresh failure scenario,
induce a device diagnostic and confirm no new automatic save or later same-IP writes;
the independent peer may finish. A reviewed explicit persistence command can already
have saved before failure: the report's save column describes **automatic save only**.
Do not infer unsaved state. Exercise unsupported questions/disconnect and interrupted
automatic save (Unknown, no retry), then regenerate offline with networking disabled.
Use fake credentials for confidentiality checks; inspect sanitized captures and notes.
No independent configuration verification is implied by these transcript checks.
