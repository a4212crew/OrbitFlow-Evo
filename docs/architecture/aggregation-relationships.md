# Cross-Vendor Aggregation Relationships — Architecture and Acceptance Contract

**Status:** Owner-approved merged design authority. Issue #147 implements the read-only capability and reporting integration; owner-operated live validation remains pending.
**Scope:** Read-only LAG/aggregation membership observation, interface report presentation and sanitized configuration evidence.  
**Non-goals:** LACP health/compliance, VLAN/service inference from membership, configuration apply, replacement of existing audit/planning resolvers.

## 1. Authority and existing implementation boundaries

Follow [repository rules](../../AGENTS.md), [interface collector skill](../../.agents/skills/interface-collector/SKILL.md), [reporting skill](../../.agents/skills/device-reporting/SKILL.md) and [documentation management](../../.agents/skills/documentation-management/SKILL.md).

Pre-Issue #147 baseline, inspected on 2026-10-24: `src/orbitflow/reporting.py` joins existing `InterfaceService` and `VlanService` outputs, has 14 `Interfaces` columns and writes `Interfaces`, `VLAN_Database`, `Run_Errors`. `src/orbitflow/excel_output.py` rejects Excel cell contents over 32,767 characters and atomically replaces reports. `src/orbitflow/compliance/resolvers.py` has aggregation-related VLAN audit behavior which **must remain intact** until separately approved and regression-validated. Planning v2 shares configuration facts and compliance/audit observations. Issue #147 adds the separate aggregation capability, three LAG columns and conditional evidence overflow without retiring that legacy behavior.

## 2. Device-family relationship templates

| Family | Logical parent | Physical member configuration | Supporting observation |
|---|---|---|---|
| Cisco C3750X IOS | `Port-channel<N>` | `channel-group <N>` | `show etherchannel summary` |
| Cisco C3850 IOS-XE | `Port-channel<N>` | `channel-group <N>` | `show etherchannel summary` |
| Cisco ME3600X IOS | `Port-channel<N>` | `channel-group <N>` | `show etherchannel summary` |
| Cisco ASR920 IOS-XE | `Port-channel<N>` | `channel-group <N>` | `show etherchannel summary`, including compact/wrapped layout |
| Cisco NCS540 IOS-XR | `Bundle-Ether<N>` / `BE<N>` | `bundle id <N>` | `show bundle brief`, `show interfaces Bundle-Ether<N>` |
| Huawei VRP | `Eth-Trunk<N>` | `eth-trunk <N>` | `display eth-trunk`, `display interface brief` |
| Ubiquiti EdgeSwitch | `interface lag N` / logical `3/N` | `addport 3/N` in physical-port stanza | `show port-channel brief` |

Treat the physical binding in the correct interface stanza as authoritative; operational lists corroborate it. Do not infer membership from descriptions, LACP configuration or up/down state. Preserve down/shutdown members. Zero-member parents remain visible when independently observed even when empty; incomplete member evidence is **unknown**, not proved empty. Relationships are device-scoped. Normalize aliases to a single canonical interface identity and retain original names as evidence.

EdgeSwitch 1.9.3-lite observed `3/1` to `3/6` as logical interfaces, including zero-member LAGs; do not infer an operator explicitly provisioned each default interface. Supporting `Local` and `Partner` tables in Huawei output must not double-count members. IOS-XR bundle brief `0/0/2` can mean two configured members but zero active, **not** zero members.

## 3. Proposed normalized observation contract

Proposed `AggregationSnapshot` per device:
- device identity, platform/family, timestamp and completeness of member/config collection;
- canonical aggregate parent and ordered/set-normalized physical member identities;
- logical aggregate subinterface identities as a separate relation, **never** physical children;
- direct configuration bindings, optional operational corroboration and source provenance;
- conflicting/missing evidence and nonfatal parser/collection problems;
- references to original **sanitized** configuration stanzas, rather than duplicating large strings.

