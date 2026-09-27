---
name: excel-inventory
description: Use for OrbitFlow Excel/list target loading, required/optional input fields, platform override normalization, credential precedence, input validation, Location ID handling, or input-source tests.
---

# Excel Inventory

## Use This Skill When

Use for Excel/list target loading, required/optional fields, row validation, optional platform override normalization, device target selection, credential precedence, Location ID handling, and input-source tests.

Do not use this skill for Teleport transport implementation, interface parsing, or access VLAN command generation.

## Adjacent Capability Boundaries — Do Not Load by Default

Load an adjacent skill only when the task modifies that layer or targeted source inspection shows the input change crosses into it.

- `../device-inventory/SKILL.md` — identification/platform/identity reconciliation.
- `../jumphost-connectivity/SKILL.md` — connection transport.
- `../interface-collector/SKILL.md` — collection behaviour.
- `../access-vlan-provisioning/SKILL.md` — provisioning-specific input semantics.

## Principle

Excel is an approved **target input source**, not the authoritative physical-device inventory.

Do not hardcode production device lists into task workflows. Load target rows, validate them, then let the device-inventory layer resolve observed hostname/vendor/platform/model/serial where required.

## Core Device Inventory Fields

| Column | Purpose | Requirement |
|---|---|---|
| `Device IP` | Management/reachability address | Required |
| `Device Name` | Compatibility/display hint | Optional |
| `Platform` | Manual OrbitFlow platform override/hint | Optional |
| `Username` | Device login | Optional if credential provider supplies it |
| `Password` | Device password | Optional if credential provider supplies it |
| `Secret` | Enable secret where required | Optional |
| `Port` | SSH port | Optional, default 22 |

Keep column names centralized as constants where practical.

## Security

Preferred behaviour:
1. approved credential provider / environment / secret store;
2. inventory credentials only where explicit compatibility requires them;
3. never print or log credential values.

Do not require passwords to be stored in Excel.

## Validation

At minimum:
- required columns exist;
- inventory is not empty when a device operation is requested;
- target address is present;
- supplied platform override, when present, normalizes to a supported identifier;
- optional port is valid when supplied;
- invalid rows produce clear row-specific errors.

A bad row must not terminate an otherwise safe multi-device batch.

## Platform Identifiers

Current intended identifiers:
- `cisco_ios`
- `cisco_xe`
- `cisco_xr`
- `huawei_vrp`
- `ubiquiti_edgeswitch`

Keep OrbitFlow platform identifiers separate from library-specific driver names where needed.

## Location ID

Where workflows use Location ID, preserve the project convention that it starts with `LW` and ends at the last consecutive digit in that ID token. Do not invent a Location ID when none is present.

## Testing

Unit tests should cover:
- valid inventory load;
- missing required columns;
- empty inventory;
- unsupported supplied platform override;
- malformed optional values;
- platform/Location ID normalization;
- credential values not appearing in logs/errors.
