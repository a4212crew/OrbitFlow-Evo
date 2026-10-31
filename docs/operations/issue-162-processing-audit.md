# Issue #162 processing audit and validation ledger

This is an implementation audit for review, **not Issue acceptance**. The fourth
revision replaces aggregate observation/result storage in the v2 pipeline,
streams public plan JSON, preserves protected workbook review and retains source
files for new confirmations. It also adds indexed execution-journal consumption,
backup failure recovery, bounded journal append/read and prompt/save response bounds. The matrix describes
current source; older increment ledgers below are historical and superseded where
explicitly noted. No private captures or devices were used. Historical workbook
binding cannot be reconstructed. Owner/native Windows and controller-safe suite
gates remain separate from synthetic implementation checks.

Paths below are relative to `src/orbitflow/`; test paths are relative to `tests/`.
All listed automated tests are offline. The full-suite ledger below distinguishes
repository-wide regression checks from newly added scalability assertions.

| Workflow / source | Collection and memory | Persistence / consumption / output / recovery | Decision and remaining risks | Regression coverage |
|---|---|---|---|---|
| Shared runner `execution.py` | Bounded device futures; sink mode retains only in-flight payloads; no-sink mode returns full list | Caller-owned sink; per-device cleanup and failure isolation | Retain scheduler. Retain no-sink list API for bounded callers; audited data-heavy workflows use sinks | `test_device_execution.py`, `test_result_spool.py` |
| Shared spool `result_spool.py` | One owner appends sanitized envelopes; input-position metadata retained | Authoritative JSONL + manifest; temporary SQLite offsets; partial recovery opt-in; lease-controlled cleanup | Implement reusable index, point/target/256-position batch retrieval, one index per consumption, 64 MiB marked/new envelopes, finite 256 MiB historical unmarked envelopes and 64 GiB spool limits, envelope checks, fsync before checkpoint; scratch index is disposable | `test_result_spool.py`, `test_result_index.py` |
| Planning v1 `configuration/plans.py`, `approvals.py` | Offline closed-schema identity/operation metadata only; max 100 targets (default 5), max 100 operations each; bounded scalar fields, no large raw observations | Canonical immutable JSON and signed SQLite authority | **Implement/retain:** add shared 16 MiB bounded file reads before JSON decoding for v1 request/plan files; retain small canonical payload and transactional signed decisions without schema migration | `test_configuration_plans.py` |
| Planning v2 observation `configuration/v2/observation.py` | Shared per-device workers; disk-backed detached observation map via shared `indexed_json.py` | Existing durable bound spool; one decoded device per access; no 16 MiB aggregate gate | **Implement:** request/workbook binding before networking; indexed working-set copy validates sanitation before persistence | `test_bulk_configuration_v2.py`, `test_result_index.py`, `test_configuration_indexed_pipeline.py` |
| Planning v2 build/validation `configuration/v2/planning.py` | Requests capped at 5,000; complete same-device row groups evaluated in workbook order; global identity collision metadata; indexed ordered results | Streamed canonical JSON save/load, immutable digest and deterministic reevaluation; 256 MiB individual value/projection allowance, 64 GiB input bound | **Implement:** remove 32 MiB aggregate gate; preserve nonadjacent same-device projections and public schemas. Explicit content/to_dict compatibility APIs materialize on demand | Planning/v2 approved-service/recovery suites and full-pipeline test |
| Planning review/XLSX `configuration/v2/workbook.py` | Write-only worksheet cells, indexed observation/result views; bounded input/result row metadata and per-device scoped evidence | Existing sheets/columns/presentation, exact protected-cell comparison and digest; read-only review, scratch cleanup | **Implement/retain:** indexed source view replaces full-plan decode; retain complete protected review and unchanged output cells | `test_configuration_streaming_workbook.py`, `test_configuration_recovery.py`, full-pipeline test, console regressions |
| Confirmed execution prepare/confirm `configuration/execution.py` | Indexed source observation/result access; selected/skipped summary metadata remains capped by 5,000 source rows | New source plan JSON retained under existing authority directory; SQLite confirmation binds source/summary digests; old inline payload supported | **Implement:** remove aggregate source-plan confirmation parameter/load. Retain explicit summary confirmation, replay claim, backup, fresh identity, verification and save gates. Summary is still a materialized public return value | `test_configuration_execution*.py`, full-pipeline mocked confirm/replay, timing suites |
| Execution report `configuration/execution.py:export_results` | Shared journal offset index; row-specific event reads and disk-backed detail references; per-row command evidence | Same offline write-only workbook, truthful historical Unknown statuses and complete links | **Implement:** eliminate full-run event-offset/reference maps and repeated per-row journal scans. Retain bounded source-summary metadata and per-row output construction | Execution/performance suites; journal-index regression in `test_result_index.py` |
| Manual Configuration `configuration/manual.py` | One shell/session per device; max 10,000 input rows, 32,767 CLI characters and 1,000 commands per row; receive callback streams captures, pending fragment capped at 65,536 characters | Shared spool and fsynced journal; report reduces only per-row/device metadata; transcripts remain disk files; atomic workbook refresh/recovery | **Retain:** no full-run response/command-event list is retained in report reconstruction. Metadata maps have explicit source-row bounds. Preserve no replay/reconnect and success-only group save | `test_manual_configuration.py`, shared CLI/lifecycle regressions |
| Inventory refresh `inventory_refresh.py`, `inventory/store.py` | Shared worker sink; attempt rows stay on spool; O(identity count) status membership and latest stable contexts, without volatile observations | Shared snapshot JSONL; atomic write-only captured-view workbook recovery; synchronized atomic canonical JSON inventory | **Retain:** existing 1,500-target/concurrency-five test verifies complete rows and cleanup. Canonical latest-facts snapshot and public contexts tuple remain materialized; this persistent-state format is distinct from large operational evidence. No database/schema migration claimed | `test_inventory_refresh.py::test_1500_inventory_attempts_stream_at_concurrency_five`, inventory/atomic replace suites |
| Interface/VLAN and database report `reporting.py` | Shared workers; per-device normalized rows/evidence; no full-run report rows | Shared spool; table generators; evidence-reference overflow; atomic workbook; offline export | Retain per-device normalization and streaming workbook. Inherits one validated index across all passes. Oversized individual device now fails explicitly and retains incomplete spool | `test_device_reporting.py`, `test_aggregation.py`, `test_aggregation_consumers.py`, `test_aggregation_owner_revision.py` |
| VLAN compliance/database `vlan_compliance.py`, `compliance_report.py`, `methodology_report.py` | Single-device audit resolvers; shared worker sink | Findings/error spool; multi-pass streaming tables; complete overflow detail; retained-spool retry | Retain family audit ownership and output schemas; index reuse removes repeated SQLite builds. Per-device finding/evidence payload is still the unit of memory | `test_vlan_compliance.py`, `test_vlan_configuration_audit.py`, `test_methodology*.py` |
| MAC observation/report `mac_lookup.py` | Shared workers; device-local MAC/BD snapshots | Shared spool; write-only tables and offline retained-spool export | Retain normalized lookup ownership and seven-column main sheet; inherits shared index reuse. Single-device table size remains bounded only at spool write, after collection | `test_mac_lookup.py` |
| Configuration backup `configuration_backup.py` | Worker-owned protected captures; shared sink stores only sanitized six-column failure rows and success markers | Retained shared spool in existing backup run .processing directory; atomic failed_devices.xlsx export/retry; optional offline recovery API | **Implement:** durable failure-output reconstruction without recapture. Raw configuration stays outside SQLite/JSONL; capture paths and workbook columns unchanged | `test_configuration_backup.py`, offline failure/disk-full/retry test |
| Transport/CLI `transport/`, `vendors/common.py` | Device-owned channels, bounded active workers; prompt/save exchanges cap received bytes at 64 MiB; literal callback stream stays disk-backed | No cross-device full-run buffers; setup/cleanup paths unchanged | **Implement/retain:** explicit oversize response failure before buffer growth, with unsafe-session handling; retain approved Linux/Windows SSH architecture, paging and prompts. Existing enable authentication caps receive bytes at 131,072 in `vendors/privilege.py`; retain its private exchange handling | `test_transport*.py`, `test_shared_cli.py`, `test_cisco_ios_cli.py`, `test_cli_lifecycle.py`, manual/execution suites |
| Console/logging `menu.py`, `terminal_progress.py`, `logging/` | Serialized progress, bounded recent activity; module-owned sanitized logging | Existing menu/profile/log paths | Retain presentation and API defaults. Optional direct recovery CLI/API added; menus remain unchanged as required | `test_operations_console.py`, `test_logging.py`, `test_terminal_progress.py`, `test_workflow_progress.py` |
| Shared XLSX `excel_output.py` | Write-only row generators; current-row memory | Temporary workbook + replace; literal strings, oversize-cell rejection | Retain existing atomic publication; new indexed API changes neither columns nor formatting | Reporting, compliance and MAC suites |

