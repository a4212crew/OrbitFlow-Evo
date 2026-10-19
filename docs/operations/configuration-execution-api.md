# Configuration execution and standalone observation API

Canonical CLI and operational semantics: [execution manual](../user_manual/configuration-execution.md).
These synchronous Python APIs do not require an HTTP server. XLSX is an optional
adapter; applications can submit normalized per-row decisions directly.

```python
from orbitflow.configuration.v2.planning import load
from orbitflow.configuration.execution import ExecutionService, ApplySettings, export_results

original = load('plan.json')
service = ExecutionService()  # authority_dir='data/configuration/execution'
prepared = service.prepare(original, {'SOURCE_ROW_ID': 'Approve'},
                           expected_digest=original.digest,
                           settings=ApplySettings(max_concurrent_devices=1))
# Alternative: service.prepare_workbook(original, 'plan.xlsx', expected_digest=original.digest)
from orbitflow.configuration.execution import operator_summary, render_summary
projection = operator_summary(prepared)
print(render_summary(projection))
# Await separate confirmation; retain the complete prepared object/digest.
```

`prepare(original: BulkPlan, decisions: dict, *, expected_digest: str,
settings=ApplySettings()) -> dict` validates immutable content and decision/dependency
intent without connecting. Decisions are row-ID mappings; values Pending/Approve/Reject;
existing plan values fill omitted decisions. `prepare_workbook(original, workbook,
*, expected_digest, settings=ApplySettings())` validates protected XLSX cells and
passes decisions to the same boundary. Both return `status`, `reference`,
`summary_digest`, `summary`, `run_path` (empty until allocation). New summaries have `awaiting_confirmation`; repeated
summaries expose their existing claimed/completed/interrupted status and reference.
Summary selected entries contain request/result/identity/verification_commands;
skipped entries retain row ID, decision and reason. Settings bind concurrency,
timeouts and connection pacing/retry. Save behavior is disclosed in the summary.

`ApplySettings(max_concurrent_devices=1, command_timeout=30.0, save_timeout=300.0,
connection_start_interval=1.0, connection_retry_delay=5.0)` is frozen. Concurrency is
a positive integer; timeouts are finite positive seconds; pacing/retry are finite
nonnegative seconds. No read-only concurrency is implicitly inherited.

After obtaining explicit confirmation of that exact summary:

```python
# credentials: existing in-memory IP -> DeviceCredentials mapping.
# transport_config: existing TransportConfig; never put secrets in preparation.
spool = service.confirm(prepared['reference'],
                        summary_digest=prepared['summary_digest'], apply=True,
                        credentials=credentials, transport_config=transport_config)
export_results(spool.path, spool.path / 'api-execution-results.xlsx')
```

`confirm(reference, *, summary_digest, apply=False, credentials=None,
transport_config=None, inventory_path='data/inventory/inventory.json',
run_root='outputs/runs/configuration_execution',
backups_dir=None, progress=None) -> ResultSpool` consumes the reference
transactionally before connection. `apply is True` is mandatory. No actor label is
authentication. Digest mismatch, missing reference, corruption and replay raise
`PlanError` before device access. A run interruption consumes confirmation permanently
and preserves its `run_path` in the local database when allocation succeeded.
Per-device/row failures are durable outcomes, not exceptions that pause safe peers.
Infrastructure/persistence failures can raise; do not retry confirm blindly.
`ResultSpool.records()` streams sanitized final device outcomes, while the incremental
journal preserves actions from unfinished devices. `export_results(run_path, output)`
is offline, refuses an existing output and returns its Path. See the manual for sheets,
interruption semantics, logs, permissions and limitations.

## Switchport collectors and pure parsers

