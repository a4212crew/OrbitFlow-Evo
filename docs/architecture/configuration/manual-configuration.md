# Manual Configuration — Issue #156

Owner-approved design implemented on this branch. Deterministic synthetic tests cover safety and compatibility; owner-operated Windows/Linux live validation remains pending. See the [operator guide](../../user_manual/manual-configuration.md) and [API](../../operations/manual-configuration-api.md).

This separate Excel-driven workflow supersedes legacy offline Manual CLI only for
new input generation. Historical v1/v2 plans, immutable digests and workbook/report
reading remain unchanged; legacy Manual CLI plans remain non-executable. Predefined
template identifiers remain stable.

Each management_ip/command row is a literal multiline block in a fresh shell.
Repeated IPs retain workbook order on one device worker; other devices may proceed
independently through shared bounded execution. Every successful row requires durable
sanitized transcript evidence, explicit mode synchronization and confirmed vendor
save. Any failed/unknown row suppresses further save and rows for that device.
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
newest first, with explicit-path fallback. Each device publishes its own short
manual_output_YYYYMMDD_HHMMSS.xlsx report as soon as its task ends; collision suffixes
and device directories disambiguate outputs. Its continuously flushed receive-only
UTF-8 capture lives alongside the report under outputs/reports/manual_configuration/.
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
Each completed device task publishes a short manual_output timestamp report and a
relative link to its receive-only capture under outputs/reports/manual_configuration/.
Run journals retain row/timing/send evidence; legacy captures recover at their real
paths. No application labels or synthetic echoes belong in captures. Owner live
validation remains pending.” Existing protected skills were not modified.
