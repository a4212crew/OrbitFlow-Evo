# Approved device configuration execution — Catalyst and EdgeSwitch

Status: **Owner-approved design, 2026-10-17 (Australia/Sydney); initially implemented by Issue #117 and revised by merged Issue #125 / PR #126 (2026-10-18). Owner live validation covers C3750X and EdgeSwitch ordered template-stage execution; C3850 and Linux validation remain pending.**
See the [execution manual](../../user_manual/configuration-execution.md) and
[supported APIs](../../operations/configuration-execution-api.md) for actual names,
defaults, behavior and limitations. Design-time suggestions below retain provenance.
This document records the owner's template-by-template review and later corrections.
It does not authorize a development Issue, production changes, or a PR merge.
Source and tests establish current behavior; supplied device transcripts establish
sample CLI behavior, not live validation of a future executor.

## Scope and authority

Initial scope: C3750X (IOS), C3850 (IOS-XE; workbook label C3850X), and
EdgeSwitch, including owner samples from EdgeSwitch 24 250W firmware 1.9.2.
Support existing predefined VLAN database, Catalyst access/trunk, EdgeSwitch VLAN
port and interface-description templates. Do not infer support for other C3750
variants from the OS identifier. Other families and free-form Manual CLI execution
are deferred. Preserve v1 planning/authority and v2 planning/review behavior.

For this scope, this document supersedes older proposed global batch pauses,
save-only-after-success policies, inferred membership from tagging, and delivery
orders that defer EdgeSwitch until after IOS-XR. It does not approve generic
removal/rollback or transactional behavior for other families.

## Shared prepare and confirm boundary

Accept immutable plan JSON plus its reviewed Excel workbook. Reuse digest,
protected-cell, row-identity, decision and dependency validation. Pending/Reject,
unsupported and blocked rows are not executable. Workbook decisions are review
intent, not authenticated execution authority. Require separate explicit apply
intent from the operator/caller; actor labels are not authentication.

Provide individually callable prepare and confirm operations, independent of Excel
presentation or an HTTP server. Prepare changes no device configuration and returns
structured summary plus a confirmation reference. Summary includes source digest,
device identity/IP/family, selected rows in order, exact approved CLI, verification
commands, skipped rows/reasons, prerequisites/blockers, configured apply concurrency
and save behavior. Disclose whole-running-config persistence, partial-change saving,
and EdgeSwitch's potential management interruption and automatic save answer `y`.

CLI renders a concise reusable projection of this full digest-bound summary (counts,
ordered device/template actions, source warnings/blockers and save scope) and asks `Confirm execution? [y/N]:`. Future web/API callers
receive `awaiting_confirmation`; a subsequent explicit call confirms the exact
selection. Bind the reference to plan digest, row selection, commands and execution
settings; changes require a new summary. Duplicate confirmation must not start a
second run. Do not invent an implemented HTTP endpoint, CLI flag, authentication
scheme or timeout/default. Codex must document actual public signatures and options
when implemented. Fresh identity/state checks still precede apply; never silently
rerender different commands under a previous confirmation.

## Device task and continuation

Group every selected row for an IP into one device task using shared device
execution. One worker owns that IP's DeviceContext, DeviceSession and CLI shell;
execute sheet-left-to-right, row-top-to-bottom sequentially. Different IPs may run
concurrently, using an explicitly configured apply limit, not implicitly inheriting
the read-only limit. No feature-specific pools or per-row workers.

Validate fresh identity, capability, relevant state and privilege; capture protected
pre-change configuration through shared capture/backup facilities before changing
configuration. A mandatory capture/preflight failure blocks that device's writes.
Send exact approved commands individually and retain responses. The owner-approved
2026-10-18 ordered-stage revision below supersedes the original per-row full-read
boundary. Earlier verified target effects form the baseline for later stages; retain
original approved evidence separately. No-op rows still require fresh verification.