```python
from orbitflow.capabilities.switchport import SwitchportService
from orbitflow.vendors.cisco.switchport import parse_switchport_output as parse_cisco
from orbitflow.vendors.ubiquiti.switchport import parse_switchport_output as parse_edge

facts = parse_cisco('Switchport: Enabled\nAdministrative Mode: static access\n'
                   'Access Mode VLAN: 1033 (Customer)')
assert facts.facts['access_vlan'] == 1033
edge = parse_edge('General Mode PVID: 1\nGeneral Mode Untagged VLANs: 1\n'
                  'General Mode Tagged VLANs: \nProtected Port: True in Group 0:')
assert edge.facts['protection']['group'] == 0

# session/context/cli already established by shared transport and inventory:
observed = SwitchportService(timeout=10.0).collect(
    session, context, 'GigabitEthernet1/0/1', cli=cli)
payload = observed.to_dict()
```

`SwitchportService(*, timeout=10.0).collect(session, context, interface, *, cli, correlation=None)`
borrows the same live DeviceSession/DeviceCLI; it never reconnects or closes them.
Supported family/platform/profile pairs: C3750X/cisco_ios/c3750x_switching,
C3850/cisco_xe/c3850_switching, EdgeSwitch/ubiquiti_edgeswitch/edgeswitch (empty legacy
profile also accepted). It performs required shared paging/Cisco width setup,
then `show interfaces <interface> switchport` (Cisco) or
`show interfaces switchport <interface>` (EdgeSwitch). Invalid/unsupported targets,
rejected/unrecognized output and failed exchanges raise fixed `SwitchportCapabilityError`;
shared CLI exchange failures invalidate synchronization. Results are serializable
`SwitchportObservation(fields: dict, facts: dict, evidence: str)` with `.to_dict()`.

Pure `parse_switchport_output(text: str) -> SwitchportObservation` functions use no
session, XLSX, transport, logging handlers or execution state. Duplicate labels raise
ValueError; malformed/missing typed values are None. Recognized blank lists are `[]`,
ALL/NONE retain symbolic strings, explicit lists expand ranges inclusively and retain
VLAN 1. Wrapped lists and all original labels/values are preserved. Cisco facts:
enabled, administrative_mode, operational_mode, access_vlan, native_vlan, allowed_vlans.
EdgeSwitch facts: pvid, untagged_vlans, tagged_vlans, forbidden_vlans, optional name,
protection {enabled, group, raw}. Missing Name is None, group zero remains valid,
tagged/forbidden overlap remains independent without warnings/lookups. Pure parser
evidence is input text; the collector applies shared evidence sanitization.

Shared `VlanService.lookup(session, context, vlan_id, *, cli=...)` now retains
sanitized Cisco lookup evidence and complete names. EdgeSwitch results retain legacy
operational_status for planning compatibility and add accurate `vlan_type`, matched
`vlan_id`, `ports_complete`; ports retain interface/current/configured/tagging.
ID/name presence and port-table completeness are independent. Existing artifacts
without the optional additions remain valid. Failed/unavailable lookup is never absence.

## Standalone verification and save

`verify_row(session, context, cli, entry, before, *, timeout=30.0, correlation=None) -> dict` in
`orbitflow.configuration.execution` performs only read-only verification; it sends
no configuration or save commands. `entry` is a selected prepare-summary entry;
`before` is a normalized `configuration.v2.observation.snapshot(context, interfaces,
vlans)` from shared InterfaceService/VlanService on the same session immediately
before the row. Callers performing independent verification must supply that baseline
to prove preservation. Return status Verified/Failed/Unknown plus structured evidence,
warnings where relevant. Collector/transport failures can raise; the executor records
their fixed categories and Unknown/Not executed outcomes. It checks full trunk sets,
native/description/admin preservation and EdgeSwitch configured membership/tagging,
without conflating Current or operational Down. Scoped configuration evidence reuses
existing capability facts. Execution composes this verifier rather than owning it.

```python
from orbitflow.capabilities.save import save_configuration
result = save_configuration(session, context, cli=cli,
                            exec_prompt=original_exec_prompt, timeout=300.0)
```

