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
backup flags and supplied total/up counts without recalculation or comparison.
Accept known empty AC, Access PW, VFI and Access VFI sections. Reject malformed
AC/PW rows, unknown sections and nonempty unsupported VFI content explicitly. References never create InterfaceRecords.

Lookups use exact canonical interface, neighbor/PW pair or internal ID only.
Return all candidates; missing or multiple matches stay unresolved. Do not
guess VLANs from internal IDs, PW IDs, domain names or interface suffixes.
Composition uses explicit shared encapsulation relationships and observed
interface identities. No auto-following neighbors, resynchronization or writes.

Test supplied summaries, aliases, BVI/down/backup attachments, exact remote and
routed joins, repeated/ambiguous domains and malformed/truncated output. Keep
sample/deterministic evidence separate from pending owner live validation.