Command rejection, failed verification or another device's failure does not trigger
a batch-wide pause. Continue executable work while session state is known. Never
send later configuration in an unexpected mode without a deterministic known-mode
transition. **The 2026-10-19 decision below supersedes mode-name expectations;
structural framing and the approved sequence now govern these exchanges.** A lost/unsynchronized session cannot safely send remaining commands:
record them Not executed and uncertain post-send results Unknown. Do not invent
alternate configuration, blindly replay writes, automatically roll back, or claim
that unknown outcomes were reverted. Other device tasks can continue.

Save once at the end of a usable device task if configuration commands were
attempted, including partial changes when some rows failed. Skip save for wholly
no-op/skipped tasks. Row verification, command errors and save completion are
separate outcomes; saving must not convert failed rows into verified rows.

## Independently reusable capabilities

Collectors borrow existing session/context/CLI resources; they do not reconnect or
own worker pools. Pure parsers accept text without a device connection. Results
are structured and serializable for CLI, Excel and future API callers. Execution
composes these functions; it is not their only usable entry point.

Reuse current VlanService lookup, InterfaceService description collection,
configuration capture, interface normalization and numeric VLAN range parsing.
The Cisco and EdgeSwitch switchport collectors/parsers are new development.
Proposed public shape (names/paths are design suggestions, not existing APIs):

```python
result = SwitchportService().collect(
    session=session, context=context, interface=interface, cli=cli)
observation = parse_switchport_output(output_text)
```

Proposed placement: `src/orbitflow/capabilities/switchport.py` for collection;
`src/orbitflow/vendors/cisco/switchport.py` and
`src/orbitflow/vendors/ubiquiti/switchport.py` for vendor grammar/commands;
`src/orbitflow/vendors/switchport_types.py` for typed results. Reuse established
repository model conventions if source inspection supports a better placement.
Document the final supported public interfaces, inputs, errors, standalone examples
and outputs. No Excel or HTTP dependency belongs in parsers/collectors.

Parse labels, not fixed line positions. Split at the first colon, retain all
original labeled values, and expose typed fields. VLAN annotations such as
`1033 (Customer)` yield integer 1033. Expand inclusive ranges; preserve ALL/NONE
explicitly. Recognized blank lists are empty; missing/malformed fields are unknown.
Support wrapped lists without swallowing the next field. Preserve VLAN 1 in these
facts even if an existing report projection suppresses it. Reject partial required
facts for verification; do not treat unrecognized nonempty output as success.

## Catalyst templates

**Historical 2026-10-17 rule, superseded by the 2026-10-19 decision below:**
Use the learned hostname and expected vendor mode, including VLAN-mode variants
`(config-vlan)#` and `(config-vl)#`; do not accept arbitrary text ending in `#`.
Normal configuration/interface prompts are `(config)#` and `(config-if)#`.

### VLAN database — both families

Create/rename CLI from current renderer:

```text
configure terminal
vlan 445
name Customer
end
```

Never delete/recreate to rename. Verify with `show vlan id 445` through shared
lookup: observed VLAN ID and complete name must match. Non-active operational
status is a warning only. Explicit not-found/name mismatch fails; rejected,
malformed or unavailable lookup is Unknown. Preserve complete sanitized evidence,
ID/name/status; ports are supporting evidence, not success conditions.

### Access port — both families

Approved renderer sequence is `configure terminal`, `interface <resolved target>`,
optional `description <text>`, `switchport`, `switchport mode access`,
`switchport access vlan <ID>`, `end`. Preserve admin state; do not add `no shutdown`.
Verify `show interfaces <interface> switchport`: Switchport Enabled,
Administrative Mode `static access`, and integer Access Mode VLAN equal to intent.
Operational `down` does not fail. Check supplied description via InterfaceService
(`show interfaces description`), preserve omitted description/admin settings via
configuration evidence. A missing/inactive global VLAN is a separately reported
warning for Catalyst access configuration; do not implicitly create it.

### Trunk port — both families

