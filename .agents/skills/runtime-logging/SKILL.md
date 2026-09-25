---
name: runtime-logging
description: Use for OrbitFlow shared runtime logging, module/date log layout, sanitization, rotation, dependency-log routing, and operator console behavior.
---

# Runtime Logging

## Principle

Runtime modules use the shared OrbitFlow logging foundation. Do not create independent handlers, ad-hoc log directories, or module-specific secret-handling rules when the shared logger can be reused.

The current shared implementation is `orbitflow.logging`.

## File Layout

Default layout:

```text
logs/<module>/YYYY-MM-DD/<name>.log
```

Examples:

```text
logs/inventory/YYYY-MM-DD/inventory_batch.log
logs/transport/YYYY-MM-DD/transport.log
logs/reporting/YYYY-MM-DD/interface_vlan_report.log
```

Logs are runtime artifacts and remain ignored by Git.

## Ownership

- Transport owns detailed SSH/tunnel/dependency diagnostics.
- Inventory owns inventory batch/result diagnostics.
- Interface/VLAN/reporting/workflow layers own their own operational events.
- Higher layers should record the stage/category of a lower-layer failure without duplicating raw lower-layer diagnostics.

## Console vs File Logs

Console output should be concise and operator-oriented.

Expected caught failures should appear as a short status such as:

```text
172.25.29.132: failed (DeviceConnectionError)
```

Detailed technical diagnostics belong in file logs.

Do not suppress the existence or category of failures merely to keep the console clean.

## Security

Never log:
- passwords;
- OTPs;
- private keys or certificates containing secret material;
- access tokens;
- authorization headers;
- credential objects;
- production secrets;
- raw device output when it may contain secrets.

Use fixed operational messages and safe structured metadata. Exception diagnostics should prefer categories, errno, and frame locations over arbitrary exception messages.

Do not weaken sanitization for debugging convenience.

## Rotation and Retention

Use bounded/rotating files through the shared logging utility. Current defaults are implementation details and may evolve, but log files must not grow without bound.

Historical dated directories may be retained for operator archival/removal. Do not build automatic destructive retention behavior unless explicitly scoped.

## Dependency Logging

Where a dependency such as Paramiko emits noisy internal tracebacks for failures OrbitFlow already catches:
- route/suppress the uncontrolled console noise where practical;
- preserve the OrbitFlow exception seen by callers;
- record safe dependency diagnostics in the appropriate module log;
- restore pre-existing logging configuration after the scoped operation;
- do not change transport retry, authentication, timeout, or connection semantics merely to alter logging.

## Concurrency

Be careful with process-wide dependency logger configuration. The current transport-routing mechanism is intended for sequential/scoped operation unless explicitly redesigned for concurrency.

Do not share one file handler unsafely across processes.

## Tests

Test:
- module/date path creation;
- bounded rotation configuration;
- logger cleanup;
- secret sanitization;
- exception-chain safety;
- dependency-console suppression/restoration;
- Windows/Linux behavior where relevant;
- caller-visible exception preservation.