Save is a separate **configuration-persistence action**; callers need explicit operator
intent. `save_configuration(session, context, *, cli, exec_prompt, timeout, correlation=None)` requires
an already synchronized session-validated privileged EXEC prompt and an approved family/profile.
It returns status Saved/Unknown, sanitized response, answered (EdgeSwitch question),
error_category and explicit_error separately. It borrows resources; no retry, reconnect
or success-marker requirement. Bad preconditions raise ValueError/InteractiveCLIError;
incomplete exchanges return Unknown and invalidate the shared shell. The caller retains
the exact session EXEC anchor, never a guessed hostname. After an echo-associated
approved sequence or checked bounded recovery reaches structural EXEC, the executor
may refresh its presentation anchor on the same owned shell. Completed fresh
observations may also refresh it only at structural privileged EXEC. Save itself never
relearns that anchor from its response. Shared `DeviceCLI.execution_mode`
and `DeviceCLI.save_configuration` implement synchronization internally; prefer the
capability wrapper for supported application use.

`ResultJournal(path, *, clean=sanitize_text)` in `orbitflow.result_spool` owns
synchronized fsynced JSONL append; `append(json_value)` sanitizes recursively and
`records()` streams complete lines for recovery. It does not retry failed writes or
retain full runs. Callers must never submit sensitive raw backup content. The executor
uses it for incremental progress alongside the existing central ResultSpool.