Send approved rendered Add/Remove/Replace CLI against the plan's resolved owner.
A physical member resolved to a Port-channel is configured/verified on that owner.
For C3750X new/conversion trunks, retain rendered `switchport trunk encapsulation
dot1q`; C3850 must omit that selector. Preserve admin state and omitted settings.

Verify Switchport Enabled, Administrative Mode `trunk`, complete allowed VLAN set,
requested native VLAN (or preserved baseline), and description. Add = previous set
union request; Remove = previous set minus request; Replace = exact request.
Interpret ALL semantically and ranges inclusively. Compare full resulting sets,
not just requested subset. Operational Down is not failure. Keep bundle membership
in operational evidence. Reuse description/configuration capture.

### Description — both families

Send approved description CLI, verify exact normalized interface/description through
InterfaceService and capture scoped configuration evidence. Physical member targets
stay physical for description; do not redirect to their bundle. Preserve unrelated
settings. Down is not failure; unavailable evidence is Unknown.

### Cisco sample contracts

Owner samples show `Access Mode VLAN: 1033 (Customer)` -> integer 1033;
`Trunking Native Mode VLAN: 1 (default)` -> integer 1; Administrative Mode
`static access` versus `trunk`; Operational Mode `down` or
`trunk (member of bundle Po1)`. Preserve every labeled field, including optional
C3850 `Vepa Enabled: false`. VLAN lists such as
`445,545,1101-1104,2400-2444,2449,4000,4001` expand completely.
`VLAN id 313 not found in current VLAN database` is explicit absence. A pasted
truncated database listing must not establish absence of unshown VLANs.

## EdgeSwitch templates and facts

Observed prompts, with presentation hostname retained for synchronization:

```text
(<LAB-ES24>) #
(<LAB-ES24>) (Vlan)#
(<LAB-ES24>) (Interface 0/3)#
```

**Historical observed presentation, not an exhaustive grammar (superseded below):**
Mode suffixes occur outside the hostname parentheses. Extend vendor-aware prompt
handling without weakening existing inventory/read-only prompt synchronization.
Global configure-mode prompt still needs representative evidence; do not claim all
firmware/mode variants are live-validated.

### VLAN database

From privileged EXEC: `vlan database`, `vlan <ID>` only when creation is needed,
`vlan name <ID> "<name>"`, `exit`. Quoted names may contain spaces.
Owner example `vlan name 1234 "testing max"` succeeded; omission of ID and an
out-of-range ID produced explicit errors. Do not broaden approved VLAN ranges from
a transcript alone; actual profile/schema validation remains authoritative.

Verify `show vlan <ID>`: VLAN ID/name match. VLAN Type `Static` is a type, not an
active/inactive status. Existing lookup currently returns this under
`operational_status`; expose accurate type semantics without breaking existing
planning consumers. Preserve all recognized port rows as independent `interface`,
`current`, `configured`, `tagging` fields. Detect incomplete table parsing rather
than silently relying on a partial list; ID/name verification and port-table
completeness must be distinguishable.

### VLAN port

Execute the exact approved current renderer CLI. Add/Change may include
`vlan participation include <list>`, `vlan tagging <list>`, inclusion of the PVID,
then `vlan pvid <ID>`. Remove uses `no vlan tagging <list>` and
`vlan participation exclude <list>` as rendered. Optional description is quoted;
end interface and global modes with the approved exits.

Existing VLAN database entries are execution prerequisites for requested PVID,
Include and tagging writes. Earlier approved database rows on the same IP can
satisfy them after successful application/verification. Missing prerequisites block
the port row, not safe unrelated rows; unknown prerequisite state is not absence
or success. Never implicitly create VLANs. Planning may still report missing VLANs
as warnings: this execution gate does not silently change planning behavior.

Recognize `Couldn't configure pvid.`, `Failed to set VLAN participation.` and
`Failed to set VLAN tagging.` as command errors even if the mode prompt returns.
Retain sanitized full responses, including multiline output, caret errors and
unexpected responses. Do not automatically run commands suggested by error text.

