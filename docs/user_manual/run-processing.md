# Run processing, recovery and timing (Issue #162)

Existing Excel inputs, CLI arguments, menu flows and public report formats stay
unchanged. A normal report always performs its own collection; a failed target
never borrows an observation from a previous run. There is no database input UI.

New internal run evidence is stored in `r.db` inside the workflow's
existing run directory. `ResultSpool.create(root, task, target_count, *, clean=sanitize_text,
short_name=False)` retains its arguments/defaults. `manifest.json` is a compatibility
checkpoint; SQLite metadata is authoritative for new runs. Tables contain ordered
result envelopes, inventory export projections and execution journal events.
Canonical inventory JSON, immutable plans, signed approval databases, protected
configuration captures/transcripts and public XLSX/JSON/text outputs retain their
existing contracts and locations. No raw backups belong in these new tables.

The central completion sink commits each sanitized outcome and its count metadata
in one SQLite transaction. Worker event recording and result checkpoints share a
run-scoped writer lock. Each run has independent evidence and UTC timestamps.
SQLite uses a bounded cache and file-backed temporary storage. Report queries
fetch at most 256 identifiers, then one bounded payload at a time, in input order.
New runs do not create an authoritative JSONL spool or rebuild an offset index.
Legacy JSONL results/events remain readable without converting the original files.

## Offline inspection and re-export

