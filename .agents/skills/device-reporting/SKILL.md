---
name: device-reporting
description: Use for OrbitFlow read-only batch reports that combine DeviceContext, InterfaceService, VlanService, and Excel output.
---

# Device Reporting

## Use This Skill When

Use for read-only reports that combine device identity, interface state/description, VLAN attachment facts, VLAN database/service objects, and batch Excel output.

Do not add new vendor commands or parsers here. Reporting composes existing capabilities.

## Related Skills

- `../excel-inventory/SKILL.md` — target-list and credential input.
- `../device-inventory/SKILL.md` — DeviceContext resolution and identity.
- `../interface-collector/SKILL.md` — interface description/admin/oper state.
- `../vlan-observation/SKILL.md` — interface VLAN facts and VLAN/service objects.
- `../runtime-logging/SKILL.md` — report-run logging and sanitized errors.
- `../jumphost-connectivity/SKILL.md` — shared DeviceSession transport.

## Architecture

Preferred per-device flow:

```text
input target
    -> connect_device(...)
    -> DeviceInventoryResolver.resolve(...)
    -> DeviceContext
    -> same DeviceSession
       -> InterfaceService.collect(..., context)
       -> VlanService.collect(..., context)
    -> normalized report rows
```

Connect once per device where practical. Do not rediscover the platform in reporting code and do not recreate transport or parser logic.

One failed device must not terminate an otherwise safe batch.

## Interface/VLAN Join

Join interface state and VLAN observations using normalized device identity plus canonical interface name.

Do not guess unsupported values. Preserve InterfaceService as the source for description/admin/oper state and VlanService as the source for VLAN/service facts.

Where one physical interface has multiple VLAN/service observations, reporting may aggregate VLAN IDs for the summary interface row while preserving vendor-neutral detail in dedicated columns. Do not collapse bridge-domain, VSI, service-instance, or other service identities into VLAN IDs.

## Default Workbook

### `Interfaces`

Recommended fields:
- Device Name
- Device IP
- Platform
- Device Family
- Interface
- Description
- Admin Status
- Oper Status
- Mode
- Attached VLANs
- Access VLAN
- Native VLAN
- PVID
- Allowed VLANs
- Tagged VLANs
- Untagged VLANs
- Service VLAN
- Outer VLAN
- Inner VLAN
- Service Binding Type
- Service Binding Name
- Collection Time

`Attached VLANs` is a convenience union of VLAN IDs already observed in normalized VLAN fields. It must not invent VLAN identity from bridge-domain/service identifiers.

### `VLAN_Database`

Recommended fields:
- Device Name
- Device IP
- Platform
- Object Type
- Object ID
- VLAN ID(s)
- Name
- Collection Time

Preserve `object_type` so traditional VLANs and service objects remain distinct.

### `Run_Errors`

Recommended fields:
- Device IP
- Device Name when known
- Stage
- Error Category
- Time

Do not include passwords, credential material, raw device output, or unsanitized exception text.

## Excel Behaviour

- Aggregate results in memory and write the workbook in a controlled batch/end-of-run step.
- Prefer one report file per execution rather than writing once per device.
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

## Tests

Cover:
- interface/VLAN join logic;
- multiple VLAN observations on one interface;
- traditional VLAN vs service-object preservation;
- workbook sheet/column generation;
- failed-device isolation;
- no-secret output;
- reuse of DeviceContext and one established session where practical;
- deterministic operation without live devices.