Use a dedicated vendor-aware aggregation collector/parser behind a reusable read-only capability, sharing `DeviceContext`, `DeviceCLI`, transport and the per-device worker. Higher-level reporting must consume normalized relationships and never reinterpret vendor CLI.

## 4. Reporting contract

In `Interfaces`, insert exactly three columns after `Interface` and before `Description`:
`LAG`, `LAG Relationship`, `LAG Member`.

- Parent: `Yes`, `Parent`, comma-separated physical member source-configuration heading names (blank for confirmed empty).
- Physical child: `Yes`, `Child`, base parent source-configuration heading name.
- Standalone interface and aggregate subinterface: three columns blank. Existing rows and service mappings remain unchanged.
- Avoid creating interface rows solely from service references. Preserve existing `VLAN_Database` and `Run_Errors` schemas.
- Audit and update position-based tagged VLAN/bridge domain/service mapping compaction in `reporting.py` when inserting columns; otherwise old data can shift into incorrect post-processing.

Failure isolation: an unavailable aggregation stage cannot silently classify members as standalone. Preserve per-device error provenance and existing successful interface/VLAN output wherever safely possible.

## 5. Full configuration evidence projection

Each original sanitized stanza is stored once, referenced by stable run/device/interface/evidence IDs.

- Selecting aggregate parent: own complete base interface stanza, **all** matching aggregate subinterface stanzas, complete physical-member interface stanzas.
- Selecting physical member: own complete stanza and its **base** aggregate parent stanza only; no sibling/member list expansion and no aggregate subinterface expansion.
- Selecting a logical aggregate subinterface: its own configuration stays with the existing interface/service mapping capability; no LAG child designation.
- Include unrelated configuration within selected stanzas (descriptions, LACP, service instances, EVC/VLAN, BPDU, QoS etc.) after effective sensitive-value sanitization.

**Global overflow design (approved at template-review level):** keep current three-sheet workbook normally; conditionally create one consolidated `Configuration_Evidence` sheet when any projected sanitized configuration evidence cannot fit Excel's 32,767-character cell limit. Recommended columns: `Device Name`, `Device IP`, `Interface`, `Evidence ID`, `Evidence Part`, `Total Parts`, `Configuration Evidence`. Use ordered chunks <=30,000 characters and verify lossless reconstruction of the sanitized string. Avoid silent truncation. Normal-size evidence remains accessible through its references whether or not the extra sheet exists. Existing non-evidence cell overflow still fails safely.

Carry evidence references/payload through the shared bounded `ResultSpool`; offline regeneration must not reconnect or lose the data. Retain current atomic workbook replacement and failure recovery guarantees. No raw secrets or production device logs in fixtures, commits or development Issues.

## 6. Regression matrix / acceptance gates

| Test class | Required examples |
|---|---|
| IOS / XE | C3750X/C3850 group numbering, descriptions disagreeing with config, down members |
| ME3600X | zero-member `Port-channel1`; wrapped members; preserve EVC subtrees |
| ASR920 | compact `1Po1(RU)LACP` and `Gi... (bndl)` rows; multiple parents, family variant |
| IOS-XR | `BE1` ↔ `Bundle-Ether1`; two configured/down members; 0/0/2 not zero; exclude `BE1.445` etc from physical members |
| Huawei | `Eth-Trunk1..3` ↔ GE0/2/2, GE0/2/1, GE0/2/0; avoid Local/Partner duplicates |
| EdgeSwitch | populated `3/2` = 0/12+0/16; six empty parents on other devices; canonical `lag 2` ↔ `3/2` |
| Cross-cutting | configured empty vs unknown; status-independent membership; device isolation; interrupted/partial output; sanitized stanzas; overflow/reassembly; spool retry |
| Compatibility | existing inventory, interfaces, VLAN database, interface/VLAN reporting and compaction, audit/compliance, configuration backup, planning v1/v2, execution, console, transport and supported public APIs remain unchanged unless explicitly authorized |

Codex must add deterministic sanitized fixtures/tests in an **owner-authorized development Issue**, update the monthly devlog and impacted user manuals/API/README/function descriptions, and supply precise Linux/Windows automated and owner-operated read-only live validation commands for review. Live validation is owner-operated. No merge without explicit owner approval.

