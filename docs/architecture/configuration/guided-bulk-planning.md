# Gap C — Approved Template-Based Configuration Planning (Target Design)

**Status:** Engineer-approved target design, **not implemented**. Supersedes the earlier two-stage Requests/Parameters workbook and offline-only C1–C4 proposal from Issue #88 (closed, not planned; PR #89 closed unmerged). Existing `orbitflow.configuration` v1 remains as documented in [offline-plans.md](offline-plans.md). This document is the authoritative target for the replacement implementation issue; it does not claim live apply exists.

> **Current implementation milestone (owner decision, 2026-10-12):** Implement and user-validate **Templates 1–8 (C3750X/C3850X)** first. The detailed signed-off requirements are in [approved-catalyst-templates.md](approved-catalyst-templates.md), and supersede generic statements on those eight templates below. Templates 9–22 remain an **unapproved detailed-design backlog** despite inclusion in this high-level catalogue; do not implement or claim to have validated them in this milestone. Existing Issue #91 and PR #92 carry the revision. No live device modification or automatic merge.
>
> **Single-plan decision workflow:** The owner's later revision replaces the standalone v2 review command/module and separate reviewed artifacts. The **generated plan workbook** is the sole per-row Pending/Approve/Reject surface, alongside immutable digest-bound plan JSON under `outputs/runs/configuration/` by default. A spreadsheet decision alone never authorizes execution; future consumption must validate linkage/integrity. Earlier "review workbook", "reviewer" and "approvals/rejections yield reviewed plans" passages below describe the superseded initial design where inconsistent with this paragraph.

## Operator journey

1. Engineer opens a single **input workbook** with an **Introduction** sheet linking to each template worksheet. Each template links back to Introduction. No template IDs, methodology IDs (M01–M08), row-order numbers, separate Requests/Parameters/Choices workbooks or change-order fields are required from the engineer.
2. Engineer fills function-specific rows on **one worksheet per device family and operation**. Required columns include management IP and operation parameters. Inline examples, validation and dropdowns should make requirements obvious. Template metadata and stable internal row IDs belong to the application, not the engineer's input.
3. For **predefined templates**, OrbitFlow connects read-only to each targeted device using shared DeviceContext, DeviceSession, device-execution and observation capabilities. Retrieve **current** configuration, normalized facts, exact sanitized source excerpts, evidence references, and observation timestamps; do not treat historical inventory snapshots as proof of live state. Reuse InterfaceService, VlanService, saved-configuration facts, and family AuditResolver where appropriate. Do not duplicate vendor parsing or change fixed compliance policies to serve planning. Failed/unavailable/ambiguous checks are explicit, not fabricated absence.
4. The **Manual CLI** worksheet is different: **offline-only**, with **no target connection or existing configuration collection**. Engineer explicitly supplies device IP, platform, scope/mode and multiline CLI. Preserve user-authored command text; perform bounded input and structural checks, label **Not Live Validated / Impact Unknown**, and never claim semantic safety. Inventory snapshot lookup may be optional but is not live evidence.
5. Planning service deterministically compares requests with observed facts and creates proposed CLI, no-ops, conflicts, dependencies and impact findings. Generate **reviewable CLI even for known changes/conflicts** (e.g. differing VLAN name), but never treat unresolved prerequisites, unknown outcomes or inconsistent ownership as deployment-ready.
6. Output a **review workbook retaining function-specific sheets and original input columns**, adding existing configuration evidence (for predefined templates), proposed multiline CLI, live-validation result, consistency and dependencies, observation timestamp, and **Engineer Decision = Pending / Approve / Reject**, plus summary/findings. No-op rows are visible. Rejected dependencies trigger re-planning/revalidation and invalidate affected digests.
7. Approvals bind exact immutable, versioned Change Plans, commands, target, provenance and collected evidence via canonical digest. Ordering for the **same device** is **worksheets left-to-right, then rows top-to-bottom**; detect cross-sheet/interface/shared-resource overlap and do not silently resolve it. Expose that rule prominently in Introduction. CLI and Excel are thin adapters; a future API/web adapter invokes the same catalogue, observation, planning and review services.

This phase **does not apply, save, commit, back up, roll back or modify devices**. Connections for predefined templates are strictly read-only. Manual CLI has the **same ordinary offline engineer approval workflow** as predefined templates, with no special second approver/SSO requirement in this phase; its unknown effects stay explicit. An offline approval never authorizes future live application.

## Approved catalogue — 22 templates