Collect `show interfaces switchport <interface>` (EdgeSwitch argument order).
For General mode, verify General Mode PVID and General untagged/tagged facts;
Access Mode VLAN and Trunking Mode VLANs Enabled do not override those facts.
Use `show vlan <ID>` on affected existing VLANs for configured inclusion/tagging:
Add tagged -> Configured Include and Tagged; Remove -> Configured Exclude and
requested tag removal. Preserve Current independently; Current/Configured
differences alone do not fail configured-intent verification. Compare PVID with
intent and verify supplied description via existing description collection.

Preserve tagged and forbidden lists independently exactly as observed. Overlap
alone triggers no automatic warning, subtraction or additional lookup; it does
not itself establish successful participation. Perform normal requested-change
verification independently of this reporting rule.

Owner sample parser fixtures:

| Port | General PVID | Untagged | Tagged | Additional fields |
|---|---:|---|---|---|
| 0/1 | 1 | 1 | empty | Protected Port False; Name not reported |
| 0/3 | 901 | 901 | 745,2449,4000-4001 | Name UNMS; Protected Port True in Group 0: |
| 3/1 | 1 | 1 | 445,545,745-746,2436-2444,2446,2449,4000-4001 | Tagged/forbidden overlap retained |

Use a consistent structured protection value: enabled boolean, optional integer
group (0 is valid), and raw value. Missing Name means not reported, not an empty
configured description. Preserve optional fields and whitespace inside values.

### Description

Execute `configure`, `interface <target>`, `description "<text>"`, `exit`, `exit`
as approved. Reuse InterfaceService/`show interfaces status all` and scoped config
evidence; optional switchport Name is supporting evidence only. Preserve PVID,
membership/tagging, protection and admin state. Down is not verification failure.

## Shared save capability

Independently callable save borrows the existing device session and learned EXEC
prompt. Send full `write memory`; abbreviated EdgeSwitch `write` was rejected.
Cisco returns after `Building configuration...` / `[OK]` in supplied samples.
EdgeSwitch asks `Are you sure you want to save? (y/n)`; send `y` only for that
recognized exchange, then wait using a separate save timeout suitable for the
reported minutes-long operation. Do not invent a numerical default in this design.

**Historical 2026-10-17 criterion, refined by the 2026-10-19 session contract below:**
Return to the original learned privileged EXEC prompt
completes save and is recorded Saved. Success-text markers are not required.
Record explicit error output separately even if the prompt returns; prompt-based
Saved is not independent proof of startup persistence. Timeout/disconnect before
prompt return is Save Unknown, with partial evidence retained and no blind retry.
Unknown questions receive no guessed answer. Match the synchronized response after
the command, not a stale prompt buffered before it.

## Recording, logging and compatibility

Keep immutable plan JSON and reviewed workbook unchanged. Existing
`consume_decisions` rejects added columns/dimension changes. Generate a separate
execution-results workbook retaining source row identity and decisions. Suggested
columns: Run ID, Apply Status, Command Responses, Unexpected Response, Verification
Commands, Verification Evidence, Verification Status, Save Status, timestamps,
Error Category and Log Reference. Separate command-detail records link to row IDs.
Treat response text as literal Excel values, not formulas. Oversized cells reference
complete sanitized durable evidence; never silently truncate.

Persist structured run/row/command results under `outputs/runs/<task>/<run-id>/`
through shared execution/spooling interfaces; preserve incremental command progress
needed for interrupted-run diagnosis rather than only final device outcomes.
Report regeneration must not reconnect or repeat writes. Workers do not concurrently
mutate a shared workbook/spool; keep writes synchronized in owning layers.

