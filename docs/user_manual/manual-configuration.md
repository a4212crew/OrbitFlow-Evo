# Manual Configuration (Issue #156)

A separate console and Python API workflow executes literal multiline Excel rows.
It does not execute or convert legacy Manual CLI plans. Predefined plan execution
retains its device-end partial-save policy. No owner-operated live validation has
been performed for this workflow; deterministic validation uses synthetic sessions.

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
   Credentials belong only in the separate existing device workbook, whose fields
   are `management_ip`, `username`, `password`, optional `secret` (enable).
3. **Execute Manual Configuration** selects the command and credential workbooks,
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
needed by your block. Literal command whitespace and order are preserved. Empty
lines, non-ASCII/control characters, tabs, formulas, credentials, save/commit/copy/write and
their abbreviations, execution wrappers (`do`, `run`), aliases, scripts, banners,
pagination and interactive exchanges are rejected or fail incomplete. Unknown or
abbreviated command roots fail closed as potentially ambiguous aliases. Supported
full roots are exposed as `orbitflow.configuration.manual.CONFIG_ROOTS`; these
include interface/VLAN/description, switchport, routing, EVC and common configuration
commands. `no`/`default` require a supported full second root. This is structural
screening, not semantic safety validation. Existing credential-bearing input checks
also apply (including the shared 256-character command-text limit). Each cell is
limited to 32,767 characters and 1,000 nonempty commands; a workbook is limited to
10,000 nonempty rows. No raw invalid command cells are retained in run artifacts.

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
new saves and later commands for that device; later rows are Not attempted.
Independent devices may continue. Interrupted transmission of save is **Unknown**;
a save already sent cannot be recalled or retried. Ctrl+C notifies active workers
to stop before further commands/save, while in-flight exchanges finish or time out.
Not saving does not undo running changes. Whole-config save may persist unrelated
changes. **Never automatically replay/resume Completed or Unknown changes.**

Artifacts use collision-safe run/template allocation:

- `outputs/runs/manual_configuration/<run-id>/`: manifest, sanitized fsynced
  `events.jsonl`, bounded shared results spool and one UTF-8 `.txt` transcript per
  device, with CRLF line endings for Notepad and timestamped source-row SEND/RECEIVE
  sections. Safe IP fallback filenames are allocated before identification, preserving evidence even for login/setup failures. Setup/enable secrets are excluded.
- `outputs/backups/configuration/<run-id>/`: existing protected configuration
  backups; treat these as sensitive and never publish them.
- `outputs/reports/manual_configuration/`: exclusively created XLSX reports with
  every input row in workbook order; cells are literal strings to prevent formula
  injection. The source workbook is unchanged.
- `outputs/logs/manual_configuration/YYYY-MM-DD/`: concise sanitized stage logs.

A recording failure stops further device writes. Retain the run if report writing
fails. Offline recovery ignores an incomplete final journal line, reports missing
row results as Incomplete, and treats a save intent without a durable confirmed
result as Unknown. A missing input snapshot cannot be recovered. Disk failures may
prevent even failure records; recovery never infers success from a returned worker
or an interrupted run. No CLI transcript establishes independent configuration
verification.

## Automated and owner-operated validation

Linux Bash deterministic checks:

```bash
PYTHONPATH=src python -m pytest tests/test_manual_configuration.py tests/test_operations_console.py tests/test_configuration_execution.py tests/test_shared_cli.py tests/test_cisco_ios_cli.py tests/test_cli_lifecycle.py tests/test_cisco_terminal_width.py tests/test_edgeswitch_angle_prompt.py tests/test_prompt_banners.py tests/test_configuration_execution_evc.py tests/test_configuration_execution_stages.py -q
PYTHONPATH=src python -m pytest -q
```

Windows PowerShell deterministic checks:

```powershell
$env:PYTHONPATH = "$PWD\src"
python -m pytest tests/test_manual_configuration.py tests/test_operations_console.py tests/test_configuration_execution.py tests/test_shared_cli.py tests/test_cisco_ios_cli.py tests/test_cli_lifecycle.py tests/test_cisco_terminal_width.py tests/test_edgeswitch_angle_prompt.py tests/test_prompt_banners.py tests/test_configuration_execution_evc.py tests/test_configuration_execution_stages.py -q
python -m pytest -q
```

Owner-operated fresh isolated lab validation remains pending. Use disposable lab
changes with recovery access; never replay previously completed/Unknown changes:

1. Decline confirmation, then use a wrong password on another attempt. Confirm
   zero device connections in operator-controlled connection monitoring.
2. Use two successful noncontiguous rows for one lab IP and one independent IP.
   Confirm fresh shell channels, workbook order, pre-row backups and one confirmed
   save per successful row; inspect the continuous transcripts and report. Include
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
