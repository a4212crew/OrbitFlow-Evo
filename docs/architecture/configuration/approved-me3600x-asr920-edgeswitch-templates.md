# Configuration v2 — Approved ME3600X, ASR920 and EdgeSwitch Templates 9–16

## Issue #152 policy correction

Issue #154 extends the separate explicitly confirmed executor to Templates 9–13;
the planning-only scope statements below continue to govern planning, not that
authorized executor. Workbook approval alone never applies changes. See the
[execution manual](../../user_manual/configuration-execution.md#me3600x-and-asr920-issue-154)
for fresh execution gates, recreation impact, outputs and pending lab validation.

ME3600X Template 10 assigns empty-parent trunk/allowed-none initialization to
only the earliest executable Approved row in workbook order. Later approved disjoint
rows omit both commands; Pending, Reject and Blocked rows never provide readiness.
An observed trunk/allowed-none parent requires no setup. ASR920 Template 12 is
unchanged. Decisions/order changes require renewed digest-bound preparation and
confirmation. Execution never rewrites approved CLI: fresh empty/partially initialized
parents block rows without approved setup; an initialized parent blocks a row still
carrying setup (`EVC_PARENT_DRIFT`). Failed/Unknown setup is never presumed successful;
only fresh compatible state permits independent continuation, and lost synchronization
stops device writes. Presence-only EVC post-verification, partial save and no retry remain.

Disjoint EVCs remain independently reviewable where safe. Contradictory descriptions, duplicate SIs, ingress overlap, uncertain
state and aggregation ownership still block. Predefined non-Ubiquiti templates
have no VLAN Database approval/synchronization dependencies and never implicitly
create VLANs. Earlier contrary prerequisite statements below are superseded.
EdgeSwitch genuine prerequisites and immutable approval/fresh execution gates remain.
See [current behavior and validation commands](../../user_manual/bulk-configuration-planning.md).

**Decision baseline:** Owner-approved design discussions through 2026-10-13. This is a requirements contract, **not** a claim that these templates are implemented or live validated. Supersedes conflicting generic statements in `guided-bulk-planning.md` for Templates 9–16. Templates 1–8 remain governed by `approved-catalyst-templates.md`. Templates 17–22 still need individual detailed sign-off. Only read-only observation and offline deterministic configuration planning are in scope. Never apply/save/commit to network devices; engineer approval in a spreadsheet is not execution authority.

## Shared planning/workbook requirements

- Use existing v2 input workbook with Introduction, per-template examples of **supported and unsupported input**, requirements, drop-downs and generated CLI illustrations. Preserve original row input, original complete sanitized CLI evidence, findings, differences, warnings, proposed commands, observation timestamps and single Pending/Approve/Reject decision. Same-device ordering: worksheet left-to-right, row top-to-bottom. No separate v2 review module.
- Preserve full interface source stanza including child stanzas and terminating `!` (Cisco) or `exit` (EdgeSwitch); preserve unknown nonsecret unrelated commands as evidence. Do not let input failures on one row abort safe other rows. Differentiate absence, unknown/unreliable evidence and operational state; running-config fallback is valid only when collection is complete/reliable. Do not conflate interface VLAN participation with global VLAN existence.
- Share typed vendor VLAN/EVC facts and platform-specific adapters; no parallel parser implementation in planning, no independent SSH/execution pool, no change to existing compliance rules. Retain compact original VLAN expression for display/CLI but normalize all member VLAN IDs for overlap/membership checks. A range `2-444` includes **every ID from 2 through 444**, inclusive; list `2-444,446-544` omits 445. QinQ matching uses (outer,inner) tag pairs, not outer tag alone.
- Keep parent interface description and service-instance description separate. Blank optional input on an EVC **recreation** means omit that child setting; blank optional physical description means leave existing parent description unchanged.
- Explicit destructive proposals may be generated as planning output, with observable impact and omitted-settings warnings, never applied. Block incomplete/untrusted device evidence and materially unsafe ownership or tag overlap; unrelated settings preserved.

## Template 9 — ME3600X VLAN Database

Inputs: `management_ip`, `vlan_id`, `name` (all required, one VLAN per row). Same create/rename/no-op semantics as the approved Catalyst VLAN Database templates. VLAN IDs 1–4094 excluding reserved 1002–1005; names <=32 ASCII `[A-Za-z0-9_.:-]` without spaces. Read-only `show running-config` and `show vlan id <ID>`. Correctly identify explicit absence vs CLI failure; full reliable running-config may prove existence or absence when operational lookup fails, annotate `VLAN_LOOKUP_FALLBACK`; unknown state blocks. Successfully collected empty global database means absence. Existing matching name = No-op, different name = rename with `VLAN_RENAME_IMPACT`; operational inactive state is informational. EVC/service-instance/BD references are **not** global VLAN database declarations. Do not change interface/EVC as part of this template.

## Templates 10 and 12 — ME3600X and ASR920 EVC

### Detection and evidence

- **ME3600X:** EVC parent requires **both** `switchport mode trunk` and `switchport trunk allowed vlan none`; it may have zero or more service instances. Recognize normal trunk, access, unconfigured and LAG-owned parents distinctly. For an *empty compatible parent*, allow required EVC initialization with these two commands; never silently convert a configured incompatible parent.
- **ASR920:** EVC detected from `service instance <ID> ethernet` under its interface; **no ME switchport lines** required. Empty compatible interface may receive required EVC setup (e.g. `no ip address` if evidenced and required), but never guess `no shutdown`, MTU or spanning-tree changes; do not alter an existing routed/incompatible interface without approved conversion.
- Parse every service-instance stanza; preserve complete parent CLI through `!`, and each nested child's description, encapsulation, rewrite, bridge-domain, split-horizon. Retain MTU, admin state, policies, Port-channel ownership. Live read-only request: `show ethernet service instance id <ID> interface <INTERFACE> detail`, with platform-safe command syntax; recognize an explicit `does not exist` response only for the requested ID/interface. Parse operational encapsulation/rewrite/BD/Up/Down; Down is informational. Unparseable operational output is not proof of absence; reconcile with reliable running-config evidence.
- Service instance ID, outer match, inner match, pushed VLAN and bridge domain are all **independent**. For example service instance 3000 may match dot1q 4000 and bind BD 4000. Parse `bridge-domain 445 split-horizon group 0` with `group=0` distinctly from absent; support `bridge-domain 700` with no group.

### Excel contract

Per EVC worksheet: `management_ip`, `interface`, `service_instance_id`, `encapsulation` (Untagged/Dot1q/QinQ), `outer_vlan`, `inner_vlan`, `rewrite`, `push_vlan`, `bridge_domain`, `split_horizon_group`, `description` (service instance), `interface_description` (parent). Required: management_ip, interface, service_instance_id, encapsulation and bridge_domain. Outer required for tagged; inner required for QinQ; both blank for untagged. Rewrite optional; `push_vlan` required only for Push. Service instance ID is not automatically the outer VLAN or BD. VLAN match fields accept fixed IDs, inclusive ranges and lists where supported; `second-dot1q any` is normalized to `1-4094`. Validate numeric bounds/known expression syntax. Explicit group 0 is valid.

The Introduction and both EVC sheets MUST provide these mapping examples:
| Encapsulation selector | Outer | Inner | Generated CLI |
|---|---|---|---|
| Untagged | blank | blank | `encapsulation untagged` |
| Dot1q | `445` | blank | `encapsulation dot1q 445` |
| Dot1q | `100-200` | blank | `encapsulation dot1q 100-200` |
| Dot1q | `2-444,446-544` | blank | `encapsulation dot1q 2-444,446-544` |
| QinQ | `300` | `200` | `encapsulation dot1q 300 second-dot1q 200` |
| QinQ | `100` | `1-4094` | `encapsulation dot1q 100 second-dot1q 1-4094` |

### Rewrite operations and compatibility (both platforms)

Supported selections: **None**, **Pop 1 symmetric**, **Pop 2 symmetric**, **Push dot1q** (no symmetric), **Push dot1q symmetric**. Treat explicit non-symmetric Push differently from symmetric. Extract pushed VLAN separately as `push_vlan`, not as an ingress match VLAN. Device detail output `Rewrite: ingress tag push dot1q 1402 vlan-type 0x8100 symmetric` and config `rewrite ingress tag push dot1q 1402 symmetric` are equivalent with ethertype annotation. Never infer a rewrite just because one normally accompanies an EVC.

| Encapsulation | No rewrite | Pop 1 symmetric | Pop 2 symmetric | Push dot1q (non-symmetric) | Push dot1q symmetric |
|---|---|---|---|---|---|
| Untagged | Supported as omission | Unsupported/untested; do not assume | Unsupported/untested | Supported | Supported |
| Dot1q single outer | No rewrite not independently lab-proven | Supported | **Rejected** | Supported | Supported |
| Dot1q outer range/list | Supported | **Rejected** | **Rejected** | Supported | Supported |
| QinQ fixed inner | No rewrite not independently lab-proven | Supported | Supported | **Rejected** | Supported |
| QinQ inner range `1-4094` | Supported | Supported | **Rejected** | **Rejected** | Supported |

Fail closed on unsupported or genuinely untested combinations with explicit blocker; do not quietly substitute a different rewrite. Do not infer that all Cisco platform/release variants support untested syntaxes. Valid example range/list: `encapsulation dot1q 2-444,446-544,546-744,747-1100,1120-2448,2450-3998` with `rewrite ingress tag push dot1q 1402 symmetric`. Push examples also include `encapsulation untagged` + `rewrite ingress tag push dot1q 100` (and symmetric); single dot1q 500 with symmetric or non-symmetric push; QinQ fixed `300 second-dot1q 200` with Push symmetric 100; QinQ `100 second-dot1q 1-4094` with Push symmetric 200. For each syntax, include valid and invalid examples in workbook help.

### Approved CLI and safety contract

Every EVC input row represents a **complete desired service-instance specification**, not a partial incremental update. Regardless of whether the target instance currently exists, generate in this order:
```text
interface GigabitEthernet0/0/6
 no service instance 2000
 service instance 2000 ethernet
  encapsulation dot1q 2-444,446-544
  rewrite ingress tag push dot1q 1402 symmetric
  bridge-domain 2000 split-horizon group 0
```
Use exactly `no service instance <ID>` (no `ethernet` suffix) as explicitly approved. If an existing instance already matches, still generate Remove/Recreate, **not No-op**; warn `SERVICE_INSTANCE_RECREATE_IMPACT` and list any omitted old child commands. Never remove unrelated service instances or mutate parent commands except explicitly supplied interface description/approved empty-parent EVC initialization. Same-interface overlapping ingress matches block unless a verified coexistence rule applies. Physical LAG ownership/incompatible interfaces block. Shutdown state retained. Missing ME3600X global VLANs referenced by a BD produce a nonblocking planning warning, not a VLAN Database approval prerequisite (Issue #152); ASR920 uses inline `bridge-domain` under its service instance, with no automatic global binding migration. Unknown reliable state blocks but confirmed target absence does not.

## Template 11 and 13 — ME3600X / ASR920 Interface Description

Inputs: `management_ip`, `interface`, `description` required. Full physical or supported Port-channel target; physical Port-channel member may be explicitly described without redirecting to the aggregate. On existing or valid empty interfaces, No-op if description already equals target, otherwise generate only `interface <name>` + `description <text>`; preserve spaces and all VLAN/EVC/BD/MTU/admin/STP/other config. Missing/ambiguous interface or unreliable config blocks. Complete existing parent stanza evidence required.

## Template 14 — EdgeSwitch VLAN Database

Inputs: `management_ip`, `vlan_id`, `name` required; **one VLAN ID per row**, 2–4093, valid quoted name including spaces within device length limit (32). Primary `show vlan <ID>`: header `VLAN ID: 445`, `VLAN Name: PPPoE`, `VLAN Type: Static` means existing; explicit `VLAN does not exist.` is confirmed absent. If command fails or result inconclusive, complete reliable `show running-config` VLAN database serves as fallback for existence/absence/name; conflicts between reliable observations block, ambiguous/incomplete state blocks `VLAN_STATE_UNKNOWN`. Parse e.g. `vlan 445,545,745-746,901,2436-2444,2446,2449,4000-4001` into each ID; quoted `vlan name 901 "VLAN 901"` preserved.
Existing equal name => No-op; existing different => rename `vlan database` / `vlan name 445 "NEW NAME"` / `exit` with warning; confirmed absent => `vlan database` / `vlan 901` / `vlan name 901 "VLAN 901"` / `exit`. No interface participation/tagging/PVID changes. Running-config fallback not equivalent to a fresh operational check; annotate source.

## Template 15 — EdgeSwitch VLAN Port

Inputs: `management_ip`, `interface`, `action` (**Add/Change** or **Remove** only), `tagged_vlans` (single ID, comma/range/list), `pvid` (optional for Add/Change), optional `description`. **Remove** must contain tagged_vlans and a **blank** pvid; any Remove+pvid blocks with `REMOVE_OPERATION_CANNOT_INCLUDE_PVID`. **Add/Change** requires at least tagged_vlans or pvid, can have tagged only, pvid only or both. No `vlan_id`, `untagged_vlans`, `mode`, `replace_untagged`, nor Replace action. One operation per row; to replace tagging, explicitly Remove then Add/Change in separate ordered rows. **PVID and tagged_vlans may include the same VLAN ID; this is valid** and must not produce conflict.

Read complete `interface <port>` through matching `exit`, including unrelated storm control, BPDU, MTU, PoE and protected-port commands; preserve them as evidence and do not modify them. For VLAN clauses, retain independent `pvid`, included membership, excluded membership and configured tagging even if `vlan tagging 746` coexists with `vlan participation exclude 746` — do not intersect/drop the tagged fact. Expand ranges (`2436-2444` represents each ID 2436…2444). Parse `show vlan <ID>` operational table by port into separate **Current**, **Configured**, and **Tagging** fields; Current Exclude vs Configured Include is evidence, not automatic misconfiguration or change instruction. Reliable running-config is fallback for configured facts.

Rendering:
- Add/Change tagged: `vlan participation include <tagged_vlans>` then `vlan tagging <tagged_vlans>`, only necessary differences.
- Add/Change PVID: `vlan participation include <pvid>` if required, then `vlan pvid <pvid>`; **no** `no vlan tagging` merely because PVID is supplied. If tagged and PVID same, retain both independent effects.
- Remove tagged: `no vlan tagging <tagged_vlans>` first, then `vlan participation exclude <tagged_vlans>`, omitting already-satisfied commands. A removal targeting the existing PVID VLAN blocks until an earlier row explicitly changes the PVID.
- VLAN absent from **global database** does **not** block this template: allow Add/Change or Remove, report `VLAN_NOT_IN_DATABASE` informatively. Do not auto-create global VLAN.
- LAG-owner checks, conflicting row dependencies, unknown parent evidence, no-op and service-impact warnings; retain all unrelated VLAN membership/config. `description` changes only if requested.

## Template 16 — EdgeSwitch Interface Description

Inputs: `management_ip`, `interface`, `description` required. Support physical and LAG interfaces and descriptions with spaces/quoting; read complete interface stanza through `exit`; exact target only, No-op on match, else render description-only under specified interface with quoted value. Preserve VLAN participation, tagging, PVID and unrelated config. Unknown interface/evidence blocks.

## Deterministic validation requirements

Fixtures for ME3600X and ASR920 parent detection, VLAN list expansion, QinQ pair matching/any normalization, five rewrite options and compatibility matrix, operational detail output including inserted ethertype, absent/down cases, group zero vs absent, empty parent versus owned/incompatible parent, existing matching child still recreated, destructive impact/omitted settings, global BD prerequisite and unrelated child preservation. Fixtures for EdgeSwitch multi-command full stanza, exclude+tag same VLAN, Current/Configured/Tagging table, VLAN lookups/fallback, Add/Change PVID-only, PVID=tagged, Remove+pvid blocker, no global VLAN precondition, order and no Replace. Workbook Introduction/input validation/roundtrip, error isolation, plan JSON/excel digest linkage, owner-approved v2 single decision surface, secret sanitization, shared observation/audit regressions, no live write and legacy v1 coverage. Explicitly report untested hardware/firmware cases for owner-run live read-only tests.
