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

Only the collection owner appends. JSONL is flushed and fsynced before manifest
progress is atomically replaced. The temporary manifest is also flushed and
fsynced before replacement. An interrupted final partial line is omitted during explicit
partial recovery. A completed spool with corrupt, duplicate or missing records
fails consumption and remains retained. Directory rename durability still depends on the host filesystem; this is not
a general power-loss durability guarantee.

Manifest replacement retries only the atomic `manifest.tmp.replace(manifest.json)`
operation on `PermissionError`: four attempts, with 0.1, 0.2 and 0.4 second delays.
It never retries JSONL append, changes permissions, or ignores exhaustion. A
successful JSONL flush/fsync commits the record for process-level recovery even if its
manifest checkpoint fails. A successful file `fsync` and atomic rename do not establish directory-entry
power-loss durability on every supported filesystem. JSONL remains canonical; manifest counts may lag after an
interruption. Explicit consumption validates/streams JSONL under the lease and
reconciles completed/failed counts before checkpointing the consumer state.

A sink failure aborts scheduling and further delivery; already running workers
finish their resource cleanup, but their undelivered outcomes are not committed.
The run is incomplete, never automatically resumed or recollected. The failing
append must not be replayed: it may already have committed. The spool rejects
further appends after a write/flush/checkpoint failure, including when a caller
catches that error. No full-run payload collection is retained in memory.
An interruption checkpoint is best effort and never masks the original error;
if it also fails, the prior manifest and canonical JSONL remain available and
the secondary error is included in sanitised run diagnostics. Recovery still
requires explicit partial-export opt-in while collection is incomplete, and
requires filesystem access to have recovered.

The compliance, inventory refresh and Interface/VLAN CLIs record top-level
application/persistence/export failures through the shared logger at
`outputs/logs/application/YYYY-MM-DD/run_errors.log` (or `--log-root`). This works
outside per-device logging scopes, including policy/input and export failures.
Logs retain categories, errno and repository code locations/exception chains,
not exception messages, source lines, locals or external filesystem paths. The
console stays concise; failure to write diagnostics is explicitly reported.
These run-level errors are distinct from isolated device-stage failures.

Completion order is persisted; consumers read input order through a temporary,
bounded-cache SQLite offset index. A consumption holds one validated index across
all table passes. `ResultSpool.indexed()` exposes the same lease-protected index
for repeated input-position, target and bounded-batch lookup; the context owns its
SQLite connection and deletes scratch state on exit. It is not a second authority.
`index.get(position)` raises `KeyError` if missing;
`index.records(positions=[...], target=None)` yields input order, accepts at most
256 positions and optionally filters exact target. Duplicate requested positions
are returned once. `index.records(target=...)` streams all matching positions.
Readers cannot race collection/consumption/cleanup through separate spool handles.
Each JSONL envelope is limited to 64 MiB and the spool to 64 GiB, with explicit
errors on append/read. Appends stage encoder chunks in a temporary on-disk file
before copying a complete envelope to JSONL; scratch/serialization/size failures
do not alter earlier committed records. The staging file needs writable space
for one envelope in addition to the spool. New manifests record `record_limit_bytes`; provenance-bound or marked spools
use the 64 MiB reader bound. Unmarked historical spools have a finite 256 MiB
read allowance, preserving the demonstrated 65 MiB capture. Larger legacy records
fail explicitly without deleting their source.
Completed malformed, duplicate, out-of-range or truncated
envelopes fail consumption and retain the run. Limits do not bound a device
collector before it returns a payload. Retrieval decodes a bounded number of individual target payloads rather than a full run.
The index is disposable; JSONL is authoritative. Per-target result size, input
credentials and canonical inventory still occupy memory; this change bounds
full-run report/attempt aggregation, not the existing inventory-store format.

## Workflow consumers

Interface/VLAN reporting defaults to `outputs/runs/interface_vlan_report/`. The
inventory refresh CLI defaults to `outputs/runs/inventory_refresh/`; its Python
API defaults to `<export_parent>/runs`. Both accept `spool_root` to choose another
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

