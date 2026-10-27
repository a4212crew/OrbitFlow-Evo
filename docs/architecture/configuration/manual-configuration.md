# Manual Configuration — Issue #156

Owner-approved design implemented on this branch. Deterministic synthetic tests cover safety and compatibility; owner-supplied run evidence is recorded below. Fresh EdgeSwitch and broader owner validation remain pending. See the [operator guide](../../user_manual/manual-configuration.md) and [API](../../operations/manual-configuration-api.md).

This separate Excel-driven workflow supersedes legacy offline Manual CLI only for
new input generation. Historical v1/v2 plans, immutable digests and workbook/report
reading remain unchanged; legacy Manual CLI plans remain non-executable. Predefined
template identifiers remain stable.

Each management_ip/command row is a literal multiline block in a fresh shell.
Repeated IPs retain workbook order on one device worker; other devices may proceed
independently through shared bounded execution. Every successful row requires durable
sanitized transcript evidence, explicit mode synchronization and confirmed vendor
save. Any failed/unknown row suppresses further automatic save and rows for that device.
Predefined execution retains its separate device-end partial-save policy.

The existing local profile may gain an optional manual_configuration_auth table
containing only a salted work-factor-protected password hash. Legacy profiles remain
valid; manual execution fails closed without valid authorization and explicit summary
confirmation. This local gate is not tamper-proof authentication.

Prompt-aware setup/finalization is permitted. User-command receive capture uses
bounded inactivity, never prompt interpretation. Silence does not prove completion;
delayed output may cross command boundaries. Reports say “Transcript only —
configuration not independently verified”. No automatic replay, retry or rollback.
Not saving does not undo running changes; whole-config save may persist unrelated
changes. Save transmitted before interruption remains Unknown and is never retried.

Manual finalization alone can synchronize `end` against the actual structural
starting prompt after arbitrary supported submode/hostname changes, then learn a
fresh privileged EXEC anchor after receive quiescence. Ordinary/predefined readers
keep their existing exact-echo rules. Anchored vendor diagnostic classification
avoids treating literal command echoes or hostname words as errors; complete
sanitized receive evidence remains authoritative, including fragmented diagnostics.

## Required protected skill corrections for Atlas

In `.agents/skills/configuration-management/SKILL.md`, qualify “For Manual CLI
only” as “For legacy offline Manual CLI plans only”; append: “Issue #156 approves
a separate Manual Configuration workflow, not execution of legacy Manual CLI plans.
New planning inputs omit Manual CLI without renumbering predefined templates.
Manual Configuration saves only after each successful durably recorded row and
stops later rows on the same device after any failure/unknown outcome. Predefined
execution retains device-end partial save. See docs/architecture/configuration/manual-configuration.md;
implementation/live validation must be established from source and evidence.”

In `.agents/skills/interactive-operations-console/SKILL.md`, append to Configuration
Management coverage: “Owner-approved Issue #156 design adds Manual Configuration:
Generate Manual Input Template; Execute Manual Configuration; Regenerate Manual
Report (offline); Back.” Replace the non-secret profile prohibition with: “Never
store plaintext passwords or other credentials. The optional manual_configuration_auth
section stores only a salted work-factor-protected admin password hash; old profiles
remain compatible. Manual apply requires hidden password verification and separate
summary confirmation before networking.” These are design corrections, not claims
of implemented or live-validated functionality. Protected .agents files are not edited.

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

Protected-skill handoff for this revision (Atlas): append to the Issue #156
configuration-management and interactive-operations-console skill notes:
“Manual input ignores blank separator lines and retains original cell-line identity.
The shared numbered chooser filters manual_*.xlsx including explicit selections.
Each completed device task atomically refreshes ONE consolidated manual_output
timestamp workbook, containing all rows and device summaries, with relative links
to named receive-only captures. New manual run/report/backup folders use short UTC
YYYYMMDD_HHMMSS names and numeric collision suffixes. Remove pre-password explanation
lines while retaining hidden password verification and explicit confirmation.
Run journals retain row/timing/send evidence; legacy captures recover at their real
paths. No application labels or synthetic echoes belong in captures. Owner live
validation remains pending.” Existing protected skills were not modified.

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

Protected-skill handoff for Atlas (exact append to configuration-management and
interactive-operations-console SKILL.md; existing protected files remain unchanged):
“Owner correction 2026-10-26: Issue #156 Manual Configuration accepts literal CLI
without semantic allowlists/denylists, abbreviations or credential-keyword bans.
This exception is manual-sender-only. Preserve structural bounds and redact secrets
independently before all persistence. Explicit user save/commit may persist changes
before failure; automatic save remains successful-row-only. Preserve fresh-shell
setup, prompt-free capture, unsupported-question failure, and predefined policies.
See docs/architecture/configuration/manual-configuration.md for evidence and status.”


## Atlas skill handoff completed

Atlas applied the configuration-management and interactive-operations-console skill
corrections on this PR before owner-authorized merge. Earlier protected-file handoff
notes above describe the implementation history; the current skill sections now
record the final literal-command, authorization, output and automatic-save contract.
No executable changes were made by Atlas. Validation evidence/limitations above
remain unchanged.

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
