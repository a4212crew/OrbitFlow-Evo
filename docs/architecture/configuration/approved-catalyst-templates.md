# Configuration v2 — Approved Catalyst Template Requirements (Templates 1–8)

## Issue #152 policy correction

Disjoint ME3600X/ASR920 EVCs independently derive safe parent setup from observed
state, including empty parents; compatible setup/descriptions require no sibling
approval. Contradictory descriptions, duplicate SIs, ingress overlap, uncertain
state and aggregation ownership still block. Predefined non-Ubiquiti templates
have no VLAN Database approval/synchronization dependencies and never implicitly
create VLANs. Earlier contrary prerequisite statements below are superseded.
EdgeSwitch genuine prerequisites and immutable approval/fresh execution gates remain.
See [current behavior and validation commands](../../user_manual/bulk-configuration-planning.md).

**Decision status:** User signed off Templates **1–8 of 22** on 2026-10-12. This is a **requirements baseline, not an implementation/validation claim**. User explicitly elected to implement and test these eight templates first. Templates 9–22 remain in the high-level catalogue but require the same four-step review and final sign-off before implementation. Issue #91 / existing PR #92 is the implementation/revision vehicle; do not merge without explicit owner approval.

**Precedence:** This page supplements [guided-bulk-planning.md](guided-bulk-planning.md). Where old generic target language differs for these eight templates or the owner-approved single-workbook decision workflow, this more recent approved detail takes precedence. Existing v1 Change Plan/approval protections remain intact.

## Shared architecture and workbook rules