Validation commands and pending owner lab checks for Linux/Windows are in the
[canonical manual](../user_manual/configuration-execution.md#validation-and-remaining-limits).

Optional `correlation` mappings on `collect`, `save_configuration` and `verify_row`
(default None) select scalar `run_id`, `row_id`, `digest` metadata only. Example:
`correlation={'run_id': 'lab-117', 'row_id': 'port-3'}`. Resource IP, normalized
interface, collection command, stage, outcome and elapsed seconds are capability-owned.
Save is device-wide; execution supplies run/digest and verification row IDs. Shared
logs retain selected fields and safe exception types/frame locations without raw
responses or arbitrary exception messages.

Collectors require one Cisco `Name` / EdgeSwitch `Port` matching the normalized
requested interface. Missing, duplicate or mismatched headers raise
SwitchportCapabilityError without reconnecting or invalidating a synchronized shell.
Pure parsers still accept incomplete observations. EdgeSwitch VLAN lookup recognizes
Port and Interface headers and rejects malformed/truncated rows as incomplete.
Supplied command-not-found, incomplete-command and VLAN-range diagnostics reject
writes. Save still records Saved on original EXEC return, with explicit_error separate.

## Owner revision: reusable operator projection and retained report

`operator_summary(prepared: dict) -> dict` is a pure XLSX/HTTP-independent projection:
reference, source_digest, summary_digest, device_count, changes, no_ops, skipped,
concurrency, ordered devices (ip/hostname/family/action counts), source-row reasons,
save_behavior and fresh_checks. `render_summary(projection) -> str` gives compact totals, numbered IP/hostname/selected
row counts in first-appearance order, a brief warnings/blockers pointer and one
backup/execute/save policy line. It does not expand action categories, commands or
finding source lists; these remain available in the structured projection/preparation.
Neither changes the full `prepared['summary']` nor its confirmation digest/replay guard.
Prepare/confirm remain the authoritative complete programmatic contract.

`confirm(backups_dir=None)` defaults to `spool.path/backups/`; an explicit path still
allocates `PATH/RUN_ID/`. BackupWriter's optional `exact_directory=False` allocation
option is used internally for this run-owned directory; standalone backup keeps its
existing dated allocation. Metadata stores run-relative backup_reference and logs the
usable backup_path. Moving an intact default run preserves references; external overrides
require retaining the external tree in its relative position. Captures never enter Excel.

`verify_row` keeps parser facts intact. Access-only fallback requires missing (not malformed) operational
access_vlan, enabled/static-access, reliable fresh normalized exact-target config and
exactly one explicit singleton access fact. Evidence adds missing_fields,
access_vlan_source, access_vlan_check(actual/requested) and warnings; contradictory
operational values fail. No implicit VLAN 1 or intent-derived fact is allowed.

`export_results` now creates Run Summary, original template-named row sheets and readable
Evidence Details, as documented in the manual. Pre-config comes only from durable
pre_row_evidence or retained pre_config, otherwise Not captured. Config Sent uses
command_intent/result/unknown events, including pending sends and partial responses.
Apply/verification/save remain separate. Old runs preserve readable available fields;
legacy skipped entries without request identity cannot reconstruct original inputs.
The exporter streams journal diagnostics and keeps positions rather than whole-run
response bodies; it rereads the journal per row. Existing output paths are refused.


Pre-revision confirmations are matched using their original metadata shape as well as
the current summary digest. Adding skipped-row presentation identity cannot create a
second executable reference for already claimed/completed/interrupted work. Existing
records return their original fully bound summary/digest; older missing skipped identity
is not invented. The confirmation store must still be retained and protected.

Backup references use forward slashes. Explicit Windows external overrides on another drive
retain an absolute reference because no run-relative path exists; default run-local
captures always retain relative references.

If switchport collection fails after normalized post-row capture, verify_row returns
Unknown with that scoped configuration retained and a safe category/warning. Status
Verification in Excel shows requested/projected state alongside actual checks; apply
status remains based on attempted command outcomes. Planning warnings and verification
warnings appear under Warning rather than being mislabeled as execution errors.

## Structured progress subscription

`ExecutionService.confirm(..., progress=None)` accepts an optional synchronous
`Callable[[dict], None]`. It is called only after successful explicit confirmation;
preparation, declined CLI input and replay rejection emit no execution progress.
Default None installs no timer and produces no console output. XLSX is independent.
For future API callers, consume the same scalar event dictionaries directly:

```python
# Only after the caller explicitly confirms the exact prepared summary:
def on_progress(event):
    # Copy/enqueue promptly; do not perform device operations in a subscriber.
    print(event['management_ip'], event['stage'], event['elapsed_seconds'])

# Supply progress=on_progress to the confirm call shown above.
```

Each event contains `management_ip`, `hostname`, `stage`, `elapsed_seconds`,
`rows_completed`, `devices_completed`. Run allocation adds `run_id` and `digest`.
`confirmed_start` includes `rows_total` and `devices_total`. Command events optionally
include `source` (template sheet and source row), `command`, `command_index`,
`command_total`, `status`, `error_category`. These are sanitized scalar presentation
fields; raw responses, credentials and nested evidence are never progress payloads.

Stages: confirmed_start, connect, identify, preflight, backup, backup_complete,
row_preflight, pre_row_evidence, command_intent, command_result/command_unknown,
mode_intent/mode_result, verification_intent, verification_warning, row_result,
save_intent, save_confirmation_recognized, save_answer_y_waiting_original_exec,
save_result, device_failure, cleanup_start/cleanup, device_complete and recording. The CLI also
uses report_generation/report_complete with IP `-` for offline reporting.
`row_result.status` is the verification outcome; command_result Returned is only exchange
progress. Totals count completed row/device outcomes, including failures, not success.

A single optional timer emits `waiting` every 5 seconds for active blocking stages,
with `awaited_stage`, `waiting_seconds`. Individual command/save waits include
`timeout_seconds` and nonnegative `remaining_seconds`; compound observation stages
instead include `command_timeout_seconds`. No deadline is invented for connection or
identification. The clock is elapsed wall time, not device liveness. Delivery is
serialized across device workers and timer; subscribers must return promptly.
Subscriber exceptions disable that subscriber without affecting device writes or
mandatory journal recording. Cancellation/error joins the timer in finally; it never
owns a device session, sends data or retries writes. No progress is retained after
reporter closure. The owner worker alone emits recognized save-question/y stages.
Progress is best-effort display; the fsynced ResultJournal remains authoritative.

The shared renderer is `orbitflow.progress.console_progress(event)`; it prints one
flushed line. `Progress(subscriber=None, *, interval=5.0, clock=monotonic)` is the
context-managed dispatcher used by execution and offline CLI reporting. Its `emit`
and deterministic `tick` are presentation mechanisms; they do not authorize actions.
See the [manual](../user_manual/configuration-execution.md#iteration-3-presentation-and-live-progress-issue-117)
for compact workbook fields, linked detail, canonical run identity and Linux/PowerShell
report/test commands. See the Issue #119 status below for reported owner lab validation
and remaining live checks.

Waiting snapshots use current batch completion counters, including outcomes from
other devices completed since the awaited stage began.


## Issue #119 console presentation

`console_progress(event)` renders IP, hostname and stage, optional source sheet/row,
command index/total, statuses and error categories; verification warnings point to
retained details. It omits raw commands, counters, correlation and all timing fields.
`Progress` delivery, scalar event keys, waiting heartbeat and independent subscribers
are unchanged: API consumers retain elapsed/wait/deadline diagnostics. Delivery remains
serialized and flushed. No execution collection, verification or transport changes.

The CLI prints one final recorded device/row outcome summary and execution elapsed
seconds before exporting the report. Partial, failed, unknown and interrupted outcomes
are distinguished; report-only operation adds no execution elapsed footer. This console
format is independent of `confirm`'s unchanged ResultSpool return contract.
Owner C3750X/EdgeSwitch lab validation of PR #118 was reported; C3850 live validation
remains outstanding. See the manual's [validation instructions](../user_manual/configuration-execution.md#issue-119-validation-status).

## Console adapter

Issue #123 adds `python -m orbitflow.menu` over the existing prepare/confirm/export APIs, without changing their signatures or execution gates. See the [console manual](../user_manual/interactive-operations-console.md). The console binds a separate 1-5 apply concurrency selection and original expected digest, renders the existing summary, and requires explicit confirmation before session validation and `confirm(..., apply=True)`. Offline recovery only calls exporters.

Console adapter note (Issue #123): the interactive caller validates the chosen immutable plan JSON, derives/displays `original.digest`, and passes it as `expected_digest` to `prepare_workbook`. This does not alter this API, workbook verification, confirmation authority or apply behavior. Direct CLI digest arguments are unchanged.


Console presentation (Issue #123 / PR #124): `python -m orbitflow.menu` wraps offline `prepare_workbook` with elapsed preparation notices and still requires its separate explicit confirmation before `confirm`. It subscribes to existing structured execution progress and displays measured durable device/elapsed counts; report export has a separate completion indicator. The console filters only its own rendering of the two long summary prose lines and retains a short caution. `render_summary`, direct execution CLI output, public service signatures, confirmation/digest binding and all apply safeguards are unchanged. See the [console guide](../user_manual/interactive-operations-console.md#progress-and-evidence-presentation-pr-124-ux-revision).

The final Issue #123 console revision renders allowlisted existing structured stages, source sheet/row and outcome statuses, plus periodic waiting snapshots after confirmation. Hostnames and arbitrary payloads are suppressed. No public callback schema, executor behavior or direct CLI rendering changes. See the [console stage guide](../user_manual/interactive-operations-console.md#confirmed-execution-stage-visibility-final-owner-revision).


## Execution timing and observation reuse (Issue #125)

`confirm`, `verify_row`, all standalone collectors, parsers, save and structured
progress signatures remain unchanged. Confirmed supported-family execution enables
internal session paging reuse and a bounded per-session deterministic snapshot
projection manager. Confirmed execution shares fresh observations within ordered
independent-target stages; standalone `verify_row` still collects its own fresh facts. Shared standalone collector defaults remain unchanged.

Detailed timing records in the existing bounded configuration/execution logger use
run/digest/IP/row/template correlation, fixed stage/command category/index, outcome,
monotonic `elapsed_seconds`, measured receive `device_wait_seconds` and residual
wall `work_seconds`. Shared log serialization represents scalar timing fields as
strings; parse seconds as finite nonnegative numbers. No raw commands/output are
included. Parent/child timings overlap; receive time is not CPU time or liveness.
Run Completed means scheduling/recording completed and does not replace row/save
outcomes. Interrupted run totals are Unknown; journal/recovery remains authoritative.
Transport admission/retry stages retain existing retry/pacing semantics.

Internal `orbitflow.timing` / `execution_observation` helpers are not new supported
public execution APIs. The offline developer script
`scripts/configuration_execution_timings.py LOG [LOG ...] [--run-id ID]
[--group-by run_id device_family management_ip template_id row_id stage_id]` exposes
bounded stage distributions with sanitized correlation, not an apply/resume interface.
Default grouping is run/family/IP. Family comes from approved bound identity;
fresh identity failures remain failures. Legacy missing fields are unknown, never
inferred across devices. Custom run/row IDs are hashed; templates/families are
allowlisted. Duplicate paths/exact timestamped records are ignored; missing files,
omitted rotations and unprovable retention completeness warn on stderr.
Only `cli_command/configuration_read` counts physical configuration exchanges;
nested collector/observation spans must never be summed. Ordered template stages
reduce repeated full reads; stage final-state verification does not establish
continuous whole-device or unobserved intermediate drift detection. See the
[profiling guide](../user_manual/configuration-execution.md#execution-profiling-and-safe-reuse-issue-125)
for arguments, limits, Windows/Linux tests/extraction, synthetic benchmark methodology
and the owner-controlled lab comparison. Console execution uses the same service;
there is no additional confirmation or menu workflow.


### Ordered stage results and timing

`confirm` uses the same selected device row order and shared worker/session ownership.
There is no new caller setting or confirmation. Internal stage formation splits at
changed templates, source/resolved target overlap and row dependencies. Relevant
fresh facts are compared against a bounded device baseline that advances verified
changes only. Failed prechecks block affected writes. Usable independent targets may
continue after rejection; uncertain session outcomes remain Unknown. Stage final
state is attributed to each independent target; overlap is observed in separate stages.

Durable row dictionaries add `stage_id` and `elapsed_seconds`; verification adds
`stage_id` and `observation_scope='stage final state; independent target'`. Existing
status/evidence keys and report sheets/columns remain. Journal stages add
`stage_precheck` (row_ids, template_id, normalized observation),
`stage_post_observation` (full normalized observation for interface stages; fresh
vlan_lookups for database stages), and `stage_result` (row IDs/statuses), all with
stage_id. Existing per-row pre_config evidence is fresh at the stage boundary and
fsynced before sends. Post-stage row results/stage result are persisted before the
next stage. Recovery never invents missing verification or repeats commands.

Timing records add sanitized `stage_id`; extractor `--group-by` accepts it alongside
existing dimensions. New spans are `template_stage`, `stage_pre_observation`,
`stage_post_observation` and `row_apply`. Initial baseline supplies the first precheck;
VLAN Database postchecks produce `vlan_lookup` spans without a full-observation span.
`row_total` spans precheck to recorded outcome, including shared stage/sibling waits;
it is wall time, not allocated physical device work. Stage/row/device totals overlap.
The independent public `verify_row(..., timeout=30.0, correlation=None)` signature
and its fresh read-only behavior remain unchanged. Shared capability correlation may
include optional scalar `stage_id`; standalone callers need not supply it.


### Execution prompt framing (Issue #134)

`DeviceCLI.execution_mode(exec_prompt, platform)` selects execution-only vendor
structural recognition after identification. Cisco hostname presentation and arbitrary
parenthesized submodes may change; EdgeSwitch accepts separate outer and inline mode
presentations and annotations. No expected-mode-name transition gate is applied.
Current exact echo and a complete unterminated structural prompt cause immediate
completion with zero new per-command delay. Read-only adapter configuration restores baseline framing;
public defaults, command authorization, rejection detection and verification do not
change. A prompt return alone cannot establish a successful configuration write.
`save_configuration` retains exact EXEC-anchor return and separate explicit-error
reporting; standalone callers must provide the synchronized current EXEC anchor.
See [contract and Linux/Windows validation](../user_manual/configuration-execution.md#flexible-execution-prompts-issue-134).

Owner's superseding no-added-wait clarification (Issue #134 / PR #135): execution
returns immediately once the current exact echo and complete unterminated vendor
structural prompt are detected. No fixed/adaptive silence wait, sleep, retry or
timeout extension is added. Earlier quiet-guard proposals are superseded; their
review history remains in the October devlog. Split incomplete prompts still require
more input; invalid prompts, missing echoes and ambiguous failed exchanges retain
session invalidation. A prompt-shaped prefix followed by later bytes cannot be
predicted under this timing contract. Independent rejection checks, verification
and exact EXEC-anchor save completion remain required. Owner Linux/C3850/EdgeSwitch
live validation remains pending.
