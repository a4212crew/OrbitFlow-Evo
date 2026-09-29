# OrbitFlow Device Capability and OSS Architecture

## Purpose

OrbitFlow is intended to evolve from a network automation codebase into a reusable OSS capability layer.

The central design rule is:

> Implement network-device capabilities once, then allow internal workflows, external REST API consumers, future GUIs, schedulers, and OSS/BSS integrations to call the same application and capability interfaces.

The REST/API layer must not reimplement vendor-specific device logic.

## Architectural Layers

### 1. Infrastructure Layer

Responsibilities:
- Teleport and SSH transport;
- device sessions;
- target input sources;
- device identification/inventory resolution;
- credential integration;
- common logging;
- bounded multi-device execution and execution configuration;
- progress/result aggregation and shared-resource coordination.

Higher layers must not recreate OS-specific transport or feature-specific multi-device executors.

### Shared Device Execution

For multi-device requests, OrbitFlow schedules complete per-device workflows through one shared execution layer. One worker owns one target and its DeviceContext/session/CLI lifecycle; reusable capabilities themselves remain single-device. The initial approved read-only setting is 10 active devices and is configuration-driven so it can change without editing feature modules.

The execution layer provides bounded scheduling, dynamic worker refill, failure isolation, per-device outcomes, and coordinated progress/result aggregation. Shared mutable state such as inventory persistence, report generation, and process-wide logging must remain protected by its owning layer rather than written unsafely by workers.

Implemented by `orbitflow.execution.execute_devices`, with configuration in
`orbitflow.config` and the application's `orbitflow.toml` execution table.
Submissions are bounded as well as active workers; completion frees a slot
without an input-order wait. Outcomes are returned in input order, contain no raw
exception objects/messages, and preserve caller context variables separately per
worker. Limit 1 executes on the caller thread. Progress output is serialized by
the execution layer; report/export generation is caller-owned after cleanup.

The inventory store owns process-local resolved-path transaction locks covering
read/modify/replace, shared across store instances. Concurrent observations of
one identity persist in transaction order; input-ordered export attempts and run
status remain stable. Sequential mode is available for ordered alias observations.
The logging layer owns path-shared rotating handlers and reference-counted global
Paramiko routing. Routing is restored only after the final connection exits;
raw dependency text is discarded, and dependency-thread markers are unattributed
rather than assigned to an arbitrary device. Separate processes must not share
inventory/log files or an export destination.

### Device Identification / Inventory Resolution

OrbitFlow separates target input from observed device identity.

A caller may begin with only a management IP plus credentials/credential reference. The device resolver should determine or reuse vendor/platform context, device family/model and any required capability profile, collect relatively stable device facts, reconcile physical identity, and return a normalized `DeviceContext`.

Inventory is not a CMDB or authoritative network source of truth. It is latest-known observed context used to identify the physical device and select reusable platform capabilities.

Identity rules:
- same serial + different IP -> same physical device;
- same IP + different serial -> likely replacement/reassignment and requires re-identification;
- same hostname + different serial -> distinct devices / hostname collision;
- no reliable serial -> do not aggressively merge.

Volatile state such as interface status, VLANs, routing/service state, counters, and logs remains in live observation capabilities and is recollected when requested.

Platform/OS family and device capability profile are separate concerns. A capability may select behaviour using both. For example, ME3600X is a Cisco IOS device but still requires EVC/service-instance VLAN parsing, while C3750X is also Cisco IOS but uses classic switchport/VLAN behaviour.

### 2. Device Capability Layer

This layer represents reusable operations that can be performed against network equipment.

Examples:
- get interface status/descriptions/counters;
- get VLAN state;
- get MAC table;
- get ARP/neighbor state;
- get routes;
- get L2VPN/service state;
- generate deterministic configuration;
- apply configuration through approved safety controls;
- verify resulting state.

Vendor-specific implementations may use different commands and parsers, but should return normalized structured models wherever practical.

Conceptual example:

```python
vlans = device.get_vlans()
interfaces = device.get_interfaces()
macs = device.get_mac_table()
```

A workflow should not need to know whether the device is Cisco IOS-XE, IOS-XR, Huawei VRP, or another supported platform.

### 3. Normalized Models

Raw CLI output should be parsed into reusable structured records.

Examples:
- `InterfaceRecord`
- `VlanRecord`
- `MacRecord`
- `RouteRecord`
- `ServiceRecord`
- `TroubleshootingFinding`
- configuration/change plan models

Normalized models are intended to be reused by:
- internal workflows;
- analysis logic;
- Excel/reporting;
- JSON serialization;
- REST API responses;
- future GUIs;
- external OSS/BSS integrations.

### 4. Application / Workflow Layer