## New automated scale checks

`test_result_index.py` writes synthetic, sanitized envelopes in reverse completion
order and checks complete input-order output and point retrieval for:

- 88 targets × 875,000 payload characters: approximately 77 MB of evidence.
- 500 and 1,500 targets × 65,536 payload characters.
- A `tracemalloc` peak assertion below 16 MiB for each case, covering collection
  and index consumption. This measures Python allocations, not total process RSS
  or the complete planning pipeline. SQLite uses a 512 KiB cache and file-backed
  temporary storage.

Other new tests exercise corrupt/missing/duplicate/truncated envelopes, invalid
positions, bounded access to an infinite position iterator, disposable transaction
interruption, idempotent rereading, disk-full/permission allocation errors, failed
export retention, cleanup, pre-network binding and sanitization. Existing spool
suite covers leases/concurrent workers, checkpoint and cleanup permission retries,
sink failure and interrupted partial recovery. These do **not** establish the
whole requested transaction-crash, cross-process concurrency or atomic plan pair
publication matrix.

## Owner-run automated validation

Run from this worktree with dependencies installed. `PYTHONPATH` is required here
because the environment's editable installation otherwise resolves another checkout.

Linux:

```bash
PYTHONPATH=src python -m pytest tests/test_result_spool.py tests/test_result_index.py tests/test_bulk_configuration_v2.py -q
PYTHONPATH=src python -m pytest -q
```

Windows PowerShell:

```powershell
$env:PYTHONPATH = (Join-Path (Get-Location) 'src')
python -m pytest tests/test_result_spool.py tests/test_result_index.py tests/test_bulk_configuration_v2.py -q
python -m pytest -q
```

Expected: all deterministic tests pass in a normal controller environment. The
managed implementation worker may reject orchestration tests creating temporary
Git markers; record those separately rather than weakening the guard. Native
Windows testing remains owner-controlled and pending.

## Read-only operator validation

Only use owner-selected retained, sanitized runs, and a **new output destination**.
Use the existing offline exports documented in
[spool architecture](../architecture/result-spool.md). For example, on both Linux
and Windows, run `python` with the worktree `src` on `PYTHONPATH`, then:

```python
from orbitflow.result_spool import ResultSpool

spool = ResultSpool('OWNER_SELECTED_RETAINED_RUN')
with spool.indexed() as index:
    print(len(index))
    for record in index.records(positions=[1]):
        print(record['input_position'], record['status'])
```

Expected: metadata only on stdout; no network connection, no inventory mutation,
no device writes. The temporary index is deleted on normal exit, while original
JSONL/manifest remain. Missing/duplicate/corrupt completed records fail explicitly;
index allocation needs writable run-directory space. Complete collection is still
required for ordinary output consumption; partial export needs the existing
explicit opt-in. Do not inspect or print private payloads in shared logs.

