---
name: device-execution
description: Use for OrbitFlow multi-device execution, bounded per-device concurrency, worker/resource isolation, execution configuration, failure isolation, progress/result aggregation, or synchronization of shared runtime resources.
---

# Device Execution

## Use This Skill When

Use this skill when a task changes how OrbitFlow executes work across multiple target devices, including worker limits, execution configuration, per-device worker lifecycle, failure isolation, execution results, progress aggregation, or shared-resource synchronization.

Do not load this skill merely because a feature can run against many devices if that feature already uses the existing device-execution public interface unchanged.

## Core Contract

The concurrency unit is one target device.

One worker owns one device workflow and that device's runtime state:

```text
one target
  -> one worker
  -> one DeviceContext
  -> one DeviceSession / transport chain
  -> one CLI lifecycle
  -> requested per-device capabilities/workflow
  -> one per-device result
  -> cleanup
```

Reusable capabilities remain single-device components. They must not create their own executors or depend on whether other devices are running concurrently.

Do not parallelize separate capabilities inside the same device workflow unless a separately approved architecture change explicitly permits it.

## Shared Runner

Multi-device callers must use the shared OrbitFlow execution layer rather than creating feature-specific `ThreadPoolExecutor`, asyncio worker pools, process pools, or similar scheduling logic.

The runner should provide bounded execution with dynamic refill: when one worker completes, the next pending device may start immediately. Do not impose fixed batch barriers unless a workflow explicitly requires them.

The initial approved read-only concurrency setting is:

```toml
[execution]
max_concurrent_devices = 10
```

The limit is configuration-driven, not hard-coded in feature modules, so operators can change it later without editing capability/workflow code.

## Failure Isolation

One device failure must not terminate an otherwise safe multi-device run.

The execution layer should capture a deterministic per-device outcome including enough safe metadata for callers to distinguish success/failure and aggregate results without relying on raw exceptions.

Worker cleanup must run on success and failure.

## Resource Ownership

Active workers must not share mutable per-device runtime resources between targets, including:

- `DeviceContext`;
- `DeviceSession`;
- Paramiko SSH clients;
- shell/CLI channels;
- Linux direct-tcpip channels;
- Windows `tsh` forwarding processes;
- per-device intermediate result objects.

Shared services may be used only through concurrency-safe contracts.

## Shared Mutable Resources

Concurrency across devices does not imply unsynchronized writes to shared state.

Examples:

- inventory persistence must protect read/modify/write reconciliation;
- report/workbook writers should aggregate worker results and write in a controlled step rather than from device workers;
- process-wide dependency logging configuration must be concurrency-safe;
- progress/console output should be coordinated by the execution/application layer.

Do not add ad-hoc workflow-level locks when the shared owning layer should provide the safety contract.

## Execution Result Spooling

For large multi-device workflows, worker outcomes should flow through a reusable central result spool instead of requiring the caller to retain the complete run in memory.

Approved architecture:

```text
device workers
    -> generic DeviceOutcome
    -> one central ResultSpool writer
    -> per-run JSONL spool
    -> output consumer
       -> Excel
       -> API
       -> database
       -> JSON/export
```

The spool is execution infrastructure, not a reporting-specific file. Device workers do not write shared spool files directly. Recoverable execution spool data belongs under `outputs/runs/`; persistent application state belongs under `data/`.

Each execution uses a unique run directory, for example:

```text
data/runs/<timestamp>_<run-id>/
    manifest.json
    results.jsonl
```

Use a task namespace plus timestamp and a collision-resistant run identifier so concurrent or repeated runs never reuse the same spool path. This is the approved target layout; existing runtime defaults may remain on legacy paths until the dedicated migration is implemented.

`results.jsonl` stores one sanitized execution envelope per completed target. The common envelope owns execution metadata such as run ID, input position, safe target/device identity, status, timestamps, error category, and a task-specific `payload`. The execution layer must not know capability-specific fields inside the payload.

`manifest.json` records run-level state such as task identity, target/completed/failed counts and lifecycle status. Incomplete or failed output consumption must be distinguishable from a successfully completed run.

Lifecycle policy:

- create a unique spool when collection starts;
- append outcomes through one owning writer as workers complete;
- consumers read/stream the spool after or during controlled aggregation;
- if final output succeeds, the completed spool may be removed according to cleanup policy;
- if output generation fails or the run is interrupted, retain the spool so output can be retried without reconnecting to devices;
- provide deterministic cleanup for abandoned retained runs;
- never persist credentials, raw secret-bearing output, or unsanitized exception text.

The initial scale-hardening validation target is approximately 1,500 devices with a configured active-device limit of 5. This validates bounded execution and bounded-memory aggregation without changing the generic configuration contract or hard-coding 5 into feature modules.

## Configuration-Changing Workflows

Provisioning/remediation may reuse the same device-execution layer, but must not automatically inherit a read-only concurrency limit unless that limit is explicitly approved for the change workflow.

Configuration changes still require explicit user intent and all existing pre-check/apply/verify/audit safeguards.

## Testing

When execution behaviour changes, cover as applicable:

- configured maximum active devices is never exceeded;
- a freed worker starts the next pending target without waiting for unrelated slow devices;
- one failed device does not stop safe peers;
- per-device runtime objects are not shared;
- shared inventory/state updates cannot lose another worker's update;
- concurrent logging remains safe and sanitized;
- result aggregation is deterministic;
- a 1,500-target synthetic run can spool exactly one outcome per target without duplicate/missing records;
- output consumption can be retried from a retained spool without rerunning device workers;
- successful cleanup removes only the intended completed run while failed/incomplete runs remain recoverable;
- large-run aggregation does not require retaining the complete report row set in memory;
- a configured worker limit of 1 preserves sequential execution semantics;
- tests do not require live devices.

Live validation remains operator-controlled.
