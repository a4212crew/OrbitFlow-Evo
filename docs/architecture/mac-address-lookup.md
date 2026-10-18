# MAC address lookup contract

Issue #130 adds an observation-only backend and terminal workflow. Deterministic
sample validation is separate from owner-operated device validation, which is pending.

`MacService.collect(session, context, cli=None)` is single-device and independent
of interface, VLAN and bridge collection. Its pure vendor parser produces immutable
entries, one table total and optional scoped totals. MACs use lowercase colon notation;
original type, destination, scope and status/detail remain available. A supplied table
total is authoritative; absent totals use parsed entry count including CPU/static/remote.
Scoped Huawei slot counts remain scoped and do not replace a whole-table count.
No count comparison, mismatch warning, count command or resynchronization is performed.

`BridgeDomainService` independently observes the approved XR summary command.
Its snapshot retains group/name/internal ID/state, ACs, BVI references, neighbor/PW
pairs, backup flags and supplied counts. Lookups return every exact candidate.
Only a unique destination join establishes domain context. Internal IDs, EFP IDs,
subinterface suffixes, PW IDs and digits in names never establish numeric VLANs.

`resolve_attachment` consumes actual interface observations or typed interface configuration blocks. Canonical join keys
remain unchanged; presentation expands Cisco/Huawei aliases by platform. Exact
EFP/subinterface identity remains in the entry while a separately observed or configured parent
may resolve physically. Aggregates retain ownership; no member is selected.
CPU, routed/logical, remote and unresolved destinations have blank physical names.
EdgeSwitch non-0/x destinations remain unresolved pending stronger identity evidence.

`enrich` composes these snapshots with existing normalized VLAN observations.
Classic switch numeric domains and Huawei numeric VLAN scopes match directly.
EVC requires exact parent/service-instance saved facts, explicit encapsulation and
matching local/global BD binding; aggregate profiles cannot prove EFP identity.
XR requires a unique operational domain join and explicit matching AC mappings.
Huawei named services require exact interface/service mapping. Unknown mappings
stay visible in Details and cannot pass a VLAN filter. Port type comes from shared
profiles; only established access/trunk/hybrid appears in the main sheet, with
EVC/service/routed semantics retained separately. Compliance policy is untouched.

The application connects once per device, resolves one DeviceContext, borrows one
CLI, and isolates optional enrichment failures. Shared execution owns scheduling
and result-spool writing. Streaming Excel export consumes normalized per-device
payloads; collection and export memory are bounded by the largest device payload
plus bounded workers, rather than all MAC rows. Normalized spools are retained
for offline recovery. Workers never write workbooks. Known input credentials
are redacted before persistence; errors contain categories, never exception text.

The console adds main item 7, MAC Address Lookup, with exactly Search MAC Address,
List All MAC Addresses and Back; Exit becomes 8. Search validates MAC/IP and exact
workbook row resolution before network confirmation and needs no concurrency
prompt. List accepts numeric VLAN, all/subset rows and per-run concurrency 1-5,
blank=1. No new profile keys are introduced. Backend collectors and recovery are
not submenu actions. Direct Python/CLI recovery remains supported.

See the [operator guide](../user_manual/mac-address-lookup.md) and
[API](../operations/mac-address-lookup-api.md) for concrete inputs and limits.
