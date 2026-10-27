# Issue #162 processing audit and validation ledger

This is an implementation audit for review, **not Issue acceptance**. The shared
spool increment is implemented; end-to-end large-plan processing remains
unfinished. Offline recovery retains the existing aggregate limits. The third-review
increment streams worksheet cells, while full-plan decoding remains aggregate. No production captures or devices were used.
The owner's private workbook/spool are unavailable and are not needed for synthetic
validation. No historical source-workbook association can be reconstructed.

Paths below are relative to `src/orbitflow/`; test paths are relative to `tests/`.
All listed automated tests are offline. The full-suite ledger below distinguishes
repository-wide regression checks from newly added scalability assertions.

| Workflow / source | Collection and memory | Persistence / consumption / output / recovery | Decision and remaining risks | Regression coverage |
|---|---|---|---|---|
| Shared runner `execution.py` | Bounded device futures; sink mode retains only in-flight payloads; no-sink mode returns full list | Caller-owned sink; per-device cleanup and failure isolation | Retain scheduler. No-sink callers require explicit audit, not a global behavior change | `test_device_execution.py`, `test_result_spool.py` |
| Shared spool `result_spool.py` | One owner appends sanitized envelopes; input-position metadata retained | Authoritative JSONL + manifest; temporary SQLite offsets; partial recovery opt-in; lease-controlled cleanup | Implement reusable index, point/target/256-position batch retrieval, one index per consumption, explicit 64 MiB envelope/64 GiB spool limits (second-review increment; see below), envelope checks, fsync before checkpoint; scratch index is disposable | `test_result_spool.py`, `test_result_index.py` |
| Planning v1 `configuration/plans.py`, `approvals.py` | Offline request and inventory snapshots materialized | Closed-schema canonical JSON; signed SQLite authority | Retain authorization semantics. Full-plan serialization is **not yet migrated** | `test_configuration_plans.py` |
| Planning v2 observation `configuration/v2/observation.py` | Shared per-device workers; normalized evidence in one payload per device | Shared spool; `bounded_observations` still builds aggregate dictionary | Implement pre-network request/workbook digest metadata. **16 MiB aggregate observation gate remains**; limited offline recovery is available; see revision section | `test_bulk_configuration_v2.py`, binding test in `test_result_index.py` |
| Planning v2 build/validation `configuration/v2/planning.py` | All observations, requests, projected rows/results materialized; same-device prior rows retain dependencies/conflicts | Immutable string content; canonical digest; re-evaluation detects tamper | **Unfinished:** replace aggregate planning/validation with disk-backed intermediates without changing order, projections, schema or safety. 32 MiB plan gate remains | `test_bulk_configuration_v2.py`, `test_configuration_v2_approved_services.py` |
| Planning review/XLSX `configuration/v2/workbook.py` | Write-only worksheet cells; full decoded plan remains in memory; review regenerates expected workbook using the streaming writer | Existing sheets/columns/presentation; exact protected-cell comparison and digest; ordinary writer scratch cleanup | Implemented worksheet streaming in third review. **Unfinished:** full-plan decode and per-request evidence aggregation; protected comparison uses read-only iterators | Same v2 suites; `test_configuration_streaming_workbook.py`; `test_operations_console.py` |
| Confirmed execution prepare/confirm `configuration/execution.py` | Full plan decoded and copied into confirmation payload; selected/skipped rows materialized | Transactional SQLite replay claims; summary JSON; journal and spool; separate explicit confirmation | Retain write/backup/verify/save gates. **Unfinished:** bounded confirmation preparation/load; never infer execution authority from recovery | `test_configuration_execution*.py`, `test_execution_observation_timing.py` |
| Execution report `configuration/execution.py:export_results` | Write-only workbook; full summary plus per-row event-offset maps and repeated journal scans | Offline journal-based reconstruction; detailed evidence retained | Retain output contract; **unfinished:** indexed event reduction and bounded summary consumption | Execution and performance suites |
| Manual Configuration `configuration/manual.py` | One session/shell per IP group; input rows grouped in memory; device-local transcripts | fsynced events, shared outcomes, write-only consolidated workbook; offline journal recovery | Preserve no-replay and successful-group-only automatic save. Report still aggregates all bounded input metadata/results; **not migrated to indexed journal processing** | `test_manual_configuration.py` |
| Inventory refresh `inventory_refresh.py`, `inventory.py` | Shared workers; per-device outcomes; status map and canonical inventory in memory | Shared spool; captured snapshot JSONL; write-only atomic workbook; offline captured-view export | Retain correct streaming export; inherits shared index reuse. Canonical JSON inventory and full status map remain separate memory risks; no format migration claimed | `test_inventory_refresh.py`, `test_device_inventory.py`, `test_inventory_atomic_replace.py` |
| Interface/VLAN and database report `reporting.py` | Shared workers; per-device normalized rows/evidence; no full-run report rows | Shared spool; table generators; evidence-reference overflow; atomic workbook; offline export | Retain per-device normalization and streaming workbook. Inherits one validated index across all passes. Oversized individual device now fails explicitly and retains incomplete spool | `test_device_reporting.py`, `test_aggregation.py`, `test_aggregation_consumers.py`, `test_aggregation_owner_revision.py` |
| VLAN compliance/database `vlan_compliance.py`, `compliance_report.py`, `methodology_report.py` | Single-device audit resolvers; shared worker sink | Findings/error spool; multi-pass streaming tables; complete overflow detail; retained-spool retry | Retain family audit ownership and output schemas; index reuse removes repeated SQLite builds. Per-device finding/evidence payload is still the unit of memory | `test_vlan_compliance.py`, `test_vlan_configuration_audit.py`, `test_methodology*.py` |
| MAC observation/report `mac_lookup.py` | Shared workers; device-local MAC/BD snapshots | Shared spool; write-only tables and offline retained-spool export | Retain normalized lookup ownership and seven-column main sheet; inherits shared index reuse. Single-device table size remains bounded only at spool write, after collection | `test_mac_lookup.py` |
| Configuration backup `configuration_backup.py` | Workers own captures and immediately write protected files; outcome holds safe failure metadata | Separate protected capture files; caller streams failure workbook | Retain raw sensitive captures outside generic spool. Failure metadata workbook has no durable reconstruction source: **unfinished recovery audit gap**. Never insert raw config into SQLite | `test_configuration_backup.py` |
| Transport/CLI `transport/`, `vendors/common.py` | Device-owned sessions/channels and receive buffers | No shared full-run payload storage | Retain connectivity/setup/cleanup. Spool limit does not bound buffers during live collection; **individual receive-size audit remains unfinished** | `test_transport*.py`, `test_shared_cli.py`, `test_cisco_ios_cli.py`, `test_cli_lifecycle.py` |
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

The optional planning-recovery CLI/API is documented in the [planning manual](../user_manual/bulk-configuration-planning.md#offline-retained-observation-recovery-issue-162-revision); aggregate planning limits still apply.
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
