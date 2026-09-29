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
- a configured worker limit of 1 preserves sequential execution semantics;
- tests do not require live devices.

Live validation remains operator-controlled.
