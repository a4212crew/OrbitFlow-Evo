---
name: interface-collector
description: Use for OrbitFlow interface description/status collection, vendor-aware collection commands, parsing, normalized interface records, change detection, Excel tracking output, collection concurrency, collector logging, or collector tests.
---

# Interface Collector

## Use This Skill When

Use for collecting interface descriptions/status, collector commands, parsing, normalized records, change comparison, tracking workbook output, concurrency/error handling, and collector tests.

Do not implement transport here.

InterfaceService is the authoritative source for actual observed/configured interface identities, descriptions, admin state, and oper state. References to interface names found only in VLAN, L2VPN, VSI, bridge-domain, or other service configuration must not be promoted into InterfaceRecord objects unless the interface is independently observed/configured as a real interface.

## Related Skills

- `../jumphost-connectivity/SKILL.md` — device sessions.
- `../device-inventory/SKILL.md` — resolved device identity/platform context.
- `../excel-inventory/SKILL.md` — optional Excel/list target input.
- `../cisco-network-cli/SKILL.md` — Cisco CLI details.
- `../huawei-network-cli/SKILL.md` — Huawei CLI details.
- `../ubiquiti-network-cli/SKILL.md` — EdgeSwitch CLI details.

## Collection Workflow

1. Receive a resolved DeviceContext or resolve the supplied target through the device-inventory layer.
2. Acquire/reuse a device session through OrbitFlow transport.
3. Run the appropriate vendor/platform command.
4. Parse deterministically.
5. Normalize into common records.
6. Isolate per-device failures.
7. Compare with prior tracking state.
8. Write the workbook in a controlled batch.

Do not implement an independent SSH path or independent platform-discovery path in collector code.

## Platform Collection Baseline

| Platform | Baseline command |
|---|---|
| Cisco IOS / IOS-XE | `show interfaces description` |
| Cisco IOS-XR | `show interfaces description` |
| Huawei VRP | `display interface brief` and/or `display interface description` |
| Ubiquiti EdgeSwitch | `show interfaces status all` |

Vendor-specific details belong in vendor skills.

## Parsing

Prefer deterministic structured parsing such as NTC templates/TextFSM or an existing tested deterministic project parser.

Fallback parsing is acceptable only when a suitable template is unavailable or structured parsing is empty while valid raw data is clearly present.

Do not rely only on fragile whitespace splitting when a stable structured parser exists.

## Normalized Record

```python
{
    "device_name": "string",
    "device_ip": "string",
    "platform": "string",
    "port_name": "string",
    "port_description": "string",
    "admin_status": "string",
    "oper_status": "string",
    "collection_time": "datetime",
}
```

Excel-facing tracking may also include `Location ID`, `Remark`, `Date Update`, and `Last Seen`.

Do not guess unavailable status fields.

## Tracking Workbook

### `Interface_Current`
Expected fields:
- Device Name
- Device IP
- Platform
- Port Name
- Port Description
- Location ID
- Admin Status
- Oper Status
- Remark
- Date Update
- Last Seen

### `Change_Log`
Append-only change history with device/interface identity, change type, old/new descriptions/status, date, and remark.

### `Run_Errors`
Per-run connection, command, parsing, or output failures with device context.

## Change Detection

Preferred interface key:

```text
Device IP + Port Name
```

A stable hostname may be added if project data guarantees consistency.

Change types:
- new interface;
- description changed;
- status changed;
- description and status changed;
- no change;
- previously known interface missing from latest successful collection.

## Date Rules

- Use execution-host system date/time.
- New/changed records update `Date Update`.
- Unchanged records preserve prior `Date Update` where available.
- Successfully collected records update `Last Seen`.

## Excel Safety and Scale

Before overwriting an existing persistent tracking workbook, create a timestamped backup where the established workflow expects overwrite-in-place behaviour.

Do not write the final workbook once per device during large runs. Aggregate results and write in controlled batches/end-of-run.

Design for approximately 1,500 devices with configurable bounded concurrency.

## Error Handling

Handle per-device connection timeout, authentication failure, unreachable target, unsupported platform, empty output, parser failure, and output failure where isolation is possible.

One failed device must not crash the full run.

## Tests

Unit-test parser normalization, empty output, new interface detection, description/status changes, unchanged-date preservation, missing-interface detection, workbook creation/update, and error recording.

Parser/compare/Excel tests must not require live devices.