## 7. Historical readiness decisions (resolved for authorized Issue #147)

1. Review and approve this normalized schema's exposed public/API shape and any compatibility versioning required for report/spool consumers.
2. Establish live controller/worktree and outstanding owner-validation status immediately before any new Codex Issue; GitHub searches alone cannot prove the serial slot is free.
3. Decide whether the whole read-only collector+report/evidence integration is one manageable Codex task after test/dependency assessment; otherwise split into **sequential** tasks.
4. Reconcile console eligibility and documented commands against actual implementation during the authorized development work.
5. Keep legacy audit aggregation logic; any eventual replacement is a separate design and owner decision.

**Gate:** This document authorizes no code changes, development Issue, device configuration action, or PR merge.


## 8. Issue #147 implementation mapping

`AggregationService.collect(session, context, *, cli=None, interfaces=())` borrows
shared CLI/session ownership; `vendors/aggregation.py` parses explicit full-config
bindings without changing compliance or planning. Supporting operational tables
are not collected in this revision: binding truth comes from configuration,
never active-member counters, Local/Partner lists or description text. Missing
configuration terminators produce unknown membership completeness and an
aggregation-stage error, while affirmative bindings and other capability rows
survive. Family live validation is pending.

Each sanitized stanza occurs once in the device spool payload. Normal workbooks
store selected stanzas once in Interface-cell comments with run/target/interface
IDs; parent and child comments reference their exact projections. Unobserved
related stanzas are stored beside the first referencing real interface. If a
projection/store exceeds 32,767 characters, the device evidence is stored once
in the consolidated conditional `Configuration_Evidence` sheet in ordered
30,000-character chunks. Comments then carry references only. See the
[operator/API manual](../user_manual/device-interface-vlan-report.md#lag-relationships-issue-147)
for lookup, recovery, exact commands and owner acceptance expectations.

The earlier readiness checklist records pre-implementation provenance, not an
outstanding request to create another task. Legacy aggregation retirement and
any merge remain outside this implementation authorization.

### First owner Windows run revision

The 2026-10-24 owner console export preserved interface/VLAN output but reported
aggregation failures on EdgeSwitch and NCS540. Parser revisions accept trailing
EXEC prompts after balanced FASTPATH closure and indented XR final terminators;
these constructed regression shapes await comparison with minimal sanitized owner
snippets. Unknown nested contexts remain incomplete, never proven empty. Safe
rejected/unavailable/unsupported/incomplete error classes retain ValueError
compatibility. Existing spool cleanup/recovery and legacy aggregation semantics
are unchanged; OneDrive cleanup was deferred. Revised owner validation is pending.


### Owner naming clarification (Issue #147 / PR #148)

Canonical device-scoped identities remain authoritative for joins and evidence
references. Separate `configuration_names` records exact source heading spelling
for `LAG Member`; `Interface` retains InterfaceService display names. Compatible
repeated aliases select the lexicographically smallest actual heading, retaining
all original headers in sanitized evidence. Missing headings use an explicitly
qualified canonical fallback, never a fabricated as-configured label.

### Owner capture-boundary clarification (2026-10-24)

### Issue #147 revision 4: FASTPATH global service commands

The earlier service-as-section interpretation is superseded: `service unms`
and `service unms key ...` are global commands, not nested mode openers.
After each interface/line section closes, the single final `exit` closes
`configure`. The owner-described 1.9.3-lite ending needs no additional outer
exit. Missing final exit remains incomplete even with a returned prompt.
Explicit physical `addport` bindings, repeated stanzas and exact heading names
remain preserved; legacy VLAN/audit/planning/execution behavior is unchanged.
Synthetic regressions cover populated 3/1 with repeated 0/49 and 0/51 stanzas,
six empty parents, truncation, missing section/final exits and extra exits.
Owner EdgeSwitch mini-live validation, followed by NCS540, remains pending.