Use shared `orbitflow.logging` for every action: prepare/confirm, preflight, backup,
mode transition/command, verification, save, recording and cleanup. Proposed logs:
`outputs/logs/configuration/YYYY-MM-DD/` and
`outputs/logs/switchport/YYYY-MM-DD/switchport.log`. Transport retains its own logs.
Include run ID, digest, device/IP, interface, row/command identity, stage, timing and
outcome/error category. Standalone collectors remain usable without an execution
run/row. Pure parser logging must not require Excel/CLI state or install handlers.
Detailed sanitized evidence belongs in results, not raw secret-bearing log output.
Never persist credentials, arbitrary unsafe exceptions or full sensitive backup
content in logs/Excel/Issues. Protected backups remain separate files inside the
execution run at `backups/<safe-device-filename>.txt` by default (owner revision
2026-10-17); run-relative references survive moving an intact run. An explicit
external backups_dir override remains honored and must be retained separately.

## Implementation delivery obligations

No application code is changed by approval of this document. A later explicitly
authorized Codex Issue must preserve inventory, shared transport/CLI, VLAN reporting,
audit/compliance, backup and v1/v2 planning contracts. Test shared interfaces and
vendor fixtures, approval/confirmation mutation and duplicate handling, command
responses/partial output, verification, save exchanges, concurrency isolation and
recoverable reporting. The owner performs device validation; supplied transcripts
are fixtures, not executor validation. Do not add documentation-enforcement CI.

Codex must append the monthly devlog and update affected README, current-state and
roadmap only when implementation changes their truth, canonical CLI manual under
`docs/user_manual/`, and supported public function/API reference with standalone
usage, prerequisites, inputs/defaults, scenarios, Linux/Windows commands where
applicable, outputs/log paths, failures and limitations. Final names/options must
match source/tests; future web integration does not imply an HTTP server is part
of this milestone. No automatic merge.

## Cumulative owner revision, 2026-10-17

The owner revision supersedes earlier JSON-centric operator presentation: detailed
programmatic preparation remains digest-bound, while CLI uses `operator_summary` /
`render_summary`. Execution Excel is plan-like with template-named sheets and original
inputs/decisions, fresh per-row Pre-config persisted before sends, actual Config Sent,
post-row Config Evidence, independent Apply/Status Verification/Save, meaningful errors
and warnings and readable continuation evidence. Old missing pre-row evidence is Not
captured. Source workbook and immutable plan remain unchanged. Exact implementation,
external backup override compatibility and older-run limits are in the manual/API.

Access-only missing operational VLAN may narrowly use fresh reliable exact-interface
explicit normalized configuration, with matching switchport identity/enabled/static
access. Preserve pure parser unknowns, operational contradictions, description/admin/
unrelated checks and missing/ambiguous Unknown outcomes. Retain fallback source and
missing-field warnings in results/logs. These revisions are fixture-validated; owner
lab checks remain pending and completed configuration must not be replayed to diagnose
reports.

## Issue #117 iteration 3 implementation reconciliation

The original bound summary remains authoritative. Operator projection groups short
finding/skip categories with source sheet/row ranges, excluding nested evidence and
presentation-only overlap warnings. Reports retain full operational detail in linked
continuation areas and put scoped CLI/checks plus per-template inputs in main cells;
manifest run_id survives relocation. Original plans/compliance are unchanged.
Optional scalar progress callbacks serve CLI and future API consumers; CLI flushes
stages and five-second wait snapshots. A presentation timer never accesses sessions,
changes deadlines or retries device writes. Save question/y labels originate in the
owning worker; original EXEC return still defines Saved. See the supported API/manual
for exact callback fields and limitations. No live validation or merge is implied.


## Issue #125 initial implementation reconciliation (superseded stage boundary)

Measured shared-shell paging exchanges were redundant; confirmed supported-family
execution now reuses accepted paging setup per session/profile while retaining every
prompt/session check and the first trusted setup. Standalone defaults are unchanged.
`execution_mode` already performed local validation only and remains unchanged
in this historical optimization revision; its recognition contract is superseded
by the 2026-10-19 decision below.

A per-session manager retains at most one normalized deterministic projection (8 MiB serialized
eligibility/retention limits). It always requires complete fresh full normalized
interface/VLAN/config inputs before a cache comparison; only identical-input pure
snapshot/audit computation is memoized. Operational lookups and row/no-op observations
remain fresh. Writes, mismatch, uncertainty and synchronization failure invalidate
retained work. No vendor scoped-refresh implementation currently proves equivalent
full-set drift/preservation coverage, so full collections remain mandatory. This
preserves the approved execution/backup/journal/save/replay contracts above.