| Family | Input worksheet/function | Notes |
|---|---|---|
| C3750X | VLAN Database | Required VLAN ID + name; live evidence; missing=create; matching=no-op; differing name=rename proposal + warning |
| C3750X | Access Port | Required interface + access VLAN; optional description; live access/trunk/ownership checks |
| C3750X | Trunk Port | Add/Remove/Replace allowed VLANs; optional native VLAN/description; explicit trunk mode for new/conversion, encapsulation dot1q where required |
| C3750X | Interface Description | Required nonempty description including spaces; existing interfaces/port-channels only |
| C3850X | VLAN Database | Same VLAN name and conflict review semantics |
| C3850X | Access Port | Explicit access-mode setup; live VLAN and ownership validation |
| C3850X | Trunk Port | Add/Remove/Replace; new trunk uses `switchport mode trunk`, without C3750X encapsulation selector |
| C3850X | Interface Description | Supports spaces; no implicit deletion |
| ME3600X | VLAN Database | Explicit global VLAN objects, required name |
| ME3600X | EVC | Tagged/untagged and QinQ; service instance, bridge-domain, symmetric pop tag rewrite; bridge-domain's **global VLAN must exist** or have an earlier approved creation dependency; generate draft on missing prerequisite |
| ME3600X | Interface Description | Physical or supported aggregate target |
| ASR920 | EVC | **Inline binding only** under interface service instance; dot1q/QinQ/untagged and qualified rewrite. Existing global binding is an observed consistency conflict, not an automatically migrated change |
| ASR920 | Interface Description | Preserve EVC config |
| NCS540 | L2VPN | L2transport subinterface, encapsulation and bridge-group/domain attachment. Numeric VLAN validity comes from valid BD→existing L2 subinterface→dot1q relationship, not BD name |
| NCS540 | Interface Description | Physical and existing routed/L2transport subinterfaces |
| EdgeSwitch | VLAN Database | Explicit VLAN DB, required name, quoted when rendering names with spaces |
| EdgeSwitch | VLAN Port | Participation/tagging/PVID; Add/Remove/Replace. Access uses `vlan participation include X` + `vlan pvid X` (no tagging-disable command). Remove tagged VLAN uses `no vlan tagging X` then `vlan participation exclude X` |
| EdgeSwitch | Interface Description | Quoted description supporting spaces |
| NE05E | VLAN Database | Explicit `vlan` / `vlan batch` existence, required VLAN description; VSI references not substitutes |
| NE05E | Subinterface VSI | Single-tag dot1q termination or vlan-type dot1q; existing VSI mandatory for deployment-ready plan; QinQ and VSI creation out of v1 |
| NE05E | Interface Description | Physical, existing subinterface, Eth-Trunk |
| All families | Manual CLI | Offline-only, no device connection, explicit platform and CLI mode/scope; unknown effects retained |

ASR920 deliberately has **no VLAN database/standalone BD creation template**: a valid forwarding VLAN requires at least one valid interface service-instance attachment, whether inline or globally observed. The ASR920 template **renders inline only** and identifies existing global bindings as consistency findings.

For all Cisco families, render configuration-mode entry as `configure terminal`; EdgeSwitch uses `configure`; Huawei VRP uses `system-view`. Separate IOS-XR future commit from planning. Do not use compliance policy's numeric **2–4001** range to restrict configuration inputs: validate actual vendor/platform supported VLAN ID/range and reserved-ID rules. Interface descriptions preserve spaces and case; missing required descriptions are invalid. Blank **optional** descriptions preserve existing text. For ME3600X EVC use the bridge-domain VLAN as the global-database prerequisite, not the outer ingress tag.

## Services, evidence, consistency and plan semantics

- Catalogue lives in versioned repository definitions with stable IDs, typed schemas, capability gates, renderers and conflict/dependency rules, independent of Excel.
- Shared live-observation orchestrator performs read-only per-device collection and stores sanitized exact command output/evidence plus normalized facts, source references and time; avoid duplicate SSH sessions and redundant collections for rows targeting the same device.
- Planning uses the original device snapshot and projects preceding approved row effects in declared worksheet/row order, without claiming those effects already exist on device. Recompute dependencies when engineer rejects a row.
- Retain original CLI and **proposed commands** for conflicting-but-understood changes, including VLAN name/description changes, access/trunk conversions, VLAN removals, and changed EVC settings. Mark service impact and warnings clearly.
- Block deployment-readiness (not necessarily CLI rendering) for unresolved parent/port-channel ownership, ambiguous interface or service bindings, absent necessary global VLAN/VSI, unreviewed migrations, or stale evidence. Known global-vs-inline ASR920 EVC conflicts are reported, never silently rewritten.
- Manual CLI input remains literal and offline. Its consistency is `not_evaluated`; detect obvious overlaps without pretending full command-effect understanding. Approve/Reject/Pending alone does not make unsafe/unknown changes execution-authorized.
- Keep raw credential/secret-bearing output and user commands out of unprotected workbooks, artifacts, spools and logs. Sanitize evidence consistently. Preserve evidence references and hashes/digests securely; immutable plan changes invalidate approval.
- Existing v1 Change Plan allowlists, authority and digest protections remain unchanged until an explicitly versioned backwards-compatible extension is implemented and tested. The existing v1 operation `ensure_vlan_present` need not silently acquire rename semantics: use an explicit rename-aware planned action.

## Future apply policy — out of scope

C5/C6 require separate approvals and lab/live testing. Shared per-device execution, up to five concurrent devices by default, sequential ordered operations per device, and fresh preflight just before applying. Connection/unreachable/identification failure **before commands could be sent** may skip/continue. Unsafe preflight, command/commit failure, verification failure or unknown outcome **after send may have begun** pauses further dispatch after safe current-wave handling; explicitly reconcile and authorize resume. Never blind-retry config or auto-rollback. A separate explicit execution authorization is required even for an approved plan.

## Acceptance for replacement implementation issue

Deterministic fixtures for all 22 template schemas, correct vendor CLI/context, live collector/audit reuse, missing or ambiguous evidence, evidence freshness, mismatched name review, VLAN creation/dependencies, ASR920 global-binding consistency, EdgeSwitch tagged removal syntax, input navigation/ordering, mixed same-device rows, row rejection, no-op results, plan digest invalidation, manual offline no-network guarantee, secret redaction and no device mutations. Include offline fake-session validation of live-observation orchestration, and user-controlled live read-only smoke tests before claiming operational validation.

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
