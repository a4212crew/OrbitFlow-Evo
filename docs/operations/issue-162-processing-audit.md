# Issue #162 processing audit and validation ledger

This is an implementation audit for review, **not Issue acceptance**. The shared
spool increment is implemented; end-to-end large-plan processing and supported
planning recovery remain unfinished. No production captures or devices were used.
The owner's private workbook/spool are unavailable and are not needed for synthetic
validation. No historical source-workbook association can be reconstructed.

Paths below are relative to `src/orbitflow/`; test paths are relative to `tests/`.
All listed automated tests are offline. The full-suite ledger below distinguishes
repository-wide regression checks from newly added scalability assertions.

| Workflow / source | Collection and memory | Persistence / consumption / output / recovery | Decision and remaining risks | Regression coverage |
|---|---|---|---|---|
| Shared runner `execution.py` | Bounded device futures; sink mode retains only in-flight payloads; no-sink mode returns full list | Caller-owned sink; per-device cleanup and failure isolation | Retain scheduler. No-sink callers require explicit audit, not a global behavior change | `test_device_execution.py`, `test_result_spool.py` |
| Shared spool `result_spool.py` | One owner appends sanitized envelopes; input-position metadata retained | Authoritative JSONL + manifest; temporary SQLite offsets; partial recovery opt-in; lease-controlled cleanup | Implement reusable index, point/target/256-position batch retrieval, one index per consumption, explicit 16 MiB envelope/64 GiB spool limits, envelope checks, fsync before checkpoint; scratch index is disposable | `test_result_spool.py`, `test_result_index.py` |
| Planning v1 `configuration/plans.py`, `approvals.py` | Offline request and inventory snapshots materialized | Closed-schema canonical JSON; signed SQLite authority | Retain authorization semantics. Full-plan serialization is **not yet migrated** | `test_configuration_plans.py` |
| Planning v2 observation `configuration/v2/observation.py` | Shared per-device workers; normalized evidence in one payload per device | Shared spool; `bounded_observations` still builds aggregate dictionary | Implement pre-network request/workbook digest metadata. **16 MiB aggregate observation gate remains**; no supported planning recovery command yet | `test_bulk_configuration_v2.py`, binding test in `test_result_index.py` |
| Planning v2 build/validation `configuration/v2/planning.py` | All observations, requests, projected rows/results materialized; same-device prior rows retain dependencies/conflicts | Immutable string content; canonical digest; re-evaluation detects tamper | **Unfinished:** replace aggregate planning/validation with disk-backed intermediates without changing order, projections, schema or safety. 32 MiB plan gate remains | `test_bulk_configuration_v2.py`, `test_configuration_v2_approved_services.py` |
| Planning review/XLSX `configuration/v2/workbook.py` | Normal workbook plus full plan; review regenerates expected workbook in memory | Existing sheets/columns; exact protected-cell comparison and digest | **Unfinished:** streaming workbook generation/comparison with unchanged protected evidence and workbook structure | Same v2 suites; `test_operations_console.py` |
| Confirmed execution prepare/confirm `configuration/execution.py` | Full plan decoded and copied into confirmation payload; selected/skipped rows materialized | Transactional SQLite replay claims; summary JSON; journal and spool; separate explicit confirmation | Retain write/backup/verify/save gates. **Unfinished:** bounded confirmation preparation/load; never infer execution authority from recovery | `test_configuration_execution*.py`, `test_execution_observation_timing.py` |
| Execution report `configuration/execution.py:export_results` | Write-only workbook; full summary plus per-row event-offset maps and repeated journal scans | Offline journal-based reconstruction; detailed evidence retained | Retain output contract; **unfinished:** indexed event reduction and bounded summary consumption | Execution and performance suites |
| Manual Configuration `configuration/manual.py` | One session/shell per IP group; input rows grouped in memory; device-local transcripts | fsynced events, shared outcomes, write-only consolidated workbook; offline journal recovery | Preserve no-replay and successful-group-only automatic save. Report still aggregates all bounded input metadata/results; **not migrated to indexed journal processing** | `test_manual_configuration.py` |
| Inventory refresh `inventory_refresh.py`, `inventory.py` | Shared workers; per-device outcomes; status map and canonical inventory in memory | Shared spool; captured snapshot JSONL; write-only atomic workbook; offline captured-view export | Retain correct streaming export; inherits shared index reuse. Canonical JSON inventory and full status map remain separate memory risks; no format migration claimed | `test_inventory_refresh.py`, `test_device_inventory.py`, `test_inventory_atomic_replace.py` |
| Interface/VLAN and database report `reporting.py` | Shared workers; per-device normalized rows/evidence; no full-run report rows | Shared spool; table generators; evidence-reference overflow; atomic workbook; offline export | Retain per-device normalization and streaming workbook. Inherits one validated index across all passes. Oversized individual device now fails explicitly and retains incomplete spool | `test_device_reporting.py`, `test_aggregation.py`, `test_aggregation_consumers.py`, `test_aggregation_owner_revision.py` |
| VLAN compliance/database `vlan_compliance.py`, `compliance_report.py`, `methodology_report.py` | Single-device audit resolvers; shared worker sink | Findings/error spool; multi-pass streaming tables; complete overflow detail; retained-spool retry | Retain family audit ownership and output schemas; index reuse removes repeated SQLite builds. Per-device finding/evidence payload is still the unit of memory | `test_vlan_compliance.py`, `test_vlan_configuration_audit.py`, `test_methodology*.py` |
| MAC observation/report `mac_lookup.py` | Shared workers; device-local MAC/BD snapshots | Shared spool; write-only tables and offline retained-spool export | Retain normalized lookup ownership and seven-column main sheet; inherits shared index reuse. Single-device table size remains bounded only at spool write, after collection | `test_mac_lookup.py` |
| Configuration backup `configuration_backup.py` | Workers own captures and immediately write protected files; outcome holds safe failure metadata | Separate protected capture files; caller streams failure workbook | Retain raw sensitive captures outside generic spool. Failure metadata workbook has no durable reconstruction source: **unfinished recovery audit gap**. Never insert raw config into SQLite | `test_configuration_backup.py` |
| Transport/CLI `transport/`, `vendors/common.py` | Device-owned sessions/channels and receive buffers | No shared full-run payload storage | Retain connectivity/setup/cleanup. Spool limit does not bound buffers during live collection; **individual receive-size audit remains unfinished** | `test_transport*.py`, `test_shared_cli.py`, `test_cisco_ios_cli.py`, `test_cli_lifecycle.py` |
| Console/logging `menu.py`, `terminal_progress.py`, `logging/` | Serialized progress, bounded recent activity; module-owned sanitized logging | Existing menu/profile/log paths | Retain presentation and API defaults. No new recovery workflow/menu action introduced in this increment | `test_operations_console.py`, `test_logging.py`, `test_terminal_progress.py`, `test_workflow_progress.py` |
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

No new planning-recovery syntax is supplied because it is **not implemented**.
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