- **Scope:** Offline deterministic *planning only* for C3750X/C3850X `VLAN Database`, `Access Port`, `Trunk Port` and `Interface Description`. Read-only live observation is allowed; device configuration, save, apply, commit, rollback or auto-merge is not.
- **Layers:** Reuse shared DeviceContext/session/device execution, InterfaceService, VlanService, Cisco vendor config-facts and existing compliance/audit resolvers. Do not implement duplicate SSH, VLAN parser, VLAN L2 methodology, concurrency pool or policy reinterpretation in Excel/planning.
- **Excel:** One Introduction sheet plus function-specific worksheets, original input columns preserved. Each original row retains validation status, field-specific error details (including relevant row references), sanitized **original complete configuration evidence**, proposed CLI, findings/warnings/blockers, resolved target, No-op, and engineer decision as relevant. Errors on one row do not abort safe other rows. Input must be retained even when invalid; never generate CLI for invalid input. Preserve ordered source statements and terminating `!` for interface stanzas. Global VLAN ranges must remain as originally declared in evidence, while semantic lookup expands their IDs.
- **Single decision surface (owner-approved Issue #91 revision):** Generated plan Excel itself carries `Pending / Approve / Reject`. No separate reviewed workbook/JSON, standalone review command, or independent v2 review workflow/module. Matching plan JSON and workbook go under `outputs/runs/configuration/` by default; caller-selected paths obey safe/no-overwrite policy. Workbook edits do **not** grant apply authority or silently mutate/re-sign immutable digest-bound plan content. Future consuming workflow must validate request/row identity, digest and decisions; no live apply here.
- **Safety:** Secret-bearing CLI/evidence is sanitized; never put credentials in issue/docs/workbooks/logs. Incomplete/ambiguous observations and ownership cannot be represented as verified clean state. Unrelated existing VLAN/switchport audit issues must not prevent description-only changes when safely classifiable. Planner warnings remain separate from blocking findings. Source CLI is inspectable and planned CLI is deterministic.
- **Ordering/conflicts:** Same-device order is workbook sheets left-to-right then rows top-to-bottom. Do not silently resolve conflicting requests for the same resource. Block duplicate conflicting same-device/interface/VLAN targets with error details on **both** rows; trunk conflict detection is after physical→Port-channel owner resolution. Interface descriptions target the exact user-entered interface and are never redirected.
- **Common CLI:** IOS/IOS-XE begins `configure terminal` and ends `end`. No implicit `no shutdown`. Blank optional description/native VLAN leaves the existing value unchanged. A true complete match is No-op and generates **no CLI**. For understood but high-risk conversions, retain proposed CLI while blocking plan approval/deployment readiness.

## Templates 1 and 5: VLAN Database — C3750X / C3850X

**Excel:** Required `management_ip`, `vlan_id`, `name`; no action column, implicit create / rename / No-op. VLAN IDs 1–4094 except reserved 1002–1005. VLAN name length ≤32 and permitted characters `A-Z a-z 0-9 _ . : -` (no spaces on **either** platform; C3850X current code needs tightening). Reject invalid inputs on original Excel row. Block conflicting same-device/VLAN requests and reference conflicting rows.

**Parsing:** Parse global declarations including `vlan 1035-1109` so any member VLAN, e.g. 1040, counts as present. Retain original declaration as evidence. Add reusable read-only shared `show vlan id <ID>` lookup in VlanService/Cisco adapter used on both platforms. Supported example output is Cisco table with header `VLAN Name Status Ports`, row `445 PPPoE active Te1/0/1, ...` and wrapped member-port continuation lines; parse existence, VLAN name, operational status; optional port/type/MTU facts must not drive create/rename decisions. Distinguish explicit not-found from rejected command, error or unparseable output. Operational lookup output is internal, **not** displayed as the Existing Evidence column.

**Fallback amendment (applies to both platforms):** If `show vlan id` fails, use reliably collected running-config VLAN evidence, annotate nonblocking `VLAN_LOOKUP_FALLBACK` and do not claim live operational verification. If configuration shows VLAN, compare the existing name and propose rename or No-op; if configuration reliably shows no declaration, creation may be proposed with fallback warning. If running configuration is also unavailable/unreliable, block as unknown—not absent. If a VLAN is inactive/suspended, warn without treating it as missing or blocking an otherwise valid name change.

**CLI:** `configure terminal / vlan <ID> / name <NAME> / end` for create and rename. When existing name differs, generate rename CLI with `VLAN_RENAME_IMPACT` warning; never delete/recreate. Exact match gives No-op/empty CLI. Unrelated interface inconsistencies do not block the VLAN Database request.

## Templates 2 and 6: Access Port — C3750X / C3850X

**Excel:** Required `management_ip`, `interface` (full canonical Cisco name, no abbreviation), `vlan_id`; optional `description` (blank means preserve existing); no action column. Validate VLAN using platform limits/reservations. Block conflicting duplicate target-interface rows, identifying Excel row numbers.

**Parsing/classification:** Parse explicit `switchport mode access`, `switchport access vlan <ID>`, description, status and full original interface stanza (declaration through `!`, order intact). Explicit switchport mode is authoritative; explicit access with leftover trunk commands remains access with residual warning, **not** trunk. An access VLAN configured without explicit mode is usable with a warning; missing description is nonblocking. Dynamic auto/desirable and empty/unconfigured interface may be planned with warning as appropriate. Already-configured access No-op requires explicit access-VLAN evidence, not an inferred default. Missing requested VLAN is nonblocking: reuse shared operational lookup with approved running-config fallback, warn and allow proposed CLI. No VLAN Database approval dependency is created for Catalyst Access Port requests (Issue #152).

**Safety:** Proposed access configuration from explicit trunk or routed `no switchport` is shown but **blocked from approval/readiness** with conversion finding. Preserve existing shutdown and unrelated settings; never auto-enable. Owner-approved *later amendment to both templates*: for a physical member with `channel-group N`, identify `Port-channelN`, preserve physical + logical evidence, **block independent Access Port change** (`PHYSICAL_PORT_CHANNEL_MEMBER`) and never silently redirect or apply.

**Full intended CLI when change required:** `configure terminal / interface <FullName> / [description <text> if provided] / switchport / switchport mode access / switchport access vlan <ID> / end`. Emit the full intended access configuration even when only VLAN or description differs. Do not generate on complete match. A blocked conversion may retain proposed CLI as an inspection-only proposal.

## Templates 3 and 7: Trunk Port — C3750X / C3850X

**Excel:** Required `management_ip`, `interface` (full name), `action` exactly Add/Replace/Remove, `vlans` (comma-separated VLAN IDs/ranges). Optional `native_vlan` and `description` preserve current values when blank. Validate ranges and VLAN IDs using platform limits. Classify ordered requests after resolution to the same effective interface/Port-channel and report both input rows: compatible Add then Add and Replace then Remove are warnings under the overlap amendment below; incompatible intent and safety prerequisites remain blockers.

**Parsing:** Explicit `switchport mode trunk` is authoritative; explicit access with leftover trunk allow commands stays access. Parse **all** `switchport trunk allowed vlan` base, `add`, `remove` (and recognized supported operation variants) in their original sequence. Expand `130-135` into six values; reconstruct the *effective* set after ordered changes rather than trusting the first statement. Missing explicit allowed list on a valid Cisco trunk means effective `ALL`, not empty; preserve ALL/exclusions semantics without pretending no VLANs exist. Native VLAN tracked separately; default VLAN 1 when omitted. Detect `channel-group N`, use logical `Port-channelN` as membership and CLI owner, show both original complete interface stanzas and `TARGET_RESOLVED_TO_PORT_CHANNEL`. Distinguish absent/mismatched Port-channel owner as a genuine blocker, not a fabricated interface. Preserve original declarations, residual commands, description and shutdown.

**Add:** An **explicit** `switchport trunk allowed vlan ...` baseline on the resolved configuration owner is required; without it, block and recommend Replace. When changes are needed, emit `switchport trunk allowed vlan add <all requested IDs>` including IDs already present. A fully matching Add is a No-op and emits nothing.

**Replace:** Complete desired allowed list using `switchport trunk allowed vlan <desired list>`. Can configure an unconfigured interface. Replacing current trunk may remove unrelated allowed VLANs: show service-impact warning. Access→trunk conversion emits full proposal but **blocks approval/readiness**. Existing shutdown remains unchanged.

**Remove:** Explicit allowed-list baseline **not required**. Emit `switchport trunk allowed vlan remove <IDs>` with service-impact warning; when no baseline, correctly interpret default ALL and resulting ALL-minus-removed membership. An absent requested VLAN is No-op if all other fields match. Native-VLAN changes/removals require impact warning and correct state handling. Do not treat empty explicit list and default ALL as the same.

**Generated CLI:** On existing trunk, emit needed allowed-list command and any explicitly requested differing native VLAN/description changes; preserve blank optional settings. With a conversion or an unconfigured interface, include `switchport`, `switchport mode trunk`, allowed list and explicit optional fields. **C3750X** adds `switchport trunk encapsulation dot1q` when applicable for new/conversion trunk. **C3850X never requires or emits that encapsulation selector**; its absence is not a parser warning. No-op when full requested state matches. Proposed CLI always targets resolved Port-channel where applicable.

## Templates 4 and 8: Interface Description — C3750X / C3850X

**Excel:** Required `management_ip`, `interface` (full Cisco name), `description` (nonblank, may contain spaces). Support existing physical, Port-channel and logical interfaces (e.g. `Vlan1035`). Same-device target duplicates with differing descriptions are blocked and cross-referenced on affected rows. No action column; no blank-as-delete mode.

**Parsing/target:** Read existing description or recognise it as absent; retain complete original target-interface stanza through `!`. Exact entered target is authoritative: a physical member's description remains separate from the Port-channel's description; **never redirect**. Port-channel configuration may be supplementary context only. Existing VLAN/switchport inconsistencies unrelated to a description-only change are nonblocking warnings; missing/ambiguous target evidence is not waived.

**CLI:** `configure terminal / interface <ExactFullName> / description <TEXT> / end`. Create missing or replace different description; matching description yields No-op/empty CLI. No generic service-impact warning for a description-only change; never change VLAN/mode/IP/shutdown or other commands.

## Milestone 1 — Implementation and validation gates

1. Codex implements **only Templates 1–8 and their necessary shared foundations**, reusing existing Issue #91 / `codex/issue-91` / PR #92. Keep catalogue placeholders for 9–22 intact if present, but **do not claim** they are newly approved/tested. Do not break functioning existing v2 or v1 behaviour.
2. Add deterministic fixtures for both platforms: range-based VLAN identification, operational `show vlan id` including wrapped ports/not-found/errors/fallback, rename/inactive/No-op; switchport explicit/dynamic/residual/routed modes and shutdown; full original evidence and secret sanitization; Port-channel access blocking versus trunk redirection, aggregate conflict; sequential add/remove with range and default ALL; Add no-baseline; Remove no-baseline; conversion blocking; full access CLI; exact description target; duplicate row references, workbook row retention, output paths, approvals/digest integrity.
3. Run relevant full deterministic tests, then provide reproducible command/help and sample input for **operator-controlled live read-only tests** on C3750X and C3850X. No production writes. Capture sample result/workbook, compare observed evidence, generated CLI and warnings; test multi-row + one-row failure isolation. Validation outcome remains **pending** until operator exercises it and signs off.
4. Atlas reviews PR #92 and issues marked `<!-- atlas-review -->` revision comments on Issue #91 before `codex-revise` label as needed. Controller owns Codex/branch/worktree/PR cycle; user controls merge. Do not implement Templates 9–22 before their separate review and user approval.
5. **Resume requirement sessions only after milestone-1 validation:** Template 9 ME3600X VLAN Database begins at **Step 1 parser**, then Step 2 Excel inputs, Step 3 CLI/output, Step 4 final sign-off. Ask explicit approval at each stage; update requirements register; avoid GitHub writes during the conversational review, except when user explicitly authorizes them.

## Notes on implementation vs decisions

Existing configuration v2 work in PR #92 is not proof that each approved scenario passes. The shared Cisco VLAN collector currently reads `show running-config`, not the new `show vlan id` lookup. The simplified normalized trunk membership used by planning needs integration with ordered audit-resolution evidence. The current evidence projection does not guarantee every original interface statement and `!`. Approval and template requirements are independent of live operational validation.

## Owner-approved ordered overlap amendment (2026-10-12)

For Templates 1-8, evaluate same-device intent in worksheet left-to-right,
then exact Excel row top-to-bottom order. Original read-only evidence stays
unchanged; preceding nonblocked, non-Reject intent supplies projected state for
later comparison and CLI/No-op generation. Pending is proposed intent, not an
approval. Rejecting an earlier row re-evaluates later rows against remaining intent.

Compatible Access Port -> Interface Description and Trunk Add -> Add or
Replace -> Remove pairs carry `ORDERED_RESOURCE_OVERLAP_WARNING` on both rows.
The later description wins, including when Access emits its own optional
description in its full approved CLI. Add still requires an explicit baseline;
Remove uses the preceding Replace result and retains service-impact warnings.
Identical description requests may sequentially produce a later No-op.

Different description-only values, Access versus Trunk intent, other unapproved
pairs, unresolved owners or any individual safety blocker retain blocking
`ORDERED_RESOURCE_OVERLAP`. Physical trunk members are compared after audited
Port-channel resolution; description targets remain exact. Missing/stale/unreliable
evidence and conversion/baseline prerequisites are never waived by overlap.
Warnings alone mean `Consistency=consistent`; blockers mean `unresolved`.
No-op describes membership/field equality only: `ADD_REQUIRES_EXPLICIT_BASELINE`
remains independently prohibited even when membership already matches.

Both immutable JSON and the single plan workbook retain overlap classification,
earlier/later worksheet names and exact row numbers, explanation and chronological
effective result. Workbook `Ordered Overlap Details` and `Projected State` are
protected planning output. `observed_allowed_state` retains original audit state;
`allowed_state` is the evaluation baseline and `desired_allowed_state` is proposed
membership. Blocked projected output is inspection-only and never feeds successors.
Digest linkage, Pending/Approve/Reject and no-overwrite outputs under
`outputs/runs/configuration/` remain unchanged. None of this grants apply authority.
Owner must repeat read-only planning on C3750X and C3850X and explicitly validate
revised worksheets before milestone completion. Templates 9-22 remain pending.


### Issue #149 / PR #150 owner revision (2026-10-25)

The earlier child-to-parent trunk redirect and broad compatible-stanza merge
language is superseded. Confirmed physical child forwarding requests block with
`NOT_ALLOW_ON_CHILD_PORT_CHANNEL`; select the logical parent explicitly instead.
Descriptions remain exact-target. EdgeSwitch addport-only stanzas preceding a
settings stanza contribute relationship evidence only; the subsequent settings
stanza supplies consistency input. Repeated actual settings remain ambiguous,
missing settings remain unknown, and actual observed duplicates still block.
Original ordered facts/source lines and all addport commands are retained.
Preparation independently rejects historical approved redirects; fresh execution
rechecks ownership. Historical codes/artifacts remain readable without bypassing
current safety. Approval, digest, backup, transport and verification gates persist.
See [owner validation matrix](../../user_manual/aggregation-validation.md).
Deterministic regression evidence does not establish live-device acceptance.