Use the existing report-specific export API/CLI from its individual manual with
an explicitly selected retained run and a new output destination. No device
collection or configuration replay occurs. Planning recovery still checks workbook
binding, identity and evidence age. Legacy unbound diagnostic evidence never
becomes a trusted source for new execution authorization. See the
[planning recovery syntax](bulk-configuration-planning.md#offline-retained-observation-recovery-issue-162-revision).

A metadata-only inspection works on Linux and Windows:

```python
from orbitflow.result_spool import ResultSpool
run = ResultSpool('OWNER_SELECTED_RETAINED_RUN')
print(run.manifest['run_id'], run.manifest['status'])
with run.indexed() as records:
    print(len(records))
    for record in records.records(positions=[1]):
        print(record['input_position'], record['status'])
```

Do not print private payloads in shared logs. A complete selected run produces
ordered historical records. Incomplete collection requires the existing explicit
`allow_partial=True` API option; normal report consumption rejects it. Corrupt or
missing databases fail rather than reconnecting. A database transaction rolls back
an interrupted uncommitted insert; committed results remain available. A crash can
leave `collecting` metadata, which is deliberately not promoted to complete.
Do not retry a failed append: a transaction may already have committed before a
manifest-mirror error. Offline export is retryable; collection is never replayed.
Permission/disk-full failures retain the run and propagate the original failure.
Recovery needs writable run-directory space for existing lifecycle/lease handling.

Successful consumed runs follow existing cleanup flags; failed/interrupted runs
remain retained. `cleanup_stale_runs(root, *, before=<aware UTC datetime>)` is the
existing explicit cleanup API. It honors leases and rejects links/unknown files.
No automatic destructive retention policy or cross-run observation cache is added.
Keep each retained directory intact, including SQLite rollback files after a crash;
do not copy just a live database while a writer is active. Filesystem power-loss
and two-public-filename crash atomicity remain outside the existing guarantees.

## Stage logs

Timing records use existing rotating module log infrastructure under
`outputs/logs/<module>/<UTC date>/`; supplied workflow log roots still apply.
`run_stages.log` records durable collection, SQLite insert/commit and retrieval,
and report-generation/publication boundaries. Function-boundary records in module
logs cover total workflows, input loading, planning/evaluation and rendering.
Each `stage_start`/`stage_end` pair carries an invocation `run_id`, `workflow`, `stage`, UTC
`started_at` and (on end) `ended_at`, monotonic `elapsed_seconds` and `status`.
Durations include nested child stages and **must not be summed**. Per-device wall
times can overlap under parallel execution; summed device time is not collection
wall time. No command response, credential, SQL parameter or exception text is
included. Failures/interruption also produce end records. Partial durable runs
have `status=partial` where failed counts are available.

Sanitized example fields (one JSON log record):

```json
{"message":"stage_end","run_id":"synthetic-run","workflow":"vlan_compliance","stage":"report_generation_publication","started_at":"2026-10-31T00:00:00+00:00","ended_at":"2026-10-31T00:00:01+00:00","elapsed_seconds":"1.0","status":"success"}
```

Collection and report publication have separate boundaries, allowing the owner to
locate post-collection delays. These timings are diagnostic, not a speed target.
Owner/device timing, private captures and Linux live validation remain pending.

## Automated and owner validation

Linux (dependencies installed, repository root):

```bash
PYTHONPATH=src python -m pytest tests/test_direct_sqlite.py tests/test_run_freshness.py tests/test_configuration_recovery.py -q
PYTHONPATH=src python -m pytest -q
```

Windows PowerShell:

```powershell
$env:PYTHONPATH = (Join-Path (Get-Location) 'src')
python -m pytest tests/test_direct_sqlite.py tests/test_run_freshness.py tests/test_configuration_recovery.py -q
python -m pytest -q
```

Expected: deterministic tests pass, including 88/~77 MB, 500 and 1,500-target
bounded-memory checks and existing complete planning pipelines. No elapsed-time
threshold is required. Check the audit ledger for actual worker results.

Owner-only validation: invoke each approved read-only report twice using its
existing manual commands and Excel input. Compare columns/order and distinct run
IDs, require a fresh collection each time, and inspect separate collection and
rendering stage records. Make one lab target unreachable in the second run and
require a current failure without historical substitution. Select a retained run
for explicit offline export with networking unavailable; require historical output
or the documented trust/age/completeness error, with no connection attempts.
Never run configuration execution merely to validate report regeneration. Owner
controls all actual-device/private-spool validation and merge decisions.


### Standalone inventory batch validation

`live_validate_inventory_batch.run_batch_validation(...)` retains its existing
Python return dictionary/list contract (explicit materialization for API callers).
The direct CLI uses ordered SQLite queries to stream its unchanged JSON schema.
Internal runs live under `outputs/runs/inventory_validation/`; failed output
publication retains them. To regenerate the JSON from a specifically selected
complete run, without networking, use this supported optional Python entry point:

```python
from scripts.live_validate_inventory_batch import export_validation_spool
export_validation_spool('OWNER_SELECTED_RETAINED_RUN', 'NEW_HISTORICAL_OUTPUT.json', cleanup=False)
```

Signature: `export_validation_spool(spool_path, results_path, *, cleanup=True)`;
returns the output `Path`. Wrong workflow or incomplete collection raises
`ValueError`; corrupt/missing SQLite fails explicitly. It preserves the original
collection time, success/failure counts and ordered results. Atomic replacement
preserves an existing output on rendering failure. `cleanup=False` retains the
selected run for further offline review; default successful cleanup removes it.
No new console action or live invocation is required.


Timing `run_id` identifies the processing invocation. Durable stages also include
`evidence_run_id`, the canonical retained directory/manifest identity. Normally
these agree; existing Manual Configuration/backup timestamp/numeric folder names
are preserved, and historical exports deliberately identify both the new offline
invocation and its selected original evidence. Neither field contains device data.

The short `r.db` basename keeps SQLite rollback-journal filenames within the legacy manifest/JSONL filename budget on Windows. Earlier direct stores named `results.sqlite` remain readable. This does not enable arbitrary OS paths beyond existing Windows limits.


Public preparation/confirmation APIs and offline export APIs include outer timing
records, including failures before device work. Shared Excel rendering has its
own boundary. Per-device device_processing_total includes all work on that device,
including approved execution where applicable; it is not pure connection time.
Device-outcome completed_count is included only by its owning result-store handle;
journal-only handles omit unavailable counters. Insert/commit end counts reflect
the completed transaction. Target-index/record disagreement is an explicit
corruption error, never silently assigned to another device or workbook row.


If successful output cleanup deletes the database but Windows denies final
directory removal, `manifest.json` becomes a cleanup-only tombstone. Reopening
that directory supports `remove()` retry; it cannot export records, restart
collection or authorize execution. This is the small lifecycle-metadata exception
to SQLite authority after data has intentionally been removed.

Execution-report XLSX publication is exclusive and atomic on the supported local
filesystem: failed rendering/save does not publish a partial destination, an
existing or racing destination is preserved, and offline retry uses retained
source evidence without reconnecting. Owned temporary XML/archive files are
closed and cleaned on success or failure. Filesystem power-loss and multi-file
publication limitations above still apply.

Planning recovery reports invalid/missing/corrupt retained storage as `PlanError`, preserving the planning API error contract. It publishes no plan, performs no network collection and does not relax workbook-binding, identity or age checks.