Monotonic stage/command/receive timings use shared bounded configuration logs and
run/digest/device/row/template correlation, with no raw CLI/output. Nested spans
overlap; residual work is wall time, not CPU. The developer-only offline extraction
and synthetic benchmark are documented in the
[execution manual](../../user_manual/configuration-execution.md#execution-profiling-and-safe-reuse-issue-125).
They add no operator workflow, confirmation gate or console menu entry. This change
has deterministic Windows validation only; owner C3750X/C3850/EdgeSwitch optimization
validation and Linux execution remain outstanding.

### Issue #125 owner-evidence revision

Offline extraction now isolates run/approved-family/IP, optionally template/row,
without attributing pooled live measurements to individual devices. Missing legacy
dimensions remain unknown; physical reads are counted only at
`cli_command/configuration_read`, separately from overlapping parent spans.
Retention warnings, bounded parsing and timestamped-record/path deduplication
prevent silently presenting known partial/overlapping inputs as complete.

Full-state freshness still comes from full VlanService configuration collection;
InterfaceService, VLAN lookup and SwitchportService remain independent fresh facts.
Targeted reads alone cannot prove absence of external changes outside their scope.
There is no validated whole-device change marker in the supported adapters.
Consequently every row class retains its current full-read boundary, including
description preservation, trunk full sets/ownership and EdgeSwitch database and
participation dependencies. No stale configuration replaces durable pre-row evidence.
The revision implements diagnostic attribution but **does not satisfy the requested
meaningful full-configuration-read reduction**. Owner lab timings remain separate
from synthetic evidence; no new device writes or live validation were performed.


## Owner-approved ordered-stage revision, 2026-10-18

Implemented on the Issue #125 revision with deterministic fixtures; owner stage lab
validation remains pending. This supersedes earlier mandatory full pre/post-row
collection claims above. It changes observation/verification granularity without
changing workbook order, supported templates, approval/confirmation or concurrency.

One mandatory full fresh baseline/identity/privilege preflight and protected backup
precede writes. Maximal contiguous same-template independent-target stages preserve
left-to-right worksheet / top-to-bottom row order. Dependencies within a proposed
stage, shared source/resolved targets (including canonical aliases), and template
changes force splits. A template that appears again later is a new stage. Existing
EVC overlap planning remains unchanged; no EVC execution is enabled.

The initial baseline supplies the first consolidated precheck; subsequent stages
collect full fresh interface/VLAN/configuration facts. Compare relevant target facts
against the bounded trusted baseline, exact approved CLI/no-op/projected result and
prerequisites. All prechecks and durable per-row evidence precede stage writes.
Per-command response/mode checks remain immediate (mode-name checks superseded
by the 2026-10-19 structural-recognition decision below). Rejection stops the affected row;
uncertain synchronization blocks unsafe continuation. A full post-stage observation
and per-target operational checks establish every independent interface result.
Database stages use fresh operational VLAN lookup postchecks only. Shared final state
never implies observation of individual intermediate effects: overlaps split stages.

Only verified target facts advance the baseline, including descriptions/configuration
and verified database name/presence. Partial/Unknown outcomes retain their status;
dependent work blocks, unrelated work requires sufficient fresh evidence and a
trustworthy shell. Persist pre/post-stage records and attributed per-row JSON before
continuing. Existing save-once-after-attempted-writes, including partial changes,
independent save outcomes, fsync/recovery and no retry/rollback/replay remain.

**Tradeoff:** stages establish final target/configuration preservation, not continuous
whole-device drift detection between reads. Unrelated out-of-scope external changes
are not globally compared/adopted; even target changes made and reverted between
reads may escape detection. No stale-only cache or unvalidated scoped parser is used.
Fresh full collections remain the fallback at interface stage boundaries, so heavily
interleaved/dependent/overlapping worksheets retain substantial cost. Missing,
ambiguous or unreliable required facts fail closed.

The [manual](../../user_manual/configuration-execution.md#ordered-template-stages-owner-approved-revision)
describes exact provenance/timing records, measured synthetic counts/durations,
Windows/Linux tests/extraction and owner-only lab comparison. Synthetic schedules
show ten independent interface rows 22 to 3 full reads, database rows 12 to 2 including
baseline/backup; these are not owner lab performance claims.


## Owner superseding prompt decision — 2026-10-19 (Issue #134)

This decision supersedes the learned-host equality, fixed expected-mode transitions
and exhaustive outer-mode assumptions above, including immediate mode checks in
older stage descriptions. Historical observations and prior approval remain recorded.
Initial identification still establishes identity, privilege and the owned SSH shell.
Subsequent execution framing on that shell accepts changing/abbreviated hostname
presentation without changing inventory identity. Cisco IOS/IOS-XE accepts privileged
EXEC and arbitrary structurally valid parenthesized submode names, including
`(config-if-srv)` and `(config-router-af)`. EdgeSwitch separately accepts outer modes
`(ES24) (Something)#`, `(ES24) (Interface 0/3)#`, inline `(ES24 Something)#`,
angle-wrapped hostnames and balanced parenthesized annotations. Arbitrary banner
lines ending in `#`, malformed wrappers and truncated prompts are not valid framing.

The immutable approved plan controls command order; no execution mode-name allowlist
or initial-host equality gate may reject a completed valid exchange. Each execution
command still requires its exact current command echo, an unterminated structural
final prompt and receive quiescence to protect split chunks. Errors, missing echo,
EOF and timeouts retain Failed/Unknown and session-invalidation semantics. A returned
prompt is exchange completion only; independent state verification determines success.

Original EXEC safety is a **session-level completion contract**: after the completed
approved sequence, or bounded vendor recovery (`end` for Cisco, `exit` for EdgeSwitch),
the synchronized shell must reach structurally privileged EXEC, excluding mode labels.
Recovery errors fail closed. Its observed presentation becomes the exact EXEC anchor
for subsequent observation and save on that same shell. A completed fresh observation
may likewise refresh the anchor only at structural privileged EXEC. No hostname is guessed, no
reconnection or write replay occurs. Nested EdgeSwitch annotations remain presentation
metadata, while inline/outer mode labels cannot establish EXEC. Save starts only at
that anchor and requires its exact return after the `write memory` echo. It never
relearns a different anchor from save output. Recognized EdgeSwitch confirmation,
explicit errors, Saved/Unknown and no-success-marker semantics remain unchanged.

Only predefined C3750X/C3850/EdgeSwitch execution changes. Shared read-only adapters,
identification, planning and all other families retain their contracts and defaults.
Automated synthetic regression evidence is separate from pending owner Linux C3750X,
C3850 and EdgeSwitch live validation of this revision. Earlier owner validations do
not validate this change. See the [operator validation steps](../../user_manual/configuration-execution.md#flexible-execution-prompts-issue-134).

PR #135 throughput review retains the one-second execution quiet guard: shorter
silence would accept delayed banner continuations covered by deterministic tests.
A synthetic 52-row/five-command serialized sequence adds 260 seconds of quiet
waiting (780 receives with two fragments per exchange), excluding device latency,
observation and save. This is a reader budget, not live throughput evidence.
See the [execution manual](../../user_manual/configuration-execution.md) for test commands, effects and pending owner validation.

Iteration 2 retains the implementation after comparing test-only 10/100 ms
windows against the current one-second guard: lower waits accept delayed false
prompts for both vendors. Empty receive queues and matching echoes do not establish
a response boundary. Probe/newline protocols require separate vendor validation and
owner approval; no weaker synchronization contract is selected. See the
[alternatives and test-report provenance](../../user_manual/configuration-execution.md#iteration-2-completion-alternatives-and-controller-evidence).
