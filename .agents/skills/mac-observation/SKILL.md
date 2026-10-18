---
name: mac-observation
description: Use for independent MAC collection/parsing, snapshot lookups, exact physical attachment resolution and normalized MAC/VLAN composition.
---

# MAC observation

Follow AGENTS.md and documentation-management. Contract:
[architecture](../../../docs/architecture/mac-address-lookup.md),
[API](../../../docs/operations/mac-address-lookup-api.md),
[manual](../../../docs/user_manual/mac-address-lookup.md).

MacService remains independently callable with resolved DeviceContext and an
already established session/optional borrowed DeviceCLI. Pure vendor parsers own
syntax. No inventory discovery, peer traversal, device writes, generated runtime
configuration, extra count command or resynchronization. IOS/IOS-XE use full
show mac address-table, XR uses the configured owner-approved location (default
0/RP0/CPU0), Huawei display mac-address and EdgeSwitch show mac-addr-table all
remain invocation-unconfirmed candidates pending owner live validation.

Normalize MACs to lowercase colon notation; preserve original type/status,
attachment, service/domain and slot scopes, duplicates and nonphysical entries.
One table total uses supplied table total or parsed count including static/CPU/
remote; local selections count themselves. Scoped totals remain scoped. Never
compare totals or substitute available address space.

Resolve exact EFP/subinterface identities to independently observed/configured parents;
never create InterfaceRecords from service references or pick LAG members.
Preserve canonical join keys and platform-correct full display names. CPU,
routed/logical, remote and unresolved destinations remain explicit. Port mode
comes from shared normalized facts; access/trunk/hybrid only when proven, else
Unknown, with EVC/service/routed detail preserved.

VLAN filtering requires explicit normalized ingress/domain relationships.
Never equate VLAN with BD/EFP/PW/internal IDs, suffixes or service-name digits.
Exact EFP typed facts and unique XR operational joins are required. XR VLAN
proof requires exact operational/configured bridge-group and domain agreement. Unknown
relationships cannot match. Compliance/audit behavior must remain unchanged.

Compose in the application using one shared session/context, shared execution
and bounded result spooling. Optional enrichment failures preserve usable MACs.
One literal-safe workbook per run, six exact main columns, one observation/row;
supporting keyed details/totals/errors, offline CLI/API regeneration, no third
submenu action. Paths: outputs/reports/mac_table, outputs/runs/mac_table and
outputs/logs/<module>/YYYY-MM-DD. Cover supplied shapes, empty/error/truncated
tables, aliases, exact/parent/service lookups, duplicates, mapping ambiguity,
menu validation/cancellation, isolation/recovery and secret exclusion offline.
Samples/tests are not owner live validation.
