# Execution-result spool

`orbitflow.result_spool.ResultSpool` owns persisted run outcomes. Workers return
normalized results; the shared runner's `on_outcome` callback executes on the
caller as workers finish and does not retain a full result list. Existing callers
without a sink still receive input-ordered lists.

Each run has a timestamp/UUID directory containing `manifest.json` and append-only
`results.jsonl`. The versioned manifest records task, run identity, target,
completed and failed counts, timestamps, collection completeness and lifecycle
state. Envelopes contain run ID, input position, safe target identity, status,
completion time, error category and a task-specific JSON payload. The spool does
not interpret payload fields. Callers supply normalized data and a sanitizer that
redacts their runtime credentials; sanitization runs recursively before persistence.
Never pass raw CLI output, credentials or exception objects as payloads.

Only the collection owner appends. JSONL is flushed before manifest progress is
atomically replaced. An interrupted final partial line is omitted during explicit
partial recovery. A completed spool with corrupt, duplicate or missing records
fails consumption and remains retained. This is process-interruption recovery,
not a power-loss durability guarantee.

Completion order is persisted; consumers read input order through a temporary,
bounded-cache SQLite offset index. Only one target payload is decoded at a time.
The index is disposable; JSONL is authoritative. Per-target result size, input
credentials and canonical inventory still occupy memory; this change bounds
full-run report/attempt aggregation, not the existing inventory-store format.

## Workflow consumers

Interface/VLAN reporting defaults to `<reports_dir>/runs`; inventory refresh
defaults to `<export_parent>/runs`. Both accept `spool_root` to choose another
location. Reporting prints its run path and inventory logs its path. Failed runs
can also be found by inspecting these directories' manifests.

Report payloads hold interface, VLAN database and error rows. Inventory payloads
hold identity membership/status updates and each attempt. Inventory also writes
`snapshot.jsonl`: the sanitized export view at collection completion, including
omitted canonical devices. It is a run artifact, never a replacement inventory
store. Input-ordered status reduction preserves last-attempt semantics; canonical
reconciliation remains transaction-ordered in the inventory store.

Retry in Python, supplying the retained run directory and destination:

```python
from orbitflow.reporting import export_report_spool
from orbitflow.inventory_refresh import export_inventory_spool

export_report_spool(run_directory, "reports/recovered.xlsx")
# For an inventory_refresh run instead:
export_inventory_spool(run_directory, "reports/recovered_inventory.xlsx")
```

Consumers stream write-only worksheets and publish through a temporary workbook.
Inventory retry uses the captured export view even if canonical inventory has
subsequently changed. Neither retry connects to devices or alters inventory.

## Lifecycle and retention

States: `created` -> `collecting` -> `collected` -> `consuming` -> `consumed`.
Collection errors/interruptions leave `interrupted`; consumer failures leave
`output_failed`. Hard termination may leave `collecting` or `consuming`. OS leases
are released by process exit, so retained runs can be recovered without stale PID
heuristics. A completed collection whose consumer was interrupted can be retried.

Successful consumers remove their run by default; `cleanup=False` retains it.
Failed device outcomes do not prevent successful workbook consumption/cleanup:
they remain represented in the final workbook. A partial collection is never
silently treated as complete. `allow_partial=True` explicitly exports available
outcomes and leaves `partial_consumed` retained. For interrupted inventory runs
without an export snapshot, partial recovery exports attempts with an empty
Inventory sheet; it cannot recreate a missing historical inventory snapshot.

No automatic age-based deletion occurs. An operator can deliberately expire
retained runs with an aware UTC cutoff:

```python
from datetime import datetime, timedelta, timezone
from orbitflow.result_spool import cleanup_stale_runs

removed = cleanup_stale_runs(
    "reports/runs", before=datetime.now(timezone.utc) - timedelta(days=30)
)
```

Cleanup rechecks age under an exclusive OS lease, skips active runs and malformed
or unrelated directories, and refuses links or unexpected files/subdirectories.
The cutoff explicitly authorizes deletion of old failed/incomplete runs too.
Inspect retained artifacts before expiring them. Recognized interrupted
reader scratch files are removed only after validating their names and resolved
paths; unknown contents are preserved. Cleanup never recursively deletes trees. Separate processes must not share an output destination or canonical
inventory store; spool paths themselves are unique across processes.