The optional planning-recovery CLI/API is documented in the [planning manual](../user_manual/bulk-configuration-planning.md#offline-retained-observation-recovery-issue-162-revision); the fourth revision uses indexed observations/results.
The owner's private ~77 MB spool/workbook must remain outside this worktree and
must not be searched for or uploaded. Legacy manifests have no binding. Current
planning freshness, immutable digest, review and execution gates are unchanged.
Actual device, private-spool and Windows validation are pending owner actions,
not automated-test claims. Do not replay completed/Unknown configuration changes.

## Acceptance still required

This Issue is not complete until the remaining rows above are implemented or
justifiably retained, end-to-end >16 MiB observations and >32 MiB candidate plans
recover/export with unchanged public artifacts, protected review and execution
consumers pass, and the complete requested fault/scalability matrix is validated.
This ledger does not assert a technical contradiction or request a scope split.

## Implementation-worker test ledger (2026-10-27)

- `PYTHONPATH=src python -m pytest tests/test_result_spool.py tests/test_result_index.py tests/test_bulk_configuration_v2.py -q`: 204 passed at the initial index/binding increment; later additions are recorded below.
- `PYTHONPATH=src python -m pytest tests/test_result_spool.py tests/test_result_index.py -q`: 47 passed after lease protection/index reuse.
- `PYTHONPATH=src python -m pytest tests/test_result_index.py -q -o junit_family=legacy --junitxml=/tmp/issue-162-index-results.xml`: 20 passed, zero failures/skips. Measured peaks: 3,802,488 bytes (88 targets), 619,692 bytes (500), 847,192 bytes (1,500). The XML is a temporary worker artifact, not a committed capture.
- Initial whole-suite run: `PYTHONPATH=src python -m pytest -q`: **3,758 passed / 25 failed / 0 skipped**, 137.91 seconds. All 25 failures are orchestration tests whose `controller_temp` guard rejects `/tmp/orbitflow-issue-162-codex-l4sq50gc` as within a Git worktree under the managed sandbox. Tests cannot reach their intended subprocess assertions. No guard, Git marker or unrelated orchestration source was changed. This is not a passing full-suite gate.

Subsequent final-source affected and whole-suite results are appended below.

Affected-workflow command (1,377 passed / 0 failed / 0 skipped, 104.81 seconds):

```bash
PYTHONPATH=src python -m pytest tests/test_result_spool.py tests/test_result_index.py tests/test_bulk_configuration_v2.py tests/test_device_execution.py tests/test_device_reporting.py tests/test_inventory_refresh.py tests/test_vlan_compliance.py tests/test_mac_lookup.py tests/test_configuration_backup.py tests/test_manual_configuration.py tests/test_configuration_execution.py tests/test_configuration_execution_evc.py tests/test_configuration_plans.py tests/test_transport.py tests/test_logging.py tests/test_operations_console.py -q
```

A subsequent whole-suite run after index lease/reuse additions returned
**3,760 passed / 25 failed / 0 skipped**, 135.37 seconds, with the identical
orchestration guard failure set. The final binding-hash implementation streams
canonical encoder chunks instead of constructing an aggregate request JSON string;
its digest is checked against the existing canonical representation.

Final-source checks:

- `PYTHONPATH=src python -m pytest tests/test_result_spool.py tests/test_result_index.py tests/test_bulk_configuration_v2.py -q`: **206 passed / 0 failed / 0 skipped**, 18.53 seconds.
- `PYTHONPATH=src python -m pytest -q`: **3,760 passed / 25 failed / 0 skipped**, 135.37 seconds. The 25 failing test IDs match the initial run exactly and remain the orchestration temp-root guard cases, not a passing gate.
- `git diff --check`: passed. Affected Markdown local-file links: checked, no missing targets.

The complete Issue acceptance gate has not passed. No commits, pushes, PR/state
changes, configuration writes or live testing were performed.


## Same-Issue revision: limited recovery and streamed review (2026-10-27)

This revision does **not** close the remaining acceptance gates above. The matrix
and prior test ledger describe the initial increment; the following entries
supersede only their recovery/review statements:

| Module | Revision and evidence | Remaining gap |
|---|---|---|
| `configuration/v2/recovery.py`, `cli.py` | New offline `recover` API/subcommand leases the shared index; checks task, completeness, exact source/request binding, target positions/status/identity and bound freshness before export. Legacy opt-in labels provenance unverified. Both files generated before exclusive publication. Tests: `test_configuration_recovery.py`. | Retains aggregate limits; cannot recover ~77 MB. Two-file publication is not crash-atomic. No live/Windows validation. |
| `configuration/v2/planning.py`, `configuration/execution.py` | Diagnostic provenance is deterministic digest-bound result evidence, persists through decision reevaluation, and is an unconditional execution-preparation rejection. Tampered results fail revalidation. Tests: recovery and existing planning/execution suites. | Full canonical plan/confirmation materialization unchanged. |
| `configuration/v2/workbook.py` | Protected actual/expected review workbooks use read-only iterators; dimensions, sheet order, formulas and protected values still checked. Regression verifies both loader calls use streaming mode. | Regenerated workbook export and decoded plan remain materialized. |
| `result_spool.py` | Public indexed context exposes its existing index to nested `records()`/`indexed()` on the owning thread; fixes duplicate lease acquisition found by recovery tests. Normal/exception exit clear the view and release scratch/lease. Tests: `test_result_index.py`. | The second-review increment below supersedes the 16 MiB envelope cap; other earlier audit gaps remain unresolved. |

Exact supported Linux/Windows recovery commands, return values, errors and
limitations are in the [operator/API guide](../user_manual/bulk-configuration-planning.md#offline-retained-observation-recovery-issue-162-revision).
The direct optional recovery entry point leaves menus unchanged under the Issue's
explicit interface requirement. No private input was sought or used.

Security-guard environment evidence: `TMPDIR`, `TMP`, and `TEMP` point beneath
`/tmp/orbitflow-issue-162-codex-xzq3e_jt`; this sandbox exposes `/tmp/.git`.
`controller_temp()` correctly rejects a temp root with any `.git` ancestor.
All writable roots are within that ancestor or this checkout. No guard, Git marker,
permissions, or orchestration code was altered to bypass the rejection. A passing
whole-suite run still requires a controller-safe owner environment outside these
managed filesystem constraints; this is an environment limitation, not Issue
completion or a demonstrated contradiction in the requested processing design.


Revision checks completed so far:

- Recovery/planning before read-only comparison: `PYTHONPATH=src python -m pytest tests/test_configuration_recovery.py tests/test_result_spool.py tests/test_result_index.py tests/test_bulk_configuration_v2.py -q`: **215 passed**, zero failures/skips.
- Recovery/index/planning/execution with read-only comparison: **422 passed**, zero failures/skips (`/tmp/issue-162-revision-final-targeted.txt`, worker-only log).
- Final protected review/recovery check: `PYTHONPATH=src python -m pytest tests/test_configuration_recovery.py tests/test_bulk_configuration_v2.py -q`: **176 passed**, zero failures/skips, 15.59 seconds; includes forged OOXML dimensions and resource closure changes.
- Initial revision whole suite: `PYTHONPATH=src python -m pytest -q`: **3,775 passed / 25 failed / 0 skipped**, 173.26 seconds. Same controller temp-root guard failure category described above. This preceded the final streamed-review/resource-closure additions.
- `PYTHONPATH=src python -m orbitflow.configuration.v2.cli recover --help`: passed without network access.
- Changed Markdown local-file links and `git diff --check`: passed.

Final whole-suite and all-module targeted commands/results follow below.


Final-source audited-module command:

```bash
PYTHONPATH=src python -m pytest tests/test_configuration_recovery.py tests/test_result_spool.py tests/test_result_index.py tests/test_bulk_configuration_v2.py tests/test_device_execution.py tests/test_device_reporting.py tests/test_inventory_refresh.py tests/test_vlan_compliance.py tests/test_mac_lookup.py tests/test_configuration_backup.py tests/test_manual_configuration.py tests/test_configuration_execution.py tests/test_configuration_execution_evc.py tests/test_configuration_plans.py tests/test_transport.py tests/test_logging.py tests/test_operations_console.py -q
```

Result: **1,396 passed / 0 failed / 0 skipped**, 137.77 seconds. Covers all
workflow families in that command; additional family/parser and orchestration
suites are included in the whole-repository run. A subsequent whole suite after
streamed-review additions returned **3,779 passed / 25 failed / 0 skipped**,
183.69 seconds; same temp-root guard category, no passing full gate claimed.


Final-source full repository gate: `PYTHONPATH=src python -m pytest -q` returned
**3,779 passed / 25 failed / 0 skipped**, 178.36 seconds
(`/tmp/issue-162-final-source-full.txt`, worker-only log). Failed test IDs match
the earlier 25 controller temp-root guard cases. This is **not a green full-suite
run**. No guard was weakened. Owner-run safe-temp commands are in the canonical
planning manual. The remaining primary >16/>32 MiB pipeline, full all-module
implementation and oversized-record compatibility gates are still open; no
technical design contradiction is asserted and no Issue acceptance is claimed.


## Second-review implementation increment (2026-10-27; incomplete)

`ResultSpool.append` now stages sanitized JSON encoder chunks in a temporary
on-disk file before copying a complete envelope to authoritative JSONL. It no
longer joins the serialized full device table and then creates a second encoded
byte string to measure it. Serialization, record/disk limit and scratch allocation
failures leave earlier committed JSONL unchanged and mark collection interrupted.
The existing fsync/checkpoint and no-retry behavior remains. A failure while copying
to authoritative JSONL may still leave a partial final line: incomplete-run readers
retain their existing partial-record policy. Scratch staging is not an atomic
filesystem transaction or a replacement for the JSONL/manifest durability model.

The individual envelope ceiling is 64 MiB, shared by append and legacy/new readers;
the spool ceiling remains 64 GiB. Regression fixtures exercise 17 MiB individual
records with and without source binding, repeated indexed retrieval, sanitation,
serialization failure, scratch failure and disk/record bounds. A separate measured
serialization test uses a >16 MiB device table and asserts <8 MiB additional Python
allocations, excluding caller-owned input and later decoding. This does not
establish an end-to-end memory bound. Historical per-device records above 64 MiB
are still unsupported: universal historical-size compatibility is **not resolved**.

This increment does not address the blocking full-plan pipeline. The aggregate
16/32 MiB limits, execution preparation, warranted module gaps, crash-safe plan
pair publication, and full fault/scalability acceptance gates remain open. No
claim of Issue completion or architecture contradiction is made. The earlier
module decisions marked unfinished remain unfinished. Owner/private-spool/live
and native Windows validation remain pending.


Second-review validation evidence:

- `PYTHONPATH=src python -m pytest tests/test_result_spool.py tests/test_result_index.py tests/test_configuration_recovery.py tests/test_bulk_configuration_v2.py -q`: **232 passed / 0 failed / 0 skipped**, 22.93 seconds (before the last serialization-memory test).
- `PYTHONPATH=src python -m pytest tests/test_result_index.py -q -o junit_family=legacy --junitxml=/tmp/issue-162-second-review-memory.xml`: **30 passed / 0 failed / 0 skipped**, 11.35 seconds. Measured peak Python bytes: 88-target/~77 MB spool 4,038,044; 500 targets 1,474,891; 1,500 targets 1,438,880; >16 MiB individual table serialization 704,529. Temporary XML is worker-only synthetic evidence.
- Initial full suite: **3,786 passed / 25 failed / 0 skipped**, 146.79 seconds. The failures remain controller temp-root guard cases. This run preceded the final serialization-memory test and the append offset micro-optimization; a final-source run follows below.
- Changed Markdown local-file links: no missing targets.

Final-source audited-module command (same 18 test files listed under
“Final-source audited-module command” above): **1,404 passed / 0 failed / 0 skipped**,
114.98 seconds (`/tmp/issue-162-second-review-modules.txt`, worker-only log).
This includes the final append implementation and serialization-memory test.

Final-source full repository gate: `PYTHONPATH=src python -m pytest -q`: **3,787
passed / 25 failed / 0 skipped**, 143.57 seconds
(`/tmp/issue-162-second-review-final-full.txt`, worker-only log). Failed test IDs
match the earlier 25 orchestration guard failures exactly; diagnostics reject
`/tmp/orbitflow-issue-162-codex-ymh1iaqv` because the inherited OS temp directory
has a Git ancestor. No guard or Git marker was changed. This is not a green gate.
Owner-host Linux/Windows safe-temp commands remain in the planning manual.
`git diff --check` passed. No commits, pushes, PR/state changes, device writes or
owner/private/live validation were performed.


## Third-review increment (2026-10-27; Issue remains incomplete)

This section supersedes the writer-specific statements above only. It does not
close the primary functionality or whole-module acceptance findings.

| Module / decision | Collection and memory | Persistence, output and recovery | Verification / remaining risk |
|---|---|---|---|
| v2 `workbook.py:export_plan` — implement | Still decodes full plan. Fixed template is copied into write-only worksheets; proposal/evidence cells stream to XML, retaining bounded input metadata and row dimensions. | Existing sheets/columns, layout, comments, hyperlinks, styles, validation lists, literal values, digest/evidence references and decisions retained. Ordinary errors close/remove owned XML scratch. | New `test_configuration_streaming_workbook.py`: 88/500/1,500 rows, 50 evidence lines each, complete exact ordered evidence, writer-only peak <16 MiB; presentation and error cleanup. Full plan and scoped per-request evidence remain materialized. No full-pipeline memory claim. |
| v2 protected review — retain | Read-only expected/actual scans still calculate dimensions from actual cells. | Write-only XML omits optional dimension hints; forged-hint regression now inserts a lying hint explicitly before adding an out-of-range cell. | Existing recovery/planning regressions plus forged-hint check. Source plan, digest and execution authority unchanged. |
| Shared spool historical envelopes — verified incompatibility | Individual `readline` remains capped at 64 MiB before JSON decoding. | A directly constructed historical-format 65 MiB sanitized envelope is rejected with `Spool record size limit exceeded`; original JSONL/manifest retained and scratch cleaned. | `test_result_index.py::test_historical_envelope_over_64_mib_fails_before_json_decode`. This is concrete historical incompatibility evidence, not a claim of supported recovery. Larger historical envelopes remain unresolved and need an owner-approved bound/compatibility decision. No limit was silently raised or bypassed. |
| Other workflow decisions above — outstanding | No additional collection, inventory, manual, backup, transport or execution implementation changes in this increment. | Their previous implemented/retained/unfinished distinctions continue to apply. | Whole-suite regression is recorded below; this is not a completed per-module design audit or a rationale for leaving mandatory work unfinished. |

The primary aggregate observation/plan pipeline is unchanged. In particular,
`recovery.py` still calls `bounded_observations`, `BulkPlan` still enforces 32 MiB,
and downstream JSON/decision/confirmation consumers remain aggregate. The required
~77 MB end-to-end planning/review/recovery and 88/500/1,500 full-pipeline tests
remain absent. No architecture contradiction is asserted. Owner private-spool,
actual device and native Windows validation remain pending.

Compatibility spot-check against the HEAD exporter used one synthetic C3750X
plan with a row gap and compared all sheet values, concrete fonts/fills/borders/
alignment/number formats/protection, comments, hyperlinks, data validations,
merged cells and sheet order: matched. It used a temporary directory and no
networking. Existing protected-review regressions provide the broader template
coverage; the spot-check is not full-pipeline validation.

The isolated writer measurement recorded peak Python allocations of 5,838,595
bytes (88 rows), 5,869,019 (500), and 6,287,010 (1,500), excluding already-decoded
input and full-plan construction. The measurement command also initially found a
style-proxy comparison test failure, corrected before the final full-suite run;
the measurement is not itself a passing final-source command. Full-source checks
are recorded below. RSS and complete 77 MB planning were not measured.


Third-review validation before the last invalid-row precedence correction:
`PYTHONPATH=src python -m pytest -q`: **3,793 passed / 25 failed / 0 skipped**,
207.98 seconds (`/tmp/issue-162-third-full.txt`, worker-only log). All failures
remain the controller temp-root guard category. A final compatibility check then
added last-invalid-row replacement and valid-row precedence handling; its direct
regression passed. The final-source full-suite result follows below.


Final-source third-review regression:

- `PYTHONPATH=src python -m pytest -q`: **3,795 passed / 25 failed / 0 skipped**, 220.69 seconds (`/tmp/issue-162-third-delivery-full.txt`, worker-only log). Includes all module families, seven new writer test cases (including invalid-row precedence and oversized evidence coordinates), and the new historical-envelope boundary case. The 25 failed IDs exactly match the earlier controller guard failures; no new failing test IDs. The guard rejects `/tmp/orbitflow-issue-162-codex-wgv3d1_i` because `/tmp/.git` is an ancestor marker. Writable roots remain inside that ancestry or this checkout; no guard, permissions or Git marker was changed. A passing controller-safe owner run is still required.
- Focused planning/recovery after invalid-row correction: `PYTHONPATH=src python -m pytest tests/test_configuration_recovery.py tests/test_bulk_configuration_v2.py -q`: **176 passed / 0 failed / 0 skipped**, 19.43 seconds. Subsequent oversized-reference correction is covered by the final full suite.
- `PYTHONPATH=src python -m pytest tests/test_result_index.py -q`: **31 passed / 0 failed / 0 skipped**, 11.74 seconds; includes direct historical 65 MiB rejection.
- `git diff --check`: passed. Affected Markdown relative file targets: no missing files.

The primary requested implementation remains incomplete. No full-pipeline 77 MB,
>32 MiB plan or end-to-end 500/1,500 target recovery result is claimed. No
production, private-spool or native Windows validation, commit/push/PR/state
operation or merge occurred.


## Fourth-review source rationale and remaining limits

The current matrix supersedes previous open implementation decisions for v2,
execution report indexing, backup report recovery and prompt/save receive buffers.
All workflows use shared execution/spool interfaces where applicable. There are no
feature-owned worker pools or new persistent per-feature processing databases.
The reusable `indexed_json.py` scratch working set and existing result/journal
offset interface own SQLite behavior; published JSON/JSONL remain authoritative.

- Preserve v1 bounded signed-plan semantics; they do not collect large observation
  bundles. Preserve streaming report/compliance/MAC normalization and exports.
- Preserve canonical inventory latest-fact JSON and its synchronized writes; it
  is a persistent identity catalogue with a public tuple accessor. The run report
  uses captured spool snapshots and streams. No volatile device output is retained
  in this canonical store. Its memory still grows with identity count; an
  unbounded persistent catalogue migration is not claimed.
- Preserve Manual Configuration source-row/decision metadata capped by existing
  input validation. Transcripts stream to files and journal recovery retains
  latest row/device metadata, not all command responses. No write resume exists.
- Backup recovery now covers complete retained failure metadata; failed capture
  files are never reconstructed from a generic spool. An interrupted collection
  remains explicitly incomplete, requiring owner inspection rather than recapture.
- New/marked envelopes remain limited to 64 MiB. Historical unmarked envelopes
  allow up to 256 MiB, tested with the demonstrated 65 MiB case; this is a finite
  compatibility strategy, not universal historical-size support. Larger single
  legacy envelopes still require an owner capacity decision. Do not alter captures
  to evade digest/provenance checks. SQLite JSON values and same-device projected
  result groups also have a finite 256 MiB allowance; input totals cap at 64 GiB.
- Public `content`/`to_dict` and execution summary return values retain their
  materializing compatibility contract. Internal observation/result consumers
  avoid full-plan materialization. Requests and selected/skipped command summaries
  remain bounded source-row metadata. Two public recovery filenames are linked
  separately; process-crash atomicity across the pair is not claimed. Each source
  plan JSON is published atomically after complete serialization/fsync.

The requested universal no-aggregate-consumer and complete crash/failure matrix
are not asserted by these qualified limits. Source/identity/age, protected cells,
canonical digest, replay, backup, verify and save safety remain required.
No production/private-spool or native Windows result is inferred from synthetic
coverage. Final automated commands/counts and measurements follow below.

Fourth-review checks completed before the final full-suite gate:

- `PYTHONPATH=src python -m pytest tests/test_configuration_indexed_pipeline.py -q -o junit_family=legacy --junitxml=/tmp/issue162-pipeline-final.xml`: **9 passed / 0 failed / 0 skipped**, 741.89 seconds. This run preceded the later load-result hash-only hardening and additional fault tests; the final full suite includes those changes. Measured full-pipeline peaks: **13,200,113 bytes** (88 targets × 900,000 padding characters, ~79 MB), **15,261,006 bytes** (500), **33,458,094 bytes** (1,500). All three output JSON files exceeded 32 MiB, with complete request/results checks, unchanged-workbook protected review, decision evaluation, source load, preparation, mocked confirmation and replay rejection. These are Python allocation measurements, not RSS or live network tests.
- Audited-module command (the 18-file command above): **1,407 passed / 0 failed / 0 skipped**, 175.55 seconds. Later source-load/reference hardening is covered separately and by the final full run.
- `PYTHONPATH=src python -m pytest tests/test_configuration_execution*.py -q`: **428 passed / 0 failed / 0 skipped**, 56.00 seconds, after restoring the older to_dict-only decision adapter compatibility. Two adapter failures in an earlier interrupted full run were corrected; no failed run is reported as green.
- `PYTHONPATH=src python -m pytest tests/test_bulk_configuration_v2.py tests/test_configuration_v2_approved_services.py tests/test_configuration_execution_stages.py tests/test_configuration_indexed_pipeline.py -k 'not full_recovery' -q`: **581 passed / 0 failed / 3 deselected**, 98.36 seconds. Deselection is the three separately measured scale cases, not skipped validation.
- `PYTHONPATH=src python -m pytest tests/test_configuration_indexed_pipeline.py -k 'not full_recovery' tests/test_configuration_recovery.py -q`: **31 passed / 0 failed / 3 deselected**, 4.22 seconds. Includes hash-only untrusted-result persistence, constructor compatibility, scratch transaction cleanup, value/disk limits, invalid JSON/chunk boundaries, concurrent immutable readers and atomic JSON publication failure.
- Historical 65 MiB reader fixture invoked under `tracemalloc` in a temporary directory with a 512 MiB assertion: **274,080,815 peak Python bytes**, passed. This deliberately larger single-record working set is separate from the 96 MiB ordinary pipeline assertion. The finite legacy allowance does not assert compatibility with arbitrarily large historical envelopes.
- Worker comparison against pre-revision HEAD planning source: four synthetic targets/eight requests, same-device database/description rows across sheets; **exact canonical content and SHA-256 matched** for Pending, Approve and Reject decisions. Existing deterministic suites cover dependencies, overlap, blockers/no-ops, tamper and vendor commands.
- `PYTHONPATH=src python -m orbitflow.configuration.v2.cli recover --help`: passed, no networking. Changed Markdown local-file links: no missing targets. Final diff check and full-suite result follow below.

Source-load security: supplied results are retained only as per-row SHA-256 values
until deterministic reevaluation matches. An injected secret-bearing result never
enters scratch SQLite; only the validated recomputed result is retained. Source
observations are sanitized/validated before SQLite insertion, and observation keys
must be canonical IP addresses. New confirmation file references must match their
UUID and cannot select an arbitrary path. No freshness or approval bypass exists.


Additional final-source focused checks:

- `PYTHONPATH=src python -m pytest tests/test_result_index.py tests/test_configuration_execution*.py -q`: **461 passed / 0 failed / 0 skipped**, 64.92 seconds. Includes missing-journal compatibility: a run interrupted before its first event keeps the historical empty-evidence view, without creating a journal or reconnecting.
- `PYTHONPATH=src python -m pytest tests/test_configuration_indexed_pipeline.py -k 'not full_recovery' tests/test_configuration_recovery.py tests/test_result_index.py -q`: **68 passed / 0 failed / 3 deselected**, 18.35 seconds. Includes one-/two-/seven-/17-character split-stream decimal/exponent/boolean/null/escaped-string parsing. Public plan loading additionally checks actual file bytes against the 64 GiB input ceiling before parsing.
- `PYTHONPATH=src python -m pytest tests/test_configuration_execution.py tests/test_configuration_recovery.py -q`: **215 passed / 0 failed / 0 skipped**, 9.59 seconds, including confirmation-source validation.

Owner validation remains read-only unless separately and explicitly authorized.
The synthetic mocked confirm consumer verifies authorization/replay plumbing, not
actual device configuration. Existing owner lab evidence is not new validation of
this revision. No credentials, production captures, Git/GitHub lifecycle changes
or live configuration operations were used.


Final shared-journal audit closure: `ResultJournal.append` now stages sanitized
encoder chunks under the owning writer lock and checks the 256 MiB event/64 GiB
journal ceilings before copying. Both legacy iteration and indexed iteration
read bounded complete lines. Serialization/size/scratch failures preserve the
committed prefix and stop later appends; partial authoritative-copy failures
remain incomplete final lines, ignored in recovery. Tests cover record/total
limits, stopped writer, committed-prefix preservation and missing journals.
An earlier focused shared-spool/index/Manual/all-execution run passed **690 tests**
(74.63 seconds) before the final total-journal assertion; the final-source focused
and whole-suite results follow. No completed interrupted full-suite run is
represented as a passing gate.


V1 audit refinement: schema bounds alone did not protect file loading before
validation. V1 request/plan readers now share a 16 MiB bounded binary read before
UTF-8/JSON decoding, exceeding the maximum canonical valid schema size. Signatures,
schema, digests and signed approvals remain unchanged. `PYTHONPATH=src python -m
pytest tests/test_configuration_plans.py -q`: **45 passed**, 0 failures/skips,
0.21 seconds, including pre-decode file-bound and CLI rejection.

The first completed fourth-review full run returned **3,818 passed / 29 failed /
0 skipped** in 1,179.58 seconds. Four failures were integration assertions that
forbade any backup results.jsonl; they now assert its exact metadata-only success
payload while retaining all credential-disclosure checks. `PYTHONPATH=src python
-m pytest tests/test_device_access.py -q`: **493 passed**, 0 failures/skips, 0.80
seconds. The other 25 failures match the known controller temp-root guard cases.
That is not a green full-suite gate. The final rerun includes the corrected tests
and the v1 input bound.

Fresh-process Linux RSS verification ran each full-pipeline node separately under
`/usr/bin/time -f %M`, asserted a 256 MiB RSS ceiling and a passing pytest result.
All three passed (one test each; 0 failures/skips):

| Targets | Peak RSS bytes | Peak Python allocations bytes |
|---|---:|---:|
| 88 (~79 MB observations) | 108,011,520 | 13,871,908 |
| 500 | 116,908,032 | 16,421,503 |
| 1,500 | 164,986,880 | 33,980,937 |

These measurements cover the full retained recovery/export/load/protected-review/
decision/preparation/mocked-confirmation chain. Fixture spool construction is
separate; shared collection/spooling scale tests cover that phase. They are
Linux synthetic measurements, not native Windows, private captures or live-device
validation. The v1-only file bound added afterward does not alter this v2 path.

## Final fourth-review automated gate — 2026-10-28

```bash
PYTHONPATH=src python -m pytest -q -o junit_family=legacy --junitxml=/tmp/issue162-fourth-final-full.xml
```

**3,823 passed / 25 failed / 0 skipped; 1,061.61 seconds.** This is the complete
repository suite after the v1 input-bound implementation and backup integration
corrections. All 25 failure IDs exactly match the previously documented controller
set (seven Codex-runner cases, 17 controller cases, one lifecycle case). The guard
raises `OrchestrationError: OS temporary directory must be outside Git worktrees`
for `/tmp/orbitflow-issue-162-codex-zdaokmqv`; `/tmp/.git` is an ancestor marker.
No guard, Git marker or filesystem permission was changed. This is **not a green
full-suite gate**; a controller-safe owner-host full run remains mandatory.

Final-source full-pipeline peaks measured within that run were **19,022,107 /
20,173,934 / 37,005,342 Python bytes** for 88 / 500 / 1,500 targets, all below
96 MiB. Each generated complete JSON above 32 MiB, exported/reloaded/reviewed it,
evaluated decisions, prepared/consumed a mocked confirmation and rejected replay.
The separately isolated RSS assertions and their measurements are recorded above.

Selected audited-module results extracted from the full-suite XML (all zero
failures and zero skips; these are coverage groups, not an additional test run):

| Module test selection | Passed |
|---|---:|
| Shared result spool / index | 27 / 35 |
| Shared device execution | 17 |
| V1 plans / signed approvals | 45 |
| Bulk v2 / approved service planning | 159 / 326 |
| Recovery / indexed full pipeline / streaming workbook | 17 / 21 / 7 |
| All configuration execution test files | 428 |
| Manual Configuration | 201 |
| Device access / backup | 493 / 111 |
| Inventory refresh / device inventory | 28 / 19 |
| Interface/VLAN reporting | 83 |
| VLAN compliance / configuration audit | 50 / 180 |
| MAC lookup/reporting | 185 |
| Transport / logging / console | 29 / 16 / 97 |

Additional family, parser, interface, aggregation, timing, lifecycle, console and
other regression files are included in the 3,848 total tests. The matrix above
continues to distinguish retained stable metadata/public materializing accessors
from indexed operational evidence; it does not claim universal historical-size
support or a crash-atomic two-name publication. Legacy envelopes above 256 MiB
still need an owner capacity decision. Source records are never split or changed
to evade provenance or digest checks.

Final `git diff --check`: passed. Changed Markdown local-file links: no missing
targets. No private workbook/spool was sought or used. No production credentials,
actual device operations, commit, push, PR/state change or merge occurred.
Native Windows, private-spool and actual-device validation remain owner-controlled
and pending. This ledger is implementation/test evidence, not Atlas acceptance.

### Final pre-persistence validation hardening

A post-gate security review moved the **complete existing observation validator**
in front of SQLite insertion, rather than applying only its string sanitizer
before insertion and its schema/platform checks afterward. Malformed status or
platform data now fails before any supplied observation value is stored. The
validator is shared with deterministic evaluation; valid content/digests and
vendor behavior are unchanged. Two regression cases audit SQLite parameters to
ensure injected text in invalid live/unavailable observations never reaches disk.

`PYTHONPATH=src python -m pytest tests/test_bulk_configuration_v2.py
tests/test_configuration_v2_approved_services.py tests/test_configuration_recovery.py
tests/test_configuration_indexed_pipeline.py tests/test_configuration_execution*.py
-k 'not full_recovery' -q`: **950 passed / 0 failed / 3 deselected**, 103.51 seconds.
The three scale cases are repeated in the full suite and fresh RSS runs. The
3,823/25 full result above precedes this final hardening; the final-source results
are appended below, rather than being inferred from earlier runs.

## Authoritative final-source result after pre-insert validation — 2026-10-28

```bash
PYTHONPATH=src python -m pytest -q -o junit_family=legacy --junitxml=/tmp/issue162-prepersist-full.xml
```

**3,825 passed / 25 failed / 0 skipped / 0 errors; 1,141.53 seconds.** This result
supersedes the earlier final-gate counts for the completed source. The 25 failure
IDs exactly equal the established controller guard set, with no additional
failures. The OS temporary directory still has `/tmp/.git` as an ancestor; the
controller guard is preserved. A controller-safe owner-host full run remains an
outstanding gate. No Issue acceptance or merge readiness is claimed.

All 23 indexed-pipeline test cases passed, including both malformed-observation
pre-persistence checks. Other named module coverage counts in the table above are
unchanged. Final full-suite pipeline Python peaks were **17,950,501 / 20,189,491 /
37,063,070 bytes** at 88 / 500 / 1,500 targets (all <96 MiB).

Fresh-process RSS checks were repeated against this same source, one passing
full-pipeline test per invocation, asserting <256 MiB RSS and <96 MiB Python:

| Targets | Final peak RSS bytes | Final isolated Python peak bytes |
|---|---:|---:|
| 88 | 107,016,192 | 13,871,397 |
| 500 | 117,063,680 | 16,410,750 |
| 1,500 | 164,261,888 | 33,968,324 |

The latest XML/log/RSS files under `/tmp/issue162-prepersist-*` and
`/tmp/issue162-final-rss-*` are worker-only synthetic artifacts; permanent evidence
is this ledger and the deterministic tests. Linux/Windows reproduction and
read-only owner recovery instructions are in the planning/backup guides.

Final source/diff and changed Markdown file-link checks passed. Remaining limits
are the explicitly materializing compatibility APIs/bounded summary metadata,
canonical latest-inventory metadata, finite 256 MiB legacy allowance and lack of
a crash-atomic two-filename publication; these are described above rather than
claimed solved by a size-limit increase. Private-spool, actual-device, native
Windows and controller-safe owner-host validation remain pending. No Git/GitHub
lifecycle action or live configuration operation was performed.

## Fifth-review disposition — 2026-10-28

The earlier whole-module matrix remains the implementation disposition. This
revision hardens ownership rather than changing public formats or rewriting
retained workflows. Specific retained-path evidence:

| Review area | Disposition and exact evidence | Limitation |
|---|---|---|
| Execution journal | Retain shared offset index and bounded staged append; `test_result_index.py::test_journal_index_point_target_and_references`, `test_journal_record_limits_preserve_committed_records_and_stop_writer`, `test_journal_disk_bound_fails_before_appending`, `test_journal_index_missing_file_preserves_empty_legacy_view` | Latest summary/source-row metadata remains materialized; partial final journal line is not a completed event |
| Backup metadata recovery | Retain metadata-only spool; `test_configuration_backup.py::test_offline_failed_backup_recovery_is_atomic_and_contains_no_configuration` | Cannot reconstruct missing raw captures or resume interrupted networking |
| Inventory | Retain stable canonical inventory and public contexts tuple; `test_inventory_refresh.py::test_1500_inventory_attempts_stream_at_concurrency_five`, `test_operator_command_full_export_and_recoverable_failure` | Catalogue memory scales with identity count; not an unbounded catalogue migration |
| Manual Configuration | Retain bounded source metadata, disk transcripts and no replay; `test_manual_configuration.py::test_group_block_journal_precedes_save_and_recovers_pending`, `test_group_journal_failure_prevents_save_and_closes`, `test_report_write_failure_retains_offline_recovery` | Existing row/command caps remain; no reconnect/resume after writes |
| Transport | Retain device-owned sessions and bounded responses; shared CLI, transport, lifecycle, Manual and execution suites | Synthetic/mocked networking; native Windows and owner live checks pending |
| Shared compatibility APIs | Retain `BulkPlan.content`, `to_dict`, public execution summary, runner no-sink list and inventory tuple contracts; existing plan/execution/inventory/runner suites | Explicit callers materialize their requested public values; internal evidence pipeline uses indexes. No universal constant-memory API claim |
| Plan output publication | Retain filenames, contents and exclusive links; new `test_orphan_publication_detected_and_fresh_destination_retry`, existing `test_second_publication_failure_removes_own_json_only` | Two-name crash atomicity is not claimed. Same destination rejects even one existing filename; fresh destination retry is read-only |
| Scratch lifecycle | Explicit failure cleanup; new retained-traceback tests in indexed-pipeline/recovery suites cover malformed/trailing JSON, result tamper, digest tamper, construction/build/validation and export disk failure | A successful returned plan owns its indexes until its consumers release it; crash scratch cleanup is OS/operator controlled |
| Observation trust | Existing `test_invalid_observation_schema_never_reaches_scratch_values`, `test_untrusted_result_strings_never_enter_scratch_sqlite`, unsafe-evidence regression retained | Complete validation precedes insertion; supplied results are hashes until reevaluation; no freshness/source-binding relaxation |

**Historical capacity decision remains open:** retain rejection above the finite
256 MiB historical envelope allowance, or commission a separately approved
capacity design. One decoded record and serialization/SQLite copies can consume
several times encoded size; raising limits expands memory exhaustion exposure.
The tested 65 MiB legacy case measured ~274 MB Python allocations. New records
remain bounded at 64 MiB, input at 64 GiB. Larger legacy originals remain untouched;
no universal backward compatibility, implicit splitting or trusted source binding
is claimed. The owner was asked explicitly; no acceptance is inferred.

**Full-suite environment:** writable roots are the checkout and `/tmp`; `/tmp/.git`
is an ancestor marker. `/var/tmp` is outside authorized writable roots. A safe
owner-host run therefore remains required; neither marker nor safety guard was
changed. Linux/Windows temp placement, PYTHONPATH, XML command and success criteria
are in the planning guide's fifth-review instructions. Owner/private-spool,
actual-device and native Windows results remain pending. Automated network
execution is mocked. Actual final-source commands/results follow below.

### Fifth-review targeted validation

- A failing SQL-parameter regression demonstrated nested `results` keys could
  persist an observation child before the containing observation validator ran.
  The reader now indexes only direct working-document/public-plan members.
  `test_nested_index_names_do_not_persist_before_observation_validation` covers
  both reserved names; the demonstrated result case failed before the fix.
- Final-source command:
  `PYTHONPATH=src python -m pytest tests/test_configuration_indexed_pipeline.py tests/test_configuration_recovery.py -k 'not full_recovery' -q`:
  **49 passed / 0 failed / 3 deselected**, 5.05 seconds. The three deselected cases
  are the 88/500/1,500 full pipelines included in the full-suite gate below.
- Giant-file error experiment:
  `PYTHONPATH=src:tests python /tmp/issue162-giant-load-failure.py` passed again
  against final source. The worker-only script saves a **34,607,182-byte** plan
  containing one sanitized Catalyst observation with 33 MiB of synthetic evidence,
  closes the original plan, changes only the digest to zeros, and loads it with
  scratch directories redirected to an empty temporary folder. It retains the
  `PlanError`/traceback and asserts `plan digest mismatch` and **zero scratch
  entries**. This is an explicit experiment, not a pytest count or universal
  memory assertion. Permanent small-fixture tests cover the same cleanup paths.
- The audited-module command below passed **1,415 / 0 failed / 0 skipped /
  0 errors**, 165.15 seconds. This completed focused run precedes the final
  successful-parser ownership-list clear; every selected module is included
  again in the final-source full suite. XML/log: `/tmp/issue162-fifth-final-modules.*`
  (worker-only artifacts).

```bash
PYTHONPATH=src python -m pytest tests/test_configuration_recovery.py tests/test_result_spool.py tests/test_result_index.py tests/test_bulk_configuration_v2.py tests/test_device_execution.py tests/test_device_reporting.py tests/test_inventory_refresh.py tests/test_vlan_compliance.py tests/test_mac_lookup.py tests/test_configuration_backup.py tests/test_manual_configuration.py tests/test_configuration_execution.py tests/test_configuration_execution_evc.py tests/test_configuration_plans.py tests/test_transport.py tests/test_logging.py tests/test_operations_console.py -q -o junit_family=legacy --junitxml=/tmp/issue162-fifth-final-modules.xml
```

Four earlier full-suite starts were interrupted (exit 130) while hardening source;
none is a completed gate. The authoritative final-source result follows below.

### Authoritative fifth-review full-suite result — 2026-10-28

```bash
PYTHONPATH=src python -m pytest -q -o junit_family=legacy --junitxml=/tmp/issue162-fifth-complete.xml
```

**3,837 passed / 25 failed / 0 skipped / 0 errors**, 1,004.99 seconds; exit 1.
The XML contains 3,862 tests. Log: `/tmp/issue162-fifth-complete.log`; these are
worker-only artifacts, with permanent findings recorded here. This is **not a
green full-suite gate**. Compared programmatically with the previous final-source
`/tmp/issue162-prepersist-full.xml`, the failed test IDs are **exactly equal**,
with no new failing IDs: seven Codex-runner, 17 controller and one lifecycle case.

Failure triage: 17 failures directly contain `OS temporary directory must be
outside Git worktrees`. Eight are downstream assertions of that early rejection:
`test_pytest_uses_external_basetemp_and_cleans_on_exit[1]` catches the guard error
before the fake subprocess populates `captured['temp']`, then raises KeyError;
seven `test_lifecycle_after_tests[True-*]` cases see `codex-failed` before the
mocked `codex` stage and fail their expected event sequence. Source confirms
`codex_runner.run_tests` enters `controller_temp` before subprocess invocation,
and `controller.process_one` enters it before the mocked Codex stage. The managed
root remains beneath `/tmp/.git`. No guard, Git marker or permissions were changed.
A controller-safe **owner-host passing run remains required** before recommendation.

All three full-pipeline cases passed, including complete public JSON above
32 MiB, XLSX export/load, protected review, decisions, preparation and mocked
confirmation/replay. Final-source peak Python allocations:

| Targets | Peak Python bytes | Assertion |
|---|---:|---|
| 88 (~79 MB synthetic observations) | 16,871,804 | <96 MiB |
| 500 | 20,227,621 | <96 MiB |
| 1,500 | 37,199,492 | <96 MiB |

These are Python allocation measurements from the final suite, **not new RSS or
actual-device measurements**. Previous fresh-process Linux RSS measurements remain
qualified to their recorded source. All audited module suites are included in
this run. The 12 additional passing test cases cover parser/plan/export resource
failure paths, nested-name pre-persistence validation and orphan-publication retry.
No device writes, private captures, Git/GitHub lifecycle actions or merge occurred.

Final `git diff --check` and changed Markdown local-file links passed. Remaining
owner gates: controller-safe green Linux full suite, native Windows, private-spool
and actual-device/read-only validation, and the explicit historical >256 MiB
capacity decision. Two-name crash atomicity remains unsupported; fresh-destination
retry is documented and tested. Atlas acceptance and merge approval are not claimed.


## Fresh-collection contract revision (2026-10-31)

Scope: owner-approved same-Issue revision; audit normal input/collection versus
explicit historical consumption. No verified application caching gap was found;
retain implementation and add deterministic regression evidence. This table
supplements the whole-module collection/memory/persistence matrix above.

| Workflow | Authoritative input and fresh path retained | Historical/failure behavior and regression evidence |
|---|---|---|
| Interface/VLAN and VLAN database | scripts/device_interface_vlan_report.py:main -> load_targets -> reporting.run_report; ResultSpool.create and execute_devices on every call; worker constructs services, connects and collects | export_report_spool takes an explicit path. test_run_freshness.py::test_interface_vlan_excel_runs_collect_again covers real workbook reload, unchanged bytes/headers, distinct run IDs/timestamps, second success/failure, no prior rows on failure and offline export without connections |
| Compliance and optional methodology/database outputs | scripts/device_vlan_compliance.py:main -> load_targets -> run_compliance -> collect_compliance; new spool, fresh connection and capability calls. Optional methodology is a projection of this same requested collection | test_run_freshness.py::test_compliance_runs_do_not_borrow_prior_success; test_vlan_compliance.py::test_report_failure_recovery_never_recollects and test_explicit_methodology_report_exports_and_recovers preserve offline retry and output contract |
| MAC search/VLAN report | mac_cli.main loads Excel, validates selections, then run_lookup creates a new spool and executes collect_device per target | Explicit export action branches before profile/network loading. test_run_freshness.py::test_mac_runs_and_explicit_export_are_separate proves second invocation, failed-current empty rows, run isolation and historical export; test_mac_lookup.py covers seven-column output/description and CLI offline branch |
| Inventory refresh | refresh_inventory_from_excel calls load_targets, creates spool and executes connect/resolve; inventory/resolver.py:resolve probes show/display version and chassis/inventory before store.reconcile | Deliberate latest-known stable inventory export remains authoritative inventory behavior. test_run_freshness.py::test_inventory_failed_refresh_labels_retained_facts proves fresh attempt, failed status and separate last-success/attempt times; test_inventory_refresh.py covers input selection/order/validation and retained-view recovery |
| Planning v2 | configuration/v2/cli.py:main reads input workbook and credential workbook before observation.collect; collect binds workbook/request digests before executing new workers | Extended test_bulk_configuration_v2.py::test_shared_live_collection_one_session_and_read_only_commands proves identical requests/binding create a different run, both IPs are retried, historical success stays intact, current failed evidence remains unavailable. Existing workbook-order, all-template roundtrip and credential-precedence tests retained |
| Planning recovery/review | recovery.recover reads specifically selected workbook/spool under lease, verifies task/completeness/order/binding/identity/age; workbook review reads immutable artifacts | test_configuration_recovery.py covers no-network idempotent export, wrong workbook, stale/future evidence, legacy diagnostic trust, failed target and publication failure. No recollection fallback exists |
| V1/predefined prepare/confirm | V1 is explicitly offline metadata planning. configuration/execution.py consumes selected immutable source and enforces its current fresh confirmation/identity/backup gates | test_configuration_plans.py and test_configuration_execution*.py retain historical compatibility, source digest, replay, failed checks and confirmation behavior; no cached operational observations added |
| Manual Configuration | configuration/manual.py:load_rows preserves Excel; execute creates a new run, spool and worker-owned live session per selected group | regenerate_report reads the explicit journal/run without executing commands. test_manual_configuration.py retains workbook grouping/order, password/confirmation gates, backup and no-replay recovery |
| Configuration backup | scripts/device_configuration_backup.py shared Excel loader; configuration_backup.run_backup creates BackupWriter and per-run .processing spool then connects per target | recover_failed_devices only regenerates failure output. test_configuration_backup.py::test_entry_point_uses_shared_excel_loader and test_offline_failed_backup_recovery_is_atomic_and_contains_no_configuration retained |
| Shared processing, transport, console, logging | ResultSpool.create collision-resistant directory; record run IDs validated by leased index; indexed_json scratch stores owned by current processing objects; DeviceInventoryResolver probes devices instead of returning cached observations | test_result_spool.py/test_result_index.py retain cross-run validation, corruption, bounds, cleanup/concurrency; transport/console/logging suites retain sessions, menus, sanitation and output behavior. No normal entry point searches prior run directories for observations |

No input schema, output columns, public signature/default, menu or device command
was changed. Excel remains authoritative for Excel-driven user input; there is no
Web GUI prerequisite or database-table input. Run-isolated SQLite indexes are
internal and disposable; durable spool/recovery and canonical inventory remain as
previously documented. Historical capacity limits and controller temp-root guards
were retained.

### Owner validation for this revision

Linux: `PYTHONPATH=src python -m pytest tests/test_run_freshness.py tests/test_bulk_configuration_v2.py tests/test_configuration_recovery.py -q`

Windows PowerShell:

```powershell
$env:PYTHONPATH = (Join-Path (Get-Location) 'src')
python -m pytest tests/test_run_freshness.py tests/test_bulk_configuration_v2.py tests/test_configuration_recovery.py -q
python -m pytest -q
```

Linux full gate: `PYTHONPATH=src python -m pytest -q`.
Run from the checked-out revision with installed dependencies. All tests use
synthetic evidence/mocked devices; the full gate includes prior 88/~79 MB, 500 and
1,500 target pipelines and finite oversized-record checks. No limit was raised.

Owner-only read-only validation: use the existing manual's normal Excel invocation
for each selected report twice, with the same approved device rows. Record each
reported spool run ID, evidence time and collection/session attempt. Run IDs must
be different and each target must be attempted again. In an operator-controlled
lab, make one target unreachable for the second execution: require its current
error/missing evidence, with no prior interface/VLAN/MAC success substituted.
Inventory may retain stable facts only with failed-with-previous-data-retained and
its original successful collection time. Compare original workbook and report
sheets/columns/order to the existing manual. Separately use the documented explicit
offline export/recovery syntax for a selected retained run to a new basename, with
network access unavailable: require complete historical output or the documented
binding/age/trust error, never a connection attempt. Review a selected immutable
plan without confirming execution. Keep private captures outside this checkout;
record metadata only. Actual-device, private-spool and owner-host Linux validation
remain pending; this revision authorizes no live/device writes.


Windows validation exposed a verified scratch-lifecycle gap: cyclic garbage
collection could finalize TemporaryDirectory before its SQLite connection closed.
IndexedJSON now registers an ordered weakref finalizer that holds scratch alive,
closes the connection, then removes the directory. Explicit close remains idempotent
and permits cleanup retry after failure. No persistence, input or output format
changed. test_result_index.py::test_indexed_json_cyclic_gc_closes_connection_before_scratch_cleanup
asserts this order on every OS, including platforms that allow unlinking open files.


A second Windows lifecycle failure was reproduced by the existing
`test_consumption_reuses_one_index_across_tables_and_clears_after_failure`:
a consumer traceback retained a suspended records iterator and its SQLite cursor,
so connection close alone did not release order.sqlite. ResultIndex now fetches
at most 256 offsets using position-keyed batches and closes each cursor before
yielding. Record order, point/batch/target access and authoritative JSONL stay
unchanged; no full-run offset list is created. Journal indexes reuse this reader.


Windows backup tests additionally reproduced WinError 206 beneath nested UUID run
names. A shorter authorized pytest base alone was insufficient. run_backup now
uses the existing ResultSpool short_name option for its private .processing child
(timestamp with atomic numeric collision suffix). Public backup run/capture paths,
failed_devices.xlsx, folder hierarchy and recovery API remain unchanged. All
111 backup tests pass with this fix; shared short-name collision tests retain
concurrent/repeated-run isolation. This is a bounded internal naming adjustment,
not an output-path migration. Other spool names/defaults are unchanged.


### Revision automated evidence (Windows worker)

- `PYTHONPATH=src python -m pytest tests/test_result_index.py::test_indexed_json_cyclic_gc_closes_connection_before_scratch_cleanup tests/test_run_freshness.py tests/test_bulk_configuration_v2.py tests/test_configuration_recovery.py -q`: **188 passed / 0 failed / 0 skipped**, 85.87 seconds, no warnings. This run preceded the later ResultIndex cursor and backup short-name fixes, which do not change planning input/collection behavior.
- `PYTHONPATH=src python -m pytest tests/test_result_index.py tests/test_result_spool.py -q --basetemp=<authorized-temp>/index -o junit_family=legacy --junitxml=<authorized-temp>/issue162-freshness-index.xml`: **63 passed / 0 failed / 0 skipped**, 56.94 seconds, final storage source.
- `PYTHONPATH=src python -m pytest tests/test_configuration_backup.py -q --basetemp=<authorized-temp>/b2`: **111 passed / 0 failed / 0 skipped**, 7.82 seconds, final backup source.

Here PYTHONPATH is set with `$env:PYTHONPATH='src'` in PowerShell. Temporary XML/log
artifacts contain only synthetic test evidence and are not committed. Short pytest
bases stay inside the controller-provided authorized temp root. Initial exploratory
runs were interrupted after reproducing Windows lifecycle/path failures; they are
not claimed as completed full-suite runs. The final-source whole-suite result follows.


Completed first final-source Windows full suite:
`$env:PYTHONPATH='src'; python -m pytest -q --basetemp="$env:TEMP/final" -o junit_family=legacy --junitxml="$env:TEMP/issue162-freshness-full-final.xml"`
returned **3,867 passed / 2 failed / 2 errors / 0 skipped**, 1,885.87 seconds.
All three scale pipelines and controller tests passed. The Manual Configuration
failures were test portability defects: native XML fixture writing transformed
CRLF, a file-URI assertion decoded a Windows drive path as POSIX, and an oversized
parameter ID exceeded Windows' environment-variable limit during setup/teardown.
Fixtures now write literal CRLF with XML carriage references, decode file URIs
with url2pathname, and use short deterministic case IDs. Source diagnostics,
line-number assertions, confirmation and command execution were not weakened.
All seven affected targeted cases pass. A full gate with these corrected tests
is rerun below; this first run is not represented as green.

First complete run pipeline peak Python bytes: **10,686,033** (88/~79 MB),
**9,909,512** (500), **26,438,730** (1,500), each below 96 MiB. XLSX writer peaks:
5,707,143 / 5,903,785 / 6,340,972 bytes. Shared-index peaks:
3,860,253 / 936,289 / 1,160,913 bytes. These are Python allocations on Windows,
not RSS or private/live-device measurements.


### Final green revision gate (2026-10-31)

```powershell
$env:PYTHONPATH = 'src'
python -m pytest -q --basetemp="$env:TEMP/green" -o junit_family=legacy --junitxml="$env:TEMP/issue162-freshness-green.xml"
```

**3,870 passed / 0 failed / 0 errors / 0 skipped**, 1,828.45 seconds (30m28s),
exit code 0, no warnings. This is the complete repository deterministic suite on
native Windows, including every audited module, the eight added regression cases,
corrected Manual Configuration portability fixtures, prior historical-artifact,
security/approval/replay tests and all controller tests. No guard was weakened.
The test base is a dedicated child of the authorized controller temp root, not a
production or repository data directory. XML/log files remain worker-only artifacts.

Final-source measured Python allocation peaks:

| Targets | Complete pipeline bytes | XLSX writer bytes | Shared spool index bytes |
|---|---:|---:|---:|
| 88 (~79 MB pipeline observations) | 10,688,863 | 5,708,193 | 3,865,198 |
| 500 | 9,909,794 | 5,903,986 | 934,659 |
| 1,500 | 26,441,712 | 6,340,583 | 1,160,138 |

Pipeline assertions remain <96 MiB; index assertions remain <16 MiB. Large-record
serialization peak is 707,827 bytes. The complete pipeline checks >32 MiB JSON,
public shapes/order/proposals/dependencies/decisions, protected workbook review,
digests, source load, preparation, mocked confirmation and replay rejection.
These are tracemalloc allocation measurements, not RSS or actual-device evidence.

The prior 25 controller temp-root failures do not reproduce on this Windows host;
all controller tests pass with the original guard. A controller-safe owner Linux
full-suite run remains pending, rather than inferred from Windows success.
Private-spool and actual-device/read-only validation, historical >256 MiB capacity
acceptance and two-name crash-atomic publication limitations remain as documented.
No private captures, production operations, Git/GitHub lifecycle changes or merge.
