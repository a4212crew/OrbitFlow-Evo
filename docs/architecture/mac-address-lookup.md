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
pairs, backup flags and supplied counts. Summary ACs/VFIs/PWs/PBBs/VNIs totals
and reported up counts are preserved without recalculation or comparisons. Empty
AC/PW sections are valid; malformed attachment rows or unsupported attachment
sections fail explicitly. Empty domains retain summary rows in the workbook. Lookups return every exact candidate.
Only a unique destination join establishes domain context. Internal IDs, EFP IDs,
subinterface suffixes, PW IDs and digits in names never establish numeric VLANs.

`resolve_attachment` consumes actual interface observations or typed interface configuration blocks. Canonical join keys
remain unchanged; presentation expands Cisco/Huawei aliases by platform. Exact
EFP/subinterface identity remains in the entry while a separately observed or configured parent
may resolve physically. Aggregates retain ownership; no member is selected.
CPU, routed/logical, remote and unresolved destinations have blank physical names.
EdgeSwitch MAC destinations `3/N` resolve to logical `lag N` only when one exact
independently observed aggregate or typed interface configuration block exists.
Absent or ambiguous identities remain unresolved; member references alone are
insufficient. No physical member is selected; `5/1` remains nonphysical.

`enrich` composes these snapshots with existing normalized VLAN observations.
Classic switch numeric domains and Huawei numeric VLAN scopes match directly.
ME3600X/ASR920 explicit numeric VLAN-table rows retain their VLAN identity; EFP and
BD-table rows require explicit service encapsulation. The parser preserves the
VLAN-versus-BD table scope, so numeric BD values cannot become VLANs.
EVC requires exact parent/service-instance saved facts, explicit encapsulation and
matching local/global BD binding; aggregate profiles cannot prove EFP identity.
XR retains the complete operational group/domain identity. VLAN proof requires a unique
operational destination join, an exact matching normalized bridge-domain
service_binding_name (group/domain), and explicit matching AC encapsulation mappings.
This applies to local and remote destinations; conflicting groups and ambiguous
attachments remain unknown even when domain names match.
Huawei named services require exact interface/service mapping. Unknown mappings
stay visible in Details and cannot pass a VLAN filter. Port type comes from shared
profiles; only established access/trunk/hybrid appears in the main sheet, with
EVC/service/routed semantics retained separately. A MAC-only untagged XR AC fallback requires a unique operational domain join,
exact configured group/domain agreement for that l2transport AC, and exactly one
distinct explicit numeric dot1q VLAN across uniquely bound configured peers in
that domain. Zero/multiple tags or conflicting bindings remain Unknown. This is
a lookup association and does not classify untagged ingress as tagged; shared XR
VLAN and bridge observation are unchanged.

`forwarding_classifications` projects immutable interface type/owner records from
the existing family resolver without evaluating compliance policy. MAC enrichment
uses this contract for ME3600X/ASR920/EdgeSwitch; EVC displays as trunk, access and
hybrid retain their meaning, and review displays Unknown. Audit BD membership is
never treated as an ingress VLAN. EdgeSwitch explicit trunk intent without any
participation/tagging/PVID facts is preserved by observation and audit, with empty
effective membership and no policy trigger; it does not imply All VLAN.

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

Search renders each selected keyed detail observation as a cohesive record, including
its normalized full attachment, MAC, group/domain, mapping, physical identity, port
type and classification. Raw attachment text is retained separately in Details.


Issue #132 / PR #133 owner revision supersedes the previous six-column main-sheet
promise: `Interface Description` is appended after `Mac address`; supporting sheets
are unchanged. Descriptions join by exact canonical identity to the verified
physical or logical aggregate owner, using InterfaceService `port_description`
and/or VlanService interface `description`. EFP/subinterface rows use the resolved
parent description; child and arbitrary aggregate-member text is not inherited.
Conflicting nonempty owner descriptions, missing evidence, CPU/remote/Drop/SVI,
and unresolved destinations produce blank descriptions. Optional evidence failures
preserve MAC collection and counts. No description is inferred from VLAN/BD,
suffix or peer identifiers. Sanitization/redaction and literal-text Excel cells
also apply to descriptions beginning with `=`, `+`, `-` or `@`.
Offline recovery preserves descriptions; historical six-value spool rows export
with a blank seventh cell. Automated regressions cover supported families and
recovery; operator read-only Linux/Windows validation remains pending.


Issue #132 / PR #133 review corrections: the policy-free shared classification
projection now classifies configured XR ACs by explicit encapsulation and one exact
BG/BD binding: untagged is access, dot1q is trunk. Existing parents combine child
roles (access/trunk/hybrid); invalid or conflicting child evidence is review/Unknown,
and routed interfaces retain routed classification. Exact AC type takes precedence
over the parent type for a MAC on that AC. This does not change numeric compliance
membership, shared VLAN observation or BridgeDomainService. No peer VLAN association
is used to claim tagged ingress.

IOS/IOS-XE parsing accepts the exact repeated `Nile Mac Address Entries` banner
and repeated column headers while preserving each row's VLAN/BD scope; other invalid
rows still fail. The main sheet's existing `Physical Interface name` column shows
the resolved physical/logical owner when proven, otherwise the normalized original
attachment (including remote tuples, Drop and unresolved LAG/IP-like destinations).
This fallback is display only: Details physical identity stays blank when unresolved,
raw attachment is retained, and descriptions still require exact owner evidence.
Seven-column output and historical six-column spool recovery remain supported.
