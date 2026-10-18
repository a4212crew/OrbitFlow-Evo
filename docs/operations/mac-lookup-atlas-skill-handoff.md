# Issue #130 protected skill reconciliation

Atlas applied this Markdown handoff on PR #131 on 2026-10-18. The focused
skills, console guidance and AGENTS routing are included on the PR branch;
merge and owner live validation remain pending. Codex did not bypass the
protected `.agents/` execution permissions. The templates below retain the
handoff provenance; the applied skills include the reviewed XR identity,
reported-count and known-empty-section clarifications.

Create `.agents/skills/mac-observation/SKILL.md` with:

```markdown
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
Exact EFP typed facts and unique XR operational joins are required. Unknown
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
```

Create `.agents/skills/bridge-domain-observation/SKILL.md` with:

```markdown
---
name: bridge-domain-observation
description: Use for independent IOS-XR operational bridge-domain attachment collection, pure parsing and exact snapshot lookups.
---

# Operational bridge-domain observation

Follow AGENTS.md and documentation-management. See
[MAC architecture](../../../docs/architecture/mac-address-lookup.md) and
[API](../../../docs/operations/mac-address-lookup-api.md).

BridgeDomainService independently collects show l2vpn bridge-domain using a
resolved XR DeviceContext and shared session/optional borrowed CLI. No MAC,
interface or VLAN collector dependency; no menu item. Preserve bridge group,
domain, internal ID, state, ACs including BVI/down/unresolved, neighbor/PW pairs,
backup flags and supplied counts. References never create InterfaceRecords.

Lookups use exact canonical interface, neighbor/PW pair or internal ID only.
Return all candidates; missing or multiple matches stay unresolved. Do not
guess VLANs from internal IDs, PW IDs, domain names or interface suffixes.
Composition uses explicit shared encapsulation relationships and observed
interface identities. No auto-following neighbors, resynchronization or writes.

Test supplied summaries, aliases, BVI/down/backup attachments, exact remote and
routed joins, repeated/ambiguous domains and malformed/truncated output. Keep
sample/deterministic evidence separate from pending owner live validation.
```

In `.agents/skills/interactive-operations-console/SKILL.md`, replace the sentence
starting `Main: Configuration Management;` with:

```markdown
Main: Configuration Management; Device Inventory; Interface & VLAN Reporting; VLAN Compliance; Configuration Backup; Environment Setting; MAC Address Lookup; Exit.

MAC Address Lookup (main 7; Exit 8): Search MAC Address; List All MAC Addresses;
Back. Exactly two feature actions. No backend collectors or regeneration submenu
choice. Search validates dotted/colon MAC and exact workbook IP before network
confirmation; no concurrency prompt. List validates VLAN 1-4094, reuses all/subset
workbook selection and per-run concurrency 1-5 blank=1. Both reuse profile and
Teleport checks/cancellation. Existing profile schema is unchanged. Output under
outputs/reports/mac_table; recovery via direct API/CLI only. See the MAC manual.
```

In `AGENTS.md` Skill Routing, insert these two rows after VLAN observation:

```markdown
| MAC observation, snapshot lookups and exact attachment/physical/VLAN composition | `.agents/skills/mac-observation/SKILL.md` |
| IOS-XR operational bridge-domain attachment observation and exact lookups | `.agents/skills/bridge-domain-observation/SKILL.md` |
```

Apply routing only alongside the new skills so links do not point at absent files.
