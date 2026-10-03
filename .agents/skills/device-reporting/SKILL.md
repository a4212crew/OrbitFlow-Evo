---
name: device-reporting
description: Use for OrbitFlow read-only batch reports that combine DeviceContext, InterfaceService, VlanService, normalized forwarding-domain state, and Excel output.
---

# Device Reporting

## Use This Skill When

Use for read-only reports that combine device identity, actual interface state/description, normalized VLAN/forwarding behaviour, forwarding-domain database objects, and batch Excel output.

Do not add vendor commands or parsers here. Reporting composes existing capabilities and must not reinterpret raw vendor configuration.

## Adjacent Capability Boundaries — Do Not Load by Default

Reporting consumes these capabilities through their existing interfaces. Using them does not require loading their skills. Load an adjacent skill only when the task changes that capability or targeted source inspection proves the change crosses the boundary.

- `../excel-inventory/SKILL.md` — target-list/credential input.
- `../device-inventory/SKILL.md` — DeviceContext identity/resolution.
- `../interface-collector/SKILL.md` — interface collection/normalization.
- `../vlan-observation/SKILL.md` — VLAN/forwarding semantics.
- `../runtime-logging/SKILL.md` — logging/sanitization behaviour.
- `../jumphost-connectivity/SKILL.md` — DeviceSession transport.

## Architecture

Preferred per-device flow:

```text
input target
    -> connect_device(...)
    -> DeviceInventoryResolver.resolve(...)
    -> DeviceContext
    -> same DeviceSession / shared CLI
       -> InterfaceService.collect(..., context)
       -> VlanService.collect(..., context)
    -> normalized report rows
```

Connect once per device where practical. Do not rediscover platform, recreate transport, or duplicate vendor parsing in reporting code.

One failed device must not terminate an otherwise safe batch.

Reporting does not own concurrency. For multi-device runs, execute the per-device reporting workflow through the shared device-execution layer. At large scale, normalized per-device outcomes are persisted through the shared execution-result spool and reporting consumes that spool; workbook generation remains a centralized controlled step.

## Interface/VLAN Join

InterfaceService is authoritative for actual interface identity plus description/admin/oper state.

VlanService is authoritative for normalized forwarding semantics:

```text
port_type
untagged_vlan
tagged_vlans
bridge_domains
service_mappings
```

Join using resolved device identity plus canonical interface name.

Rules:

- one report row per actual interface;
- reporting must not create an interface solely because VLAN/L2VPN/VSI/bridge-domain/service configuration references a name;
- reporting must not infer access/trunk/hybrid/EVC/service/routed semantics from raw vendor fields;
- reporting must not reconstruct bridge-domain/VSI relationships;
- multiple EVC/service observations may aggregate into one physical-interface row only when exact `service_mappings` remain preserved;
- preserve `ALL`, `NONE`, explicit tagged VLAN lists, and blank distinctly;
- unmatched service references belong to validation/analysis output, not the normal Interfaces row set.

## Default Workbook

### `Interfaces`

Recommended normalized fields:

- Device Name
- Device IP
- Platform
- Device Family
- Interface
- Description
- Admin Status
- Oper Status
- Port Type
- Untagged VLAN
- Tagged VLANs
- Bridge Domains
- Service Mappings
- Collection Time

The report should display normalized capability output, not derive forwarding meaning itself.

### `VLAN_Database`

Recommended fields:

- Device Name
- Device IP
- Platform
- Object Type
- Object ID
- Domain ID
- Name
- Collection Time

Preserve `object_type` so `vlan`, `bridge_domain`, and `vsi` remain distinct.

The `Domain ID` may be numeric or named. For example, IOS-XR may use a bridge-domain name and Huawei may use a VSI name.

If an object has no configured name, use its object/domain ID as the display name.

Do not create database objects from interface references in the reporting layer.

### `Run_Errors`

Recommended fields:

- Device IP
- Device Name when known
- Stage
- Error Category
- Time

Do not include passwords, credential material, raw device output, or unsanitized exception text.

Validation/compliance findings are a separate future output unless explicitly requested.

## Excel Behaviour

- Do not require the complete multi-device report row set to remain in memory for large runs.
- Consume the shared execution-result spool incrementally and use streaming/write-only workbook generation where practical.
- Workers must not write the workbook or shared spool directly; shared execution owns spooling and reporting owns output consumption.
- Prefer one report file per execution rather than writing once per device.
- If workbook generation fails after device collection, retain the run spool so the workbook can be regenerated without recollecting devices.
- Apply practical operator formatting: frozen headers, filters, readable column widths, and stable tab names.
- Keep Excel output deterministic and covered by tests.
- Design for approximately 1,500 devices.
- Reporting is observation only; do not add compliance decisions unless explicitly requested as a separate analysis feature.

## Logging

Use the shared OrbitFlow logging foundation. A reporting run should use a module-owned log such as:

```text
logs/reporting/YYYY-MM-DD/interface_vlan_report.log
```

Keep console output concise and record per-device/stage failures in both the run log and `Run_Errors` where appropriate.

User-facing report files belong under the approved output hierarchy, for example `outputs/reports/interface_vlan/`. This is the target path architecture; until runtime migration is implemented, existing code may still use legacy defaults.

## Tests

Cover:

- one row per actual interface;
- canonical interface join;
- normalized port-type and forwarding-field presentation;
- multiple EVC mappings aggregated without losing exact service mappings;
- `ALL`/`NONE`/blank preservation;
- unmatched service references not creating interface rows;
- VLAN/bridge-domain/VSI object preservation;
- workbook sheet/column generation;
- failed-device isolation;
- no-secret output;
- reuse of DeviceContext and one established session/shared CLI where practical;
- deterministic operation without live devices;
- large synthetic runs (target approximately 1,500 devices) preserve one outcome per target without duplicate/missing report content;
- workbook generation can be retried from a retained spool without rerunning device collection.