Complex operational features orchestrate reusable device capabilities rather than embedding vendor commands directly.

Examples:
- interface description collector;
- VLAN audit;
- VLAN mismatch analysis;
- configuration planning and remediation;
- service troubleshooting;
- service assurance;
- provisioning;
- migration checks;
- compliance/audit workflows.

Recommended pattern:

```text
OBSERVE
  -> collect normalized state

ANALYZE
  -> compare against policy / expected state

PLAN
  -> generate deterministic remediation plan

APPLY
  -> execute only when explicitly requested and safety checks pass

VERIFY
  -> recollect state and confirm result

RECORD
  -> report/log outcome
```

Read-only analysis must remain usable without configuration privileges.

### 5. Integration / OSS Layer

OrbitFlow should expose the same application and capability interfaces through external integrations.

Potential consumers:
- REST API;
- internal GUI;
- schedulers;
- external OSS/BSS systems;
- service portals;
- other automation platforms.

The API layer should be thin. It should authenticate/authorize, validate requests, call the same internal service/capability interfaces, and serialize normalized results.

Conceptual examples:

```text
GET  /devices/{id}/interfaces
GET  /devices/{id}/vlans
GET  /devices/{id}/mac-table
GET  /devices/{id}/routes

POST /workflows/vlan-audit
POST /workflows/service-troubleshooting
POST /workflows/vlan-remediation
```

Normal OSS operations should expose intent/capability APIs rather than raw vendor CLI.

A generic raw-command API must not become the main OSS interface. If one is introduced later for controlled engineering use, it should be separately authorized and treated as an exceptional capability.

## Device Facade / Capability Interface

OrbitFlow should move toward a device facade/factory that selects the correct vendor implementation while presenting stable capabilities to workflows.

Conceptual example:

```python
device_context = device_resolver.resolve(target, credentials)
device = device_factory(device_context)

interfaces = device.get_interfaces()
vlans = device.get_vlans()

plan = device.plan_config(...)
device.apply_config(plan)
device.verify(...)
```

The exact class structure should evolve incrementally. Do not create empty abstractions or directories before they are needed, but new features should follow this direction.

## Capability Composition from DeviceContext

The intended request path is:

```text
Excel / CSV / CLI / API input
        -> validated targets
        -> shared device-execution layer
        -> per-device workflow
        -> Device Inventory / Resolver
        -> DeviceContext
        -> reusable device capabilities
        -> normalized observations
        -> workflows / analysis / reporting
```

First run for an unknown target may perform platform detection and stable fact collection before invoking the requested capability. Subsequent runs should reuse known context but still perform enough identity validation to detect replacement/reassignment. Live interface/VLAN/routing/service/log observations are recollected rather than treated as permanent inventory.

## Vendor Isolation

Vendor commands and parsing rules belong in vendor-specific modules.

A higher-level workflow must not contain code such as:

```python
if vendor == "cisco":
    run("show vlan brief")
elif vendor == "huawei":
    run("display vlan")
```

Instead, the workflow should call a capability such as `get_vlans()`, and the selected vendor implementation decides how to obtain and parse the data.

## Configuration Safety

Configuration capabilities must remain distinct from observation and analysis.

Preferred flow:

```text
validate
  -> pre-check
  -> plan/generate
  -> explicit apply
  -> verify
  -> record
```

API exposure must preserve the same safety model. An API endpoint must not bypass validation, pre-check, apply, verification, or audit controls already required by internal workflows.

## Troubleshooting Model

Troubleshooting should collect reusable facts and evaluate deterministic diagnostic rules.

Conceptual flow:

```text
Collect facts
  -> normalize observations
  -> evaluate diagnostic rules
  -> produce findings
  -> narrow probable fault domain
  -> suggest next checks or remediation
  -> optional explicit remediation
```

Possible capabilities used by troubleshooting:
- interface state/counters;
- VLAN presence;
- MAC learning;
- ARP/neighbor state;
- routing state;
- service/L2VPN state;
- configuration/policy state.

Troubleshooting output should be structured enough to support CLI presentation, reports, REST API responses, and future GUI presentation.

## Development Guidance

When adding a new feature:

1. Identify reusable device capability/capabilities first.
2. Implement vendor-specific command/parsing logic in the vendor layer.
3. Normalize output into structured models.
4. Keep analysis/decision logic independent from raw CLI syntax.
5. Build the per-device workflow by composing capabilities.
6. For multi-device execution, reuse the shared device-execution layer; do not introduce feature-specific concurrency.
7. Keep configuration planning/apply/verify separate from observation.
8. Make the same capability/service callable by future REST/API consumers without duplicating device logic.
9. Add deterministic tests at each reusable layer.

This architecture should be applied incrementally as OrbitFlow grows.