export_report_spool(run_directory, "outputs/reports/interface_vlan/recovered.xlsx")
# For an inventory_refresh run instead:
export_inventory_spool(run_directory, "outputs/reports/inventory/recovered_inventory.xlsx")
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
Permission denials during removal receive four attempts with 0.1, 0.2 and 0.4
second delays. Exhaustion returns a deferred cleanup status (`remove()` returns
`False`) and logs a fixed, sanitized warning; successful consumer output is still
returned. Cleanup records `cleanup_started` before deleting data and retains (or
restores after final directory denial) the manifest, with its original lifecycle
status and age. Such a directory may contain only cleanup residue, not replayable
outcomes: it permits cleanup retries, not another output consumption. Retry with
`ResultSpool(run_directory).remove()` for consumed runs, or the explicit stale
cleanup cutoff below. Failed output generation never starts cleanup and remains
fully replayable. No access-control changes or recursive removal are used.
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
    "outputs/runs/interface_vlan_report", before=datetime.now(timezone.utc) - timedelta(days=30)
)
```

Cleanup rechecks age under an exclusive OS lease, skips active runs and malformed
or unrelated directories, and refuses links or unexpected files/subdirectories.
The cutoff explicitly authorizes deletion of old failed/incomplete runs too.
Inspect retained artifacts before expiring them. Recognized interrupted
reader scratch files are removed only after validating their names and resolved
paths; unknown contents are preserved. Cleanup never recursively deletes trees. Separate processes must not share an output destination or canonical
inventory store; spool paths themselves are unique across processes.

## Request binding and Issue #162 status

`ResultSpool.bind(metadata)` persists sanitized JSON metadata once, only before
collection starts, under the run lease. It rejects sanitizer-changing values and
bindings over 64 KiB. Future v2 planning observations bind the canonical request
identity (including layout and invalid input rows) and source workbook SHA-256
when present; API-only request lists record a null workbook digest. Metadata is
not authentication. Legacy runs have no binding and cannot acquire a trusted
historical workbook association through inference. The direct offline planning recovery entry point is described in the
[planning manual](../user_manual/bulk-configuration-planning.md#offline-retained-observation-recovery-issue-162-revision).
It verifies complete target order, binding and freshness under the shared lease.
Explicit unbound legacy interpretation is diagnostic only and is rejected by
execution preparation. Observations and ordered results now use shared SQLite working sets;
aggregate planning gates no longer apply. Existing immutable plan and execution gates remain.

See the [whole-module audit and validation ledger](../operations/issue-162-processing-audit.md).
`indexed_json.py` owns reusable immutable SQLite JSON maps/arrays and canonical
stream encoding. Per-value processing is bounded to 256 MiB, total input to
64 GiB, nesting to 64 and container membership to 100,000. Scratch databases use
a 512 KiB cache and file-backed temporary storage; failed transactions remove
scratch state. Spools and published JSON remain authoritative. Planning validation
reevaluates complete same-device groups in workbook order, then indexes results
by original position. During load, untrusted supplied results are retained only as
hashes until reevaluation matches, preventing injected result secrets from reaching
scratch SQLite. Canonical streaming preserves existing SHA-256 bytes.
`BulkPlan.content`/`to_dict` retain explicit materializing compatibility behavior;
internal consumers use indexed views. New confirmation SQLite rows bind a separate
immutable public plan JSON by digest; old inline payloads remain supported.

Journal appends stage encoded chunks on disk under the owning lock, enforce
256 MiB per-event and 64 GiB total bounds before copying, then flush/fsync.
Failures stop the writer; committed prefixes remain readable and incomplete
final lines are ignored. Legacy iterator reads apply the same finite event/total
bounds. `ResultJournal.indexed()` exposes the same offset interface for complete event
lines, row-key lookup and disk-backed output references. Execution reports avoid
full-run offset maps and repeated full journal scans. Backup failure outcomes use
the shared spool beneath each backup run's `.processing` directory; raw config
never enters it. Prompt/save exchange buffers have a 64 MiB receive ceiling;
manual literal callbacks retain their disk-streamed receive behavior.

Plan JSON publication is exclusive and atomic for one file. Recovery completes
both exports before linking either, but two independent public filenames cannot
be published atomically by these links; a process crash may leave one artifact.
The retained spool can be exported to a new destination without networking.
