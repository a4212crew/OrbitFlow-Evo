# Configuration v2 template operator reference

Use this reference with [bulk planning commands, output review and owner read-only smoke tests](bulk-configuration-planning.md). Templates 1–8 follow the [Catalyst signed-off contract](../architecture/configuration/approved-catalyst-templates.md); 9–16 follow the [ME3600X/ASR920/EdgeSwitch signed-off contract](../architecture/configuration/approved-me3600x-asr920-edgeswitch-templates.md). These contracts take precedence over generic catalogue notes. Templates 17–22 below are **catalogue/provisional, not owner-approved or live-validated**. Their descriptions report existing code, not a promise of device support.

## Rules for every worksheet

Fill from row 3. Each scenario below uses `management_ip=192.0.2.91`; substitute your authorized target. Unlisted optional fields are blank. All listed columns are the complete input schema, in workbook order. Do not add old schema columns. Required means nonempty. Blank optional parent/interface text preserves it; blank EVC child inputs omit the old child setting. Fields are case-sensitive; IDs are integers, not floats, formulas, expressions or booleans. Management IP accepts IPv4/IPv6 literals, not hostnames. CLI illustrations use `/` between separate command lines; interface identifiers containing `/` remain intact. They are proposals only and must never be pasted to production equipment by this workflow.

Same-device order is sheet left-to-right, then row top-to-bottom. Earlier nonblocked, non-Reject proposals supply projected state; Pending supplies intent but cannot satisfy an approval dependency. Changing a decision recalculates later readiness. Original input/evidence remains original. Compatible overlap warns on both rows; unsafe/unknown overlap blocks and cites exact sheet/row. Two differing database names for the same ID, differing description-only values, or repeated same-ID EVC recreation remain conflicting intent. Rejecting a prerequisite cannot make successors ready. Unrelated devices and invalid rows remain isolated.

Every predefined row requires fresh, reliable, correctly identified read-only evidence. Missing/stale/ambiguous observations block. Confirmed absence is different from unknown. For approved templates, running-config fallback requires complete collection, is annotated, and never claims an operational check succeeded. Approved full sanitized source/line evidence includes unknown unrelated nonsecret commands, Cisco nested children and ending `!`, or EdgeSwitch interface through `exit`; provisional-family limitations are listed separately below. No synthetic interfaces are invented from service references. Description-only operations retain recognized unrelated VLAN findings as warnings; unsafe identity/target evidence still blocks. No approval authorizes apply/save/commit. One immutable digest-bound JSON and one plan workbook are the review artifacts; edit only Pending/Approve/Reject. Regenerate old workbooks when output columns change; existing artifacts are never overwritten.

Text is printable ASCII, normally 1–256 characters; multiline Manual CLI is 1–16000 characters and permits CR/LF/tab. Secrets, credential words, URL schemes, control characters and formulas are forbidden. Descriptions/names reject embedded double quotes, semicolons and backslashes; EdgeSwitch renderer adds required quotes. For ordinary non-EVC/non-VLAN-Port fields surrounding whitespace is rejected. Safe EVC/EdgeSwitch port descriptions retain supplied printable whitespace. Do not include credentials even in a description. Empty required descriptions are invalid; no implicit deletion is offered.

## Shared scenario results and dependencies

A No-op has empty CLI; safety blockers can still coexist with No-op. Warnings alone remain consistent. A draft CLI on a blocked row is inspection-only. Shutdown, MTU, PoE, storm-control, policies and unrelated membership remain unchanged unless an approved input explicitly requests its field. No template automatically enables a port or saves configuration.

Database rows: reliable absence creates, equal existing name No-ops, different name renames with `VLAN_RENAME_IMPACT`; no delete/recreate. Cisco/Edge operational inactive state warns. CLI rejection/inconclusive lookup uses `VLAN_LOOKUP_FALLBACK` only with reliable complete config; contradictory sources block. A failed lookup plus unreliable config blocks `VLAN_STATE_UNKNOWN`. Distinct global objects are not inferred from EVC/BD/VSI references. Earlier database creation can be a dependency; it must be approved for readiness where required.

Description rows: existing empty/different description produces description-only CLI; exact match No-ops. Missing/ambiguous target or unreliable evidence blocks. Physical LAG-member descriptions stay on the entered physical target. Same identical description twice makes the later row No-op and carries overlap warning; differing descriptions on description-only rows block. A preceding approved access/EVC/port request then description is compatible for approved families and the final text wins.

## Template 1 — C3750X VLAN Database

Status: signed-off detailed contract; deterministic validation only, owner live validation pending.

| Input column | Requirement | Allowed values / forbidden values / example |
|---|---|---|
| `management_ip` | Required | IPv4/IPv6 literal; e.g. 192.0.2.91. No hostname, credentials or URL. |
| `vlan_id` | Required | One integer VLAN ID; family bounds below. No list/range, ALL, 0 or 4095. |
| `name` | Required | Family-specific VLAN name limits below; no empty name, quotes, semicolon or backslash. |

Bounds: 1–4094 excluding 1002–1005; names =32 ASCII [A-Za-z0-9_.:-], no spaces. VLAN 445,545 or 200-100 in vlan_id is invalid. Empty/overlong names block; Customer Site is invalid on Cisco, valid on EdgeSwitch/NE05E within length bounds.

| Filled input (plus management_ip) and observed state | Expected result |
|---|---|
| vlan_id=901; name=Customer; absent global VLAN | `configure terminal / vlan 901 / name Customer / end` |
| vlan_id=901; name=Customer; existing name Customer | No-op, empty CLI |
| vlan_id=901; name=Customer; existing name Old | Rename with VLAN_RENAME_IMPACT; same CLI, no deletion |
| vlan_id=1002; name=Customer | Invalid input, no CLI |
| vlan_id=901; name=Customer; unknown evidence | Blocked; never infer absent |

Evidence: full reliable running-config global VLAN declaration/list/name plus `show vlan id 901`. Explicit absence creates; operational failure/inconclusive output falls back only to complete config, annotated VLAN_LOOKUP_FALLBACK. Conflicting reliable names/existence block. Inactive/down is informational. An empty reliably collected database proves absence. Interface membership and service references do not establish global existence. Earlier approved creation supplies prerequisites to later ME EVC; conflicting same-ID requests block and cite rows. EdgeSwitch port membership never requires global creation. No interface command is emitted here.

## Template 2 — C3750X Access Port

Status: signed-off detailed contract; deterministic validation only, owner live validation pending.

| Input column | Requirement | Allowed values / forbidden values / example |
|---|---|---|
| `management_ip` | Required | IPv4/IPv6 literal; e.g. 192.0.2.91. No hostname, credentials or URL. |
| `interface` | Required | Existing explicit interface identifier; platform details and sample below. No whitespace except EdgeSwitch lag N; no shell metacharacters. |
| `vlan_id` | Required | One integer VLAN ID; family bounds below. No list/range, ALL, 0 or 4095. |
| `description` | Optional | Printable ASCII text with spaces/case, e.g. Customer Site Alpha; no secrets, quotes, semicolon or backslash. Blank optional preserves existing description. |

Interface: full canonical Cisco name, e.g. GigabitEthernet1/0/1; no abbreviated Gi names. vlan_id: one integer 1–4094 excluding 1002–1005. Optional description preserves blank; input has no action/native VLAN.

| Filled input (plus management_ip) and observed state | Expected result |
|---|---|
| interface=GigabitEthernet1/0/1; vlan_id=445; description=Customer; empty/dynamic/access different | `configure terminal / interface GigabitEthernet1/0/1 / description Customer / switchport / switchport mode access / switchport access vlan 445 / end` |
| same interface; vlan_id=445; description blank; explicit access VLAN already 445 | No-op; existing description preserved |
| vlan_id=445; missing global VLAN | Nonblocking GLOBAL_VLAN_REQUIRED; proposed access CLI, no auto-create |
| same input after earlier Pending/Reject database prerequisite | Dependency not approved; cannot claim readiness |
| same input on configured trunk or routed no switchport | Show proposal; ACCESS_CONVERSION_BLOCKED |
| same input on channel-group member | PHYSICAL_PORT_CHANNEL_MEMBER; no redirection |
| vlan_id=1002 or interface=Gi1/0/1 | Invalid, no CLI |

Evidence: full physical stanza and logical Port-channel evidence where owned; approved show vlan id lookup/config fallback for target VLAN. Explicit access mode wins over residual trunk statements, which warn. Access VLAN without explicit mode/empty/dynamic mode warns; inferred default VLAN alone is not a complete match. Shutdown retained. Earlier Access then Description is compatible, warns both rows, final description wins. Access versus Trunk on same effective resource blocks. Unknown syntax/owner/evidence is never waived by a No-op.

## Template 3 — C3750X Trunk Port

Status: signed-off detailed contract; deterministic validation only, owner live validation pending.

| Input column | Requirement | Allowed values / forbidden values / example |
|---|---|---|
| `management_ip` | Required | IPv4/IPv6 literal; e.g. 192.0.2.91. No hostname, credentials or URL. |
| `interface` | Required | Existing explicit interface identifier; platform details and sample below. No whitespace except EdgeSwitch lag N; no shell metacharacters. |
| `action` | Required | Exact family-specific selection below; no lowercase aliases. |
| `vlans` | Required | Comma-separated integers/inclusive ranges, e.g. 445,545-546. Nonempty, no duplicates, reversed ranges, ALL or NONE input. API uses a list of integer IDs. |
| `native_vlan` | Optional | One integer in Catalyst VLAN bounds. Blank retains existing/default native VLAN; separate from allowed membership. |
| `description` | Optional | Printable ASCII text with spaces/case, e.g. Customer Site Alpha; no secrets, quotes, semicolon or backslash. Blank optional preserves existing description. |

Interface: full canonical Cisco name. action exactly Add, Remove or Replace; vlans one/comma/inclusive ranges with no duplicates, 1–4094 excluding 1002–1005. ALL/NONE are observed symbolic states, **not input values**. native_vlan same bounds, optional and independent; description optional. Blank optional inputs preserve native/default VLAN 1 and description.

| Filled input (plus management_ip and interface=GigabitEthernet1/0/2) and state | Expected CLI/result |
|---|---|
| action=Add; vlans=445,545; explicit baseline=445 | `configure terminal / interface GigabitEthernet1/0/2 / switchport trunk allowed vlan add 445,545 / end` (all requested IDs) |
| action=Add; vlans=445; explicit baseline contains 445 | No-op if all other requested fields match |
| action=Add; vlans=445; no explicit allowed baseline (ALL) | ADD_REQUIRES_EXPLICIT_BASELINE, even if No-op; use Replace |
| action=Remove; vlans=445; no baseline (ALL) | `switchport trunk allowed vlan remove 445` in configuration/interface/end; projected ALL except 445; service warning |
| action=Remove; vlans=445; explicit baseline=545 | No-op |
| action=Replace; vlans=445,545-546; existing trunk | `switchport trunk allowed vlan 445,545,546` in configuration/interface/end; service-impact warning for changes |
| action=Replace; vlans=445; empty interface | Setup `switchport / switchport trunk encapsulation dot1q / switchport mode trunk` before `switchport trunk allowed vlan 445` |
| action=Replace; vlans=445; existing access | Full setup proposal, TRUNK_CONVERSION_BLOCKED |
| action=Add; vlans=445; native_vlan=545; description=Customer; tags match | Only requested differing native/description commands; no redundant allowed command |
| action=Remove; vlans=445; native_vlan=445 | NATIVE_VLAN_IMPACT warning; inspect unchanged versus requested native state carefully |
| action=Replace; vlans=ALL or 200-100 or 1002 | Invalid, no CLI |

Evidence: reconstruct all original allowed base/add/remove/except statements in source order; preserve ALL and NONE distinctly. The collector requests operational VLAN lookups for input IDs; trunk evaluation uses configured allowed-list state and does not require global database existence or auto-create VLANs. The global-VLAN warning and database dependency rule described for Access do not add a trunk database prerequisite. Resolve physical members to audited Port-channel owner, retain both stanzas and TARGET_RESOLVED_TO_PORT_CHANNEL; absent/conflicting owner blocks. C3850X never emits an encapsulation selector. C3750X adds it only for new/conversion trunks. Optional differing native VLAN/description render only when requested. No shutdown/MTU changes. Compatible Add?Add and Replace?Remove use projected state and overlap warnings; other unapproved overlapping pairs block. Unknown baseline syntax blocks, never treated as an empty list.

## Template 4 — C3750X Description

Status: signed-off detailed contract; deterministic validation only, owner live validation pending.

| Input column | Requirement | Allowed values / forbidden values / example |
|---|---|---|
| `management_ip` | Required | IPv4/IPv6 literal; e.g. 192.0.2.91. No hostname, credentials or URL. |
| `interface` | Required | Existing explicit interface identifier; platform details and sample below. No whitespace except EdgeSwitch lag N; no shell metacharacters. |
| `description` | Required | Printable ASCII text with spaces/case, e.g. Customer Site Alpha; no secrets, quotes, semicolon or backslash. Blank optional preserves existing description. |

Required description; target example `GigabitEthernet1/0/1`. Catalyst requires full canonical FastEthernet/GigabitEthernet/TenGigabitEthernet/FortyGigabitEthernet/HundredGigE/Port-channel/Vlan/Loopback names with numeric slash components and optional numeric suffix; abbreviations like Gi1/0/1 are invalid. Other catalogue identifiers accept [A-Za-z0-9][A-Za-z0-9./:-]* (EdgeSwitch also lag N), but actual unambiguous observed existence is mandatory. Physical and supported logical/aggregate targets stay exact; no LAG redirect.

| Filled input (plus management_ip) and observed state | Expected result |
|---|---|
| interface=GigabitEthernet1/0/1; description=Customer Site Alpha; old/empty text | `configure terminal / interface GigabitEthernet1/0/1 / description Customer Site Alpha / end` |
| same input; matching text | No-op |
| same input; physical member of aggregate | Change exact member description only |
| description blank, target missing/ambiguous, or unreliable source | Invalid input or evidence blocker |
| same target in two rows; identical description | Later No-op, compatible overlap warning for approved families |
| same target in two rows; different descriptions | Ordered overlap blocker |

Evidence: exact interface declaration plus preserved configuration and original observed description, never redirected to aggregate. Approved Cisco keeps complete parent/child stanza through `!`; EdgeSwitch through `exit`, including unrelated PoE/MTU/STP/VLAN/PVID. VLAN defects can warn but no VLAN repair occurs. NCS540 provisional renderer retains `l2transport` when evidenced, and rejects unresolved declarations; NE05E remains provisional, with existing scoped facts rather than a new full-stanza guarantee. Provisional family overlap behavior is conservative, so do not assume the approved-family duplicate warning exemption.

## Template 5 — C3850X VLAN Database

Status: signed-off detailed contract; deterministic validation only, owner live validation pending.

| Input column | Requirement | Allowed values / forbidden values / example |
|---|---|---|
| `management_ip` | Required | IPv4/IPv6 literal; e.g. 192.0.2.91. No hostname, credentials or URL. |
| `vlan_id` | Required | One integer VLAN ID; family bounds below. No list/range, ALL, 0 or 4095. |
| `name` | Required | Family-specific VLAN name limits below; no empty name, quotes, semicolon or backslash. |

Bounds: 1–4094 excluding 1002–1005; names =32 ASCII [A-Za-z0-9_.:-], no spaces. VLAN 445,545 or 200-100 in vlan_id is invalid. Empty/overlong names block; Customer Site is invalid on Cisco, valid on EdgeSwitch/NE05E within length bounds.

| Filled input (plus management_ip) and observed state | Expected result |
|---|---|
| vlan_id=901; name=Customer; absent global VLAN | `configure terminal / vlan 901 / name Customer / end` |
| vlan_id=901; name=Customer; existing name Customer | No-op, empty CLI |
| vlan_id=901; name=Customer; existing name Old | Rename with VLAN_RENAME_IMPACT; same CLI, no deletion |
| vlan_id=1002; name=Customer | Invalid input, no CLI |
| vlan_id=901; name=Customer; unknown evidence | Blocked; never infer absent |

Evidence: full reliable running-config global VLAN declaration/list/name plus `show vlan id 901`. Explicit absence creates; operational failure/inconclusive output falls back only to complete config, annotated VLAN_LOOKUP_FALLBACK. Conflicting reliable names/existence block. Inactive/down is informational. An empty reliably collected database proves absence. Interface membership and service references do not establish global existence. Earlier approved creation supplies prerequisites to later ME EVC; conflicting same-ID requests block and cite rows. EdgeSwitch port membership never requires global creation. No interface command is emitted here.

## Template 6 — C3850X Access Port

Status: signed-off detailed contract; deterministic validation only, owner live validation pending.

| Input column | Requirement | Allowed values / forbidden values / example |
|---|---|---|
| `management_ip` | Required | IPv4/IPv6 literal; e.g. 192.0.2.91. No hostname, credentials or URL. |
| `interface` | Required | Existing explicit interface identifier; platform details and sample below. No whitespace except EdgeSwitch lag N; no shell metacharacters. |
| `vlan_id` | Required | One integer VLAN ID; family bounds below. No list/range, ALL, 0 or 4095. |
| `description` | Optional | Printable ASCII text with spaces/case, e.g. Customer Site Alpha; no secrets, quotes, semicolon or backslash. Blank optional preserves existing description. |

Interface: full canonical Cisco name, e.g. GigabitEthernet1/0/1; no abbreviated Gi names. vlan_id: one integer 1–4094 excluding 1002–1005. Optional description preserves blank; input has no action/native VLAN.

| Filled input (plus management_ip) and observed state | Expected result |
|---|---|
| interface=GigabitEthernet1/0/1; vlan_id=445; description=Customer; empty/dynamic/access different | `configure terminal / interface GigabitEthernet1/0/1 / description Customer / switchport / switchport mode access / switchport access vlan 445 / end` |
| same interface; vlan_id=445; description blank; explicit access VLAN already 445 | No-op; existing description preserved |
| vlan_id=445; missing global VLAN | Nonblocking GLOBAL_VLAN_REQUIRED; proposed access CLI, no auto-create |
| same input after earlier Pending/Reject database prerequisite | Dependency not approved; cannot claim readiness |
| same input on configured trunk or routed no switchport | Show proposal; ACCESS_CONVERSION_BLOCKED |
| same input on channel-group member | PHYSICAL_PORT_CHANNEL_MEMBER; no redirection |
| vlan_id=1002 or interface=Gi1/0/1 | Invalid, no CLI |

Evidence: full physical stanza and logical Port-channel evidence where owned; approved show vlan id lookup/config fallback for target VLAN. Explicit access mode wins over residual trunk statements, which warn. Access VLAN without explicit mode/empty/dynamic mode warns; inferred default VLAN alone is not a complete match. Shutdown retained. Earlier Access then Description is compatible, warns both rows, final description wins. Access versus Trunk on same effective resource blocks. Unknown syntax/owner/evidence is never waived by a No-op.

## Template 7 — C3850X Trunk Port

Status: signed-off detailed contract; deterministic validation only, owner live validation pending.

| Input column | Requirement | Allowed values / forbidden values / example |
|---|---|---|
| `management_ip` | Required | IPv4/IPv6 literal; e.g. 192.0.2.91. No hostname, credentials or URL. |
| `interface` | Required | Existing explicit interface identifier; platform details and sample below. No whitespace except EdgeSwitch lag N; no shell metacharacters. |
| `action` | Required | Exact family-specific selection below; no lowercase aliases. |
| `vlans` | Required | Comma-separated integers/inclusive ranges, e.g. 445,545-546. Nonempty, no duplicates, reversed ranges, ALL or NONE input. API uses a list of integer IDs. |
| `native_vlan` | Optional | One integer in Catalyst VLAN bounds. Blank retains existing/default native VLAN; separate from allowed membership. |
| `description` | Optional | Printable ASCII text with spaces/case, e.g. Customer Site Alpha; no secrets, quotes, semicolon or backslash. Blank optional preserves existing description. |

Interface: full canonical Cisco name. action exactly Add, Remove or Replace; vlans one/comma/inclusive ranges with no duplicates, 1–4094 excluding 1002–1005. ALL/NONE are observed symbolic states, **not input values**. native_vlan same bounds, optional and independent; description optional. Blank optional inputs preserve native/default VLAN 1 and description.

| Filled input (plus management_ip and interface=GigabitEthernet1/0/2) and state | Expected CLI/result |
|---|---|
| action=Add; vlans=445,545; explicit baseline=445 | `configure terminal / interface GigabitEthernet1/0/2 / switchport trunk allowed vlan add 445,545 / end` (all requested IDs) |
| action=Add; vlans=445; explicit baseline contains 445 | No-op if all other requested fields match |
| action=Add; vlans=445; no explicit allowed baseline (ALL) | ADD_REQUIRES_EXPLICIT_BASELINE, even if No-op; use Replace |
| action=Remove; vlans=445; no baseline (ALL) | `switchport trunk allowed vlan remove 445` in configuration/interface/end; projected ALL except 445; service warning |
| action=Remove; vlans=445; explicit baseline=545 | No-op |
| action=Replace; vlans=445,545-546; existing trunk | `switchport trunk allowed vlan 445,545,546` in configuration/interface/end; service-impact warning for changes |
| action=Replace; vlans=445; empty interface | Setup `switchport / switchport mode trunk` before `switchport trunk allowed vlan 445` |
| action=Replace; vlans=445; existing access | Full setup proposal, TRUNK_CONVERSION_BLOCKED |
| action=Add; vlans=445; native_vlan=545; description=Customer; tags match | Only requested differing native/description commands; no redundant allowed command |
| action=Remove; vlans=445; native_vlan=445 | NATIVE_VLAN_IMPACT warning; inspect unchanged versus requested native state carefully |
| action=Replace; vlans=ALL or 200-100 or 1002 | Invalid, no CLI |

Evidence: reconstruct all original allowed base/add/remove/except statements in source order; preserve ALL and NONE distinctly. The collector requests operational VLAN lookups for input IDs; trunk evaluation uses configured allowed-list state and does not require global database existence or auto-create VLANs. The global-VLAN warning and database dependency rule described for Access do not add a trunk database prerequisite. Resolve physical members to audited Port-channel owner, retain both stanzas and TARGET_RESOLVED_TO_PORT_CHANNEL; absent/conflicting owner blocks. C3850X never emits an encapsulation selector. C3750X adds it only for new/conversion trunks. Optional differing native VLAN/description render only when requested. No shutdown/MTU changes. Compatible Add?Add and Replace?Remove use projected state and overlap warnings; other unapproved overlapping pairs block. Unknown baseline syntax blocks, never treated as an empty list.

## Template 8 — C3850X Description

Status: signed-off detailed contract; deterministic validation only, owner live validation pending.

| Input column | Requirement | Allowed values / forbidden values / example |
|---|---|---|
| `management_ip` | Required | IPv4/IPv6 literal; e.g. 192.0.2.91. No hostname, credentials or URL. |
| `interface` | Required | Existing explicit interface identifier; platform details and sample below. No whitespace except EdgeSwitch lag N; no shell metacharacters. |
| `description` | Required | Printable ASCII text with spaces/case, e.g. Customer Site Alpha; no secrets, quotes, semicolon or backslash. Blank optional preserves existing description. |

Required description; target example `GigabitEthernet1/0/1`. Catalyst requires full canonical FastEthernet/GigabitEthernet/TenGigabitEthernet/FortyGigabitEthernet/HundredGigE/Port-channel/Vlan/Loopback names with numeric slash components and optional numeric suffix; abbreviations like Gi1/0/1 are invalid. Other catalogue identifiers accept [A-Za-z0-9][A-Za-z0-9./:-]* (EdgeSwitch also lag N), but actual unambiguous observed existence is mandatory. Physical and supported logical/aggregate targets stay exact; no LAG redirect.

| Filled input (plus management_ip) and observed state | Expected result |
|---|---|
| interface=GigabitEthernet1/0/1; description=Customer Site Alpha; old/empty text | `configure terminal / interface GigabitEthernet1/0/1 / description Customer Site Alpha / end` |
| same input; matching text | No-op |
| same input; physical member of aggregate | Change exact member description only |
| description blank, target missing/ambiguous, or unreliable source | Invalid input or evidence blocker |
| same target in two rows; identical description | Later No-op, compatible overlap warning for approved families |
| same target in two rows; different descriptions | Ordered overlap blocker |

Evidence: exact interface declaration plus preserved configuration and original observed description, never redirected to aggregate. Approved Cisco keeps complete parent/child stanza through `!`; EdgeSwitch through `exit`, including unrelated PoE/MTU/STP/VLAN/PVID. VLAN defects can warn but no VLAN repair occurs. NCS540 provisional renderer retains `l2transport` when evidenced, and rejects unresolved declarations; NE05E remains provisional, with existing scoped facts rather than a new full-stanza guarantee. Provisional family overlap behavior is conservative, so do not assume the approved-family duplicate warning exemption.

## Template 9 — ME3600X VLAN Database

Status: signed-off detailed contract; deterministic validation only, owner live validation pending.

| Input column | Requirement | Allowed values / forbidden values / example |
|---|---|---|
| `management_ip` | Required | IPv4/IPv6 literal; e.g. 192.0.2.91. No hostname, credentials or URL. |
| `vlan_id` | Required | One integer VLAN ID; family bounds below. No list/range, ALL, 0 or 4095. |
| `name` | Required | Family-specific VLAN name limits below; no empty name, quotes, semicolon or backslash. |

Bounds: 1–4094 excluding 1002–1005; names =32 ASCII [A-Za-z0-9_.:-], no spaces. VLAN 445,545 or 200-100 in vlan_id is invalid. Empty/overlong names block; Customer Site is invalid on Cisco, valid on EdgeSwitch/NE05E within length bounds.

| Filled input (plus management_ip) and observed state | Expected result |
|---|---|
| vlan_id=901; name=Customer; absent global VLAN | `configure terminal / vlan 901 / name Customer / end` |
| vlan_id=901; name=Customer; existing name Customer | No-op, empty CLI |
| vlan_id=901; name=Customer; existing name Old | Rename with VLAN_RENAME_IMPACT; same CLI, no deletion |
| vlan_id=1002; name=Customer | Invalid input, no CLI |
| vlan_id=901; name=Customer; unknown evidence | Blocked; never infer absent |

Evidence: full reliable running-config global VLAN declaration/list/name plus `show vlan id 901`. Explicit absence creates; operational failure/inconclusive output falls back only to complete config, annotated VLAN_LOOKUP_FALLBACK. Conflicting reliable names/existence block. Inactive/down is informational. An empty reliably collected database proves absence. Interface membership and service references do not establish global existence. Earlier approved creation supplies prerequisites to later ME EVC; conflicting same-ID requests block and cite rows. EdgeSwitch port membership never requires global creation. No interface command is emitted here.

## Template 10 — ME3600X EVC

Status: signed-off detailed contract; deterministic validation only, owner live validation pending.

| Input column | Requirement | Allowed values / forbidden values / example |
|---|---|---|
| `management_ip` | Required | IPv4/IPv6 literal; e.g. 192.0.2.91. No hostname, credentials or URL. |
| `interface` | Required | Existing explicit interface identifier; platform details and sample below. No whitespace except EdgeSwitch lag N; no shell metacharacters. |
| `service_instance_id` | Required | Integer 1–4000, independent of outer VLAN, push_vlan and BD. No 0/4001. |
| `encapsulation` | Required | Exact selector below; conditional outer/inner input rules apply. |
| `bridge_domain` | Required | EVC integer 1–4094 (ME excludes 1002–1005); NCS540 nonempty ASCII name [A-Za-z0-9_.:-]+, e.g. CUSTOMER-445. |
| `outer_vlan` | Conditional | Required for tagged encapsulation, forbidden for untagged. EVC compact inclusive ID/range/list 1–4094; NCS540 one integer 1–4094. No reversed range, ALL or NONE. |
| `inner_vlan` | Conditional | Required only for QinQ; forbidden otherwise. EVC ID/range/list 1–4094 or any (normalized to 1-4094); NCS540 one integer 1–4094. |
| `rewrite` | Optional | Blank defaults to None; exactly None, Pop 1 symmetric, Pop 2 symmetric, Push dot1q, Push dot1q symmetric. Matrix below is mandatory; no substitution. |
| `push_vlan` | Conditional | Required only with either Push, otherwise forbidden. One integer 1–4094, independent of ingress VLANs. No list/range. |
| `split_horizon_group` | Optional | Integer 0–15; explicit 0 is retained, blank means omit on child recreation. No -1/16. |
| `description` | Optional | Printable ASCII text with spaces/case, e.g. Customer Site Alpha; no secrets, quotes, semicolon or backslash. Child-only; blank omits existing description on recreation. |
| `interface_description` | Optional | Parent-only description; blank preserves. Printable ASCII 1–256, no secrets, double quotes, semicolon or backslash. |

See the [complete matrix and scenario table](#evc-complete-encapsulation-x-rewrite-matrix-templates-10-and-12) below; both EVC sheets have exactly the same child input grammar. Interface accepts physical/aggregate FastEthernet/GigabitEthernet/TenGigabitEthernet/Port-channel or Fa/Gi/Te/Po followed by numeric slash components, without subinterface suffix. Ingress outer/inner IDs are 1–4094, including IDs otherwise reserved in a global switching database. ME global BD uses its stricter database bounds.

Every row renders `configure terminal / interface GigabitEthernet0/1 / no service instance 3000 / service instance 3000 ethernet / <complete child commands> / end`. It never returns No-op, even when matching or confirmed absent. Existing target triggers SERVICE_INSTANCE_RECREATE_IMPACT. Service Instance Differences lists exact unique before/after commands, added/removed settings and recreation/existence. OMITTED_CHILD_SETTINGS means old child commands absent from desired specification; nested syntax facts and ending `!` are not duplicate omitted commands. All unrelated children and parent commands are preserved. A blank child description/group/rewrite can remove old settings; blank interface_description preserves parent text. Group 0 is explicit, not absence.

ME parent requires both switchport mode trunk and switchport trunk allowed vlan none; compatible empty parent can initialize both. BD needs global VLAN, or earlier approved database creation. ASR uses inline BD only, no ME switchport setup; compatible empty parent can propose no ip address. Neither guesses no shutdown/MTU/STP. Routed, incompatible, physical LAG-owned parents block. Unknown child ingress, duplicate instance ID, unknown forwarding syntax or conflicting detail/config block. QinQ overlap compares outer/inner pairs; unrelated service with intersecting ingress blocks (single-tag versus QinQ coexistence is not assumed safe). Repeated same-ID EVC rows conflict; distinct disjoint ingress children can sequence with warnings.

Evidence: full sanitized parent and all nested child source through ending `!`, policies/admin/ownership, plus `show ethernet service instance id 3000 interface GigabitEthernet0/1 detail`. Explicit absence must identify requested ID/interface. Up/Down stays operational evidence (Down warns); unparseable/rejected detail falls back to reliable config with SERVICE_DETAIL_FALLBACK, never inferred absence. Contradictory reliable ingress/rewrite/BD/group blocks SERVICE_OBSERVATION_CONFLICT. ME global lookup uses show vlan id <BD>; fallback is annotated. ASR global-binding relationships conflict and are never automatically migrated.

## Template 11 — ME3600X Description

Status: signed-off detailed contract; deterministic validation only, owner live validation pending.

| Input column | Requirement | Allowed values / forbidden values / example |
|---|---|---|
| `management_ip` | Required | IPv4/IPv6 literal; e.g. 192.0.2.91. No hostname, credentials or URL. |
| `interface` | Required | Existing explicit interface identifier; platform details and sample below. No whitespace except EdgeSwitch lag N; no shell metacharacters. |
| `description` | Required | Printable ASCII text with spaces/case, e.g. Customer Site Alpha; no secrets, quotes, semicolon or backslash. Blank optional preserves existing description. |

Required description; target example `GigabitEthernet0/1`. Catalyst requires full canonical FastEthernet/GigabitEthernet/TenGigabitEthernet/FortyGigabitEthernet/HundredGigE/Port-channel/Vlan/Loopback names with numeric slash components and optional numeric suffix; abbreviations like Gi1/0/1 are invalid. Other catalogue identifiers accept [A-Za-z0-9][A-Za-z0-9./:-]* (EdgeSwitch also lag N), but actual unambiguous observed existence is mandatory. Physical and supported logical/aggregate targets stay exact; no LAG redirect.

| Filled input (plus management_ip) and observed state | Expected result |
|---|---|
| interface=GigabitEthernet0/1; description=Customer Site Alpha; old/empty text | `configure terminal / interface GigabitEthernet0/1 / description Customer Site Alpha / end` |
| same input; matching text | No-op |
| same input; physical member of aggregate | Change exact member description only |
| description blank, target missing/ambiguous, or unreliable source | Invalid input or evidence blocker |
| same target in two rows; identical description | Later No-op, compatible overlap warning for approved families |
| same target in two rows; different descriptions | Ordered overlap blocker |

Evidence: exact interface declaration plus preserved configuration and original observed description, never redirected to aggregate. Approved Cisco keeps complete parent/child stanza through `!`; EdgeSwitch through `exit`, including unrelated PoE/MTU/STP/VLAN/PVID. VLAN defects can warn but no VLAN repair occurs. NCS540 provisional renderer retains `l2transport` when evidenced, and rejects unresolved declarations; NE05E remains provisional, with existing scoped facts rather than a new full-stanza guarantee. Provisional family overlap behavior is conservative, so do not assume the approved-family duplicate warning exemption.

## Template 12 — ASR920 EVC

Status: signed-off detailed contract; deterministic validation only, owner live validation pending.

| Input column | Requirement | Allowed values / forbidden values / example |
|---|---|---|
| `management_ip` | Required | IPv4/IPv6 literal; e.g. 192.0.2.91. No hostname, credentials or URL. |
| `interface` | Required | Existing explicit interface identifier; platform details and sample below. No whitespace except EdgeSwitch lag N; no shell metacharacters. |
| `service_instance_id` | Required | Integer 1–4000, independent of outer VLAN, push_vlan and BD. No 0/4001. |
| `encapsulation` | Required | Exact selector below; conditional outer/inner input rules apply. |
| `bridge_domain` | Required | EVC integer 1–4094 (ME excludes 1002–1005); NCS540 nonempty ASCII name [A-Za-z0-9_.:-]+, e.g. CUSTOMER-445. |
| `outer_vlan` | Conditional | Required for tagged encapsulation, forbidden for untagged. EVC compact inclusive ID/range/list 1–4094; NCS540 one integer 1–4094. No reversed range, ALL or NONE. |
| `inner_vlan` | Conditional | Required only for QinQ; forbidden otherwise. EVC ID/range/list 1–4094 or any (normalized to 1-4094); NCS540 one integer 1–4094. |
| `rewrite` | Optional | Blank defaults to None; exactly None, Pop 1 symmetric, Pop 2 symmetric, Push dot1q, Push dot1q symmetric. Matrix below is mandatory; no substitution. |
| `push_vlan` | Conditional | Required only with either Push, otherwise forbidden. One integer 1–4094, independent of ingress VLANs. No list/range. |
| `split_horizon_group` | Optional | Integer 0–15; explicit 0 is retained, blank means omit on child recreation. No -1/16. |
| `description` | Optional | Printable ASCII text with spaces/case, e.g. Customer Site Alpha; no secrets, quotes, semicolon or backslash. Child-only; blank omits existing description on recreation. |
| `interface_description` | Optional | Parent-only description; blank preserves. Printable ASCII 1–256, no secrets, double quotes, semicolon or backslash. |

See the [complete matrix and scenario table](#evc-complete-encapsulation-x-rewrite-matrix-templates-10-and-12) below; both EVC sheets have exactly the same child input grammar. Interface accepts physical/aggregate FastEthernet/GigabitEthernet/TenGigabitEthernet/Port-channel or Fa/Gi/Te/Po followed by numeric slash components, without subinterface suffix. Ingress outer/inner IDs are 1–4094, including IDs otherwise reserved in a global switching database. ME global BD uses its stricter database bounds.

Every row renders `configure terminal / interface GigabitEthernet0/1 / no service instance 3000 / service instance 3000 ethernet / <complete child commands> / end`. It never returns No-op, even when matching or confirmed absent. Existing target triggers SERVICE_INSTANCE_RECREATE_IMPACT. Service Instance Differences lists exact unique before/after commands, added/removed settings and recreation/existence. OMITTED_CHILD_SETTINGS means old child commands absent from desired specification; nested syntax facts and ending `!` are not duplicate omitted commands. All unrelated children and parent commands are preserved. A blank child description/group/rewrite can remove old settings; blank interface_description preserves parent text. Group 0 is explicit, not absence.

ME parent requires both switchport mode trunk and switchport trunk allowed vlan none; compatible empty parent can initialize both. BD needs global VLAN, or earlier approved database creation. ASR uses inline BD only, no ME switchport setup; compatible empty parent can propose no ip address. Neither guesses no shutdown/MTU/STP. Routed, incompatible, physical LAG-owned parents block. Unknown child ingress, duplicate instance ID, unknown forwarding syntax or conflicting detail/config block. QinQ overlap compares outer/inner pairs; unrelated service with intersecting ingress blocks (single-tag versus QinQ coexistence is not assumed safe). Repeated same-ID EVC rows conflict; distinct disjoint ingress children can sequence with warnings.

Evidence: full sanitized parent and all nested child source through ending `!`, policies/admin/ownership, plus `show ethernet service instance id 3000 interface GigabitEthernet0/1 detail`. Explicit absence must identify requested ID/interface. Up/Down stays operational evidence (Down warns); unparseable/rejected detail falls back to reliable config with SERVICE_DETAIL_FALLBACK, never inferred absence. Contradictory reliable ingress/rewrite/BD/group blocks SERVICE_OBSERVATION_CONFLICT. ME global lookup uses show vlan id <BD>; fallback is annotated. ASR global-binding relationships conflict and are never automatically migrated.

## Template 13 — ASR920 Description

Status: signed-off detailed contract; deterministic validation only, owner live validation pending.

| Input column | Requirement | Allowed values / forbidden values / example |
|---|---|---|
| `management_ip` | Required | IPv4/IPv6 literal; e.g. 192.0.2.91. No hostname, credentials or URL. |
| `interface` | Required | Existing explicit interface identifier; platform details and sample below. No whitespace except EdgeSwitch lag N; no shell metacharacters. |
| `description` | Required | Printable ASCII text with spaces/case, e.g. Customer Site Alpha; no secrets, quotes, semicolon or backslash. Blank optional preserves existing description. |

Required description; target example `GigabitEthernet0/1`. Catalyst requires full canonical FastEthernet/GigabitEthernet/TenGigabitEthernet/FortyGigabitEthernet/HundredGigE/Port-channel/Vlan/Loopback names with numeric slash components and optional numeric suffix; abbreviations like Gi1/0/1 are invalid. Other catalogue identifiers accept [A-Za-z0-9][A-Za-z0-9./:-]* (EdgeSwitch also lag N), but actual unambiguous observed existence is mandatory. Physical and supported logical/aggregate targets stay exact; no LAG redirect.

| Filled input (plus management_ip) and observed state | Expected result |
|---|---|
| interface=GigabitEthernet0/1; description=Customer Site Alpha; old/empty text | `configure terminal / interface GigabitEthernet0/1 / description Customer Site Alpha / end` |
| same input; matching text | No-op |
| same input; physical member of aggregate | Change exact member description only |
| description blank, target missing/ambiguous, or unreliable source | Invalid input or evidence blocker |
| same target in two rows; identical description | Later No-op, compatible overlap warning for approved families |
| same target in two rows; different descriptions | Ordered overlap blocker |

Evidence: exact interface declaration plus preserved configuration and original observed description, never redirected to aggregate. Approved Cisco keeps complete parent/child stanza through `!`; EdgeSwitch through `exit`, including unrelated PoE/MTU/STP/VLAN/PVID. VLAN defects can warn but no VLAN repair occurs. NCS540 provisional renderer retains `l2transport` when evidenced, and rejects unresolved declarations; NE05E remains provisional, with existing scoped facts rather than a new full-stanza guarantee. Provisional family overlap behavior is conservative, so do not assume the approved-family duplicate warning exemption.

## Template 14 — EdgeSwitch VLAN Database

Status: signed-off detailed contract; deterministic validation only, owner live validation pending.

| Input column | Requirement | Allowed values / forbidden values / example |
|---|---|---|
| `management_ip` | Required | IPv4/IPv6 literal; e.g. 192.0.2.91. No hostname, credentials or URL. |
| `vlan_id` | Required | One integer VLAN ID; family bounds below. No list/range, ALL, 0 or 4095. |
| `name` | Required | Family-specific VLAN name limits below; no empty name, quotes, semicolon or backslash. |

Bounds: 2–4093; names =32 ASCII characters including spaces. VLAN 445,545 or 200-100 in vlan_id is invalid. Empty/overlong names block; Customer Site is invalid on Cisco, valid on EdgeSwitch/NE05E within length bounds.

| Filled input (plus management_ip) and observed state | Expected result |
|---|---|
| vlan_id=901; name=Customer; absent global VLAN | `vlan database / vlan 901 / vlan name 901 "Customer" / exit` |
| vlan_id=901; name=Customer; existing name Customer | No-op, empty CLI |
| vlan_id=901; name=Customer; existing name Old | Rename with VLAN_RENAME_IMPACT; same CLI, omit vlan 901 when already present |
| vlan_id=1; name=Customer | Invalid input, no CLI |
| vlan_id=901; name=Customer; unknown evidence | Blocked; never infer absent |

Evidence: full reliable running-config global VLAN declaration/list/name plus `show vlan 901`. Explicit absence creates; operational failure/inconclusive output falls back only to complete config, annotated VLAN_LOOKUP_FALLBACK. Conflicting reliable names/existence block. Inactive/down is informational. An empty reliably collected database proves absence. Interface membership and service references do not establish global existence. Earlier approved creation supplies prerequisites to later ME EVC; conflicting same-ID requests block and cite rows. EdgeSwitch port membership never requires global creation. No interface command is emitted here.

## Template 15 — EdgeSwitch VLAN Port

Status: signed-off detailed contract; deterministic validation only, owner live validation pending.

| Input column | Requirement | Allowed values / forbidden values / example |
|---|---|---|
| `management_ip` | Required | IPv4/IPv6 literal; e.g. 192.0.2.91. No hostname, credentials or URL. |
| `interface` | Required | Existing explicit interface identifier; platform details and sample below. No whitespace except EdgeSwitch lag N; no shell metacharacters. |
| `action` | Required | Exact family-specific selection below; no lowercase aliases. |
| `tagged_vlans` | Conditional | One/comma/inclusive range/list 2–4093; required for Remove; Add/Change requires this and/or pvid. Example 545,745-746. No ALL/NONE/1/4094/reversed ranges. |
| `pvid` | Conditional | Optional Add/Change integer 2–4093; forbidden for Remove even if unchanged. May also occur in tagged_vlans; blank retains current PVID. |
| `description` | Optional | Printable ASCII text with spaces/case, e.g. Customer Site Alpha; no secrets, quotes, semicolon or backslash. Blank optional preserves existing description. |

Interface example 0/1 or evidenced lag 1. Only Add/Change or Remove. tagged_vlans IDs and pvid 2–4093. Forbidden: Replace, vlan_id, untagged_vlans, mode, vlans, replace_untagged. See the full [action/PVID/tagged scenario table below](#edgeswitch-complete-action-x-taggedpvid-cases-template-15). All operations use `configure / interface 0/1 / <differences> / exit / exit`; No-op emits nothing.

Independent configured include/exclude/tagged/PVID are retained, including exclude 746 AND tagging 746. Tagging is never intersected away against membership for planning. Current/Configured/Tagging from show vlan are distinct; Current Exclude versus Configured Include never authorizes an automatic fix. Complete interface evidence through exit includes unrelated PoE/storm-control/MTU/BPDU/protected-port settings; no such commands render. Global VLAN absence gives VLAN_NOT_IN_DATABASE informational warning, never auto-creation. Operational show vlan <ID> evidence uses reliable complete running-config fallback; contradictory reliable global observations and unknown config still block.

Earlier Remove then Add/Change explicitly replaces membership/tagging; PVID change then Remove frees the old PVID. Earlier Pending adds dependency blocker, Reject removes projected effect and can expose PVID-removal blocker. Compatible port pairs warn with source rows and project membership/tagging/PVID; unsafe pairs/owned LAG members/unknown parent block. Current PVID cannot be removed until an earlier approved row changes it. Optional description affects only supplied text. Repeated fully satisfied rows No-op safely while retaining overlap warnings.

## Template 16 — EdgeSwitch Description

Status: signed-off detailed contract; deterministic validation only, owner live validation pending.

| Input column | Requirement | Allowed values / forbidden values / example |
|---|---|---|
| `management_ip` | Required | IPv4/IPv6 literal; e.g. 192.0.2.91. No hostname, credentials or URL. |
| `interface` | Required | Existing explicit interface identifier; platform details and sample below. No whitespace except EdgeSwitch lag N; no shell metacharacters. |
| `description` | Required | Printable ASCII text with spaces/case, e.g. Customer Site Alpha; no secrets, quotes, semicolon or backslash. Blank optional preserves existing description. |

Required description; target example `0/1`. Catalyst requires full canonical FastEthernet/GigabitEthernet/TenGigabitEthernet/FortyGigabitEthernet/HundredGigE/Port-channel/Vlan/Loopback names with numeric slash components and optional numeric suffix; abbreviations like Gi1/0/1 are invalid. Other catalogue identifiers accept [A-Za-z0-9][A-Za-z0-9./:-]* (EdgeSwitch also lag N), but actual unambiguous observed existence is mandatory. Physical and supported logical/aggregate targets stay exact; no LAG redirect.

| Filled input (plus management_ip) and observed state | Expected result |
|---|---|
| interface=0/1; description=Customer Site Alpha; old/empty text | `configure / interface 0/1 / description "Customer Site Alpha" / exit / exit` |
| same input; matching text | No-op |
| same input; physical member of aggregate | Change exact member description only |
| description blank, target missing/ambiguous, or unreliable source | Invalid input or evidence blocker |
| same target in two rows; identical description | Later No-op, compatible overlap warning for approved families |
| same target in two rows; different descriptions | Ordered overlap blocker |

Evidence: exact interface declaration plus preserved configuration and original observed description, never redirected to aggregate. Approved Cisco keeps complete parent/child stanza through `!`; EdgeSwitch through `exit`, including unrelated PoE/MTU/STP/VLAN/PVID. VLAN defects can warn but no VLAN repair occurs. NCS540 provisional renderer retains `l2transport` when evidenced, and rejects unresolved declarations; NE05E remains provisional, with existing scoped facts rather than a new full-stanza guarantee. Provisional family overlap behavior is conservative, so do not assume the approved-family duplicate warning exemption.

## Template 17 — NCS540 L2VPN

Status: **catalogue/provisional, not owner-approved or live-validated**.

| Input column | Requirement | Allowed values / forbidden values / example |
|---|---|---|
| `management_ip` | Required | IPv4/IPv6 literal; e.g. 192.0.2.91. No hostname, credentials or URL. |
| `interface` | Required | Existing explicit interface identifier; platform details and sample below. No whitespace except EdgeSwitch lag N; no shell metacharacters. |
| `subinterface` | Required | Integer suffix: NCS540 0–2147483647; NE05E 1–4094. Parent field must omit the suffix to avoid accidental double suffix. |
| `encapsulation` | Required | Exact selector below; conditional outer/inner input rules apply. |
| `bridge_group` | Required | Nonempty CLI identifier [A-Za-z0-9][A-Za-z0-9./:-]*, e.g. CUSTOMER; no spaces. |
| `bridge_domain` | Required | EVC integer 1–4094 (ME excludes 1002–1005); NCS540 nonempty ASCII name [A-Za-z0-9_.:-]+, e.g. CUSTOMER-445. |
| `outer_vlan` | Conditional | Required for tagged encapsulation, forbidden for untagged. EVC compact inclusive ID/range/list 1–4094; NCS540 one integer 1–4094. No reversed range, ALL or NONE. |
| `inner_vlan` | Conditional | Required only for QinQ; forbidden otherwise. EVC ID/range/list 1–4094 or any (normalized to 1-4094); NCS540 one integer 1–4094. |
| `description` | Optional | Printable ASCII text with spaces/case, e.g. Customer Site Alpha; no secrets, quotes, semicolon or backslash. Blank optional preserves existing description. |

**Provisional existing implementation only.** encapsulation exactly dot1q, QinQ or untagged (different case from EVC). Numeric outer required except untagged; numeric inner only QinQ, each 1–4094. bridge_group and bridge_domain names are independent of tags. No rewrite/pop/push/group column is present; no implicit commit. Example parent GigabitEthernet0/0/0/1; subinterface=445.

| Filled input (plus management_ip/interface/subinterface above) | Expected proposal/result |
|---|---|
| encapsulation=dot1q; outer_vlan=445; bridge_group=CUSTOMER; bridge_domain=BD445 | `configure terminal / interface GigabitEthernet0/0/0/1.445 l2transport / encapsulation dot1q 445 / exit / l2vpn / bridge group CUSTOMER / bridge-domain BD445 / interface GigabitEthernet0/0/0/1.445 / end` |
| encapsulation=QinQ; outer_vlan=300; inner_vlan=200; same group/domain | Same hierarchy, `encapsulation dot1q 300 second-dot1q 200` |
| encapsulation=untagged; tags blank; same group/domain | Same hierarchy, `encapsulation untagged` |
| description=Customer with any valid case | Description before encapsulation under subinterface |
| existing exact ingress/description and same unique L2 attachment | No-op |
| existing routed target or attachment to another BD | ROUTED_SUBINTERFACE_CONVERSION / L2VPN_ATTACHMENT_CONFLICT |
| same outer ingress on sibling subinterface | Conservative INGRESS_TAG_OVERLAP blocker, even different QinQ inner |
| QinQ without inner, untagged with outer, subinterface=-1, pop_tags=1 | Invalid input |

Evidence uses shared IOS-XR configuration facts/audit relationship validation and existing declared interfaces; service references never invent targets. Missing actual parent/evidence or unresolved owner blocks. Provisional behavior does not provide the approved ME/ASR full-child recreation contract. Cross-row interface/domain overlaps remain conservative blockers; no approval or live forwarding support is inferred from renderer output.

## Template 18 — NCS540 Description

Status: **catalogue/provisional, not owner-approved or live-validated**.

| Input column | Requirement | Allowed values / forbidden values / example |
|---|---|---|
| `management_ip` | Required | IPv4/IPv6 literal; e.g. 192.0.2.91. No hostname, credentials or URL. |
| `interface` | Required | Existing explicit interface identifier; platform details and sample below. No whitespace except EdgeSwitch lag N; no shell metacharacters. |
| `description` | Required | Printable ASCII text with spaces/case, e.g. Customer Site Alpha; no secrets, quotes, semicolon or backslash. Blank optional preserves existing description. |

Required description; target example `GigabitEthernet0/0/0/1.445`. Catalyst requires full canonical FastEthernet/GigabitEthernet/TenGigabitEthernet/FortyGigabitEthernet/HundredGigE/Port-channel/Vlan/Loopback names with numeric slash components and optional numeric suffix; abbreviations like Gi1/0/1 are invalid. Other catalogue identifiers accept [A-Za-z0-9][A-Za-z0-9./:-]* (EdgeSwitch also lag N), but actual unambiguous observed existence is mandatory. Physical and supported logical/aggregate targets stay exact; no LAG redirect.

| Filled input (plus management_ip) and observed state | Expected result |
|---|---|
| interface=GigabitEthernet0/0/0/1.445; description=Customer Site Alpha; old/empty text | `configure terminal / interface GigabitEthernet0/0/0/1.445 / description Customer Site Alpha / end` |
| same input; matching text | No-op |
| same input; physical member of aggregate | Change exact member description only |
| description blank, target missing/ambiguous, or unreliable source | Invalid input or evidence blocker |
| same target in two rows; identical description | Later No-op, compatible overlap warning for approved families |
| same target in two rows; different descriptions | Ordered overlap blocker |

Evidence: exact interface declaration plus preserved configuration and original observed description, never redirected to aggregate. Approved Cisco keeps complete parent/child stanza through `!`; EdgeSwitch through `exit`, including unrelated PoE/MTU/STP/VLAN/PVID. VLAN defects can warn but no VLAN repair occurs. NCS540 provisional renderer retains `l2transport` when evidenced, and rejects unresolved declarations; NE05E remains provisional, with existing scoped facts rather than a new full-stanza guarantee. Provisional family overlap behavior is conservative, so do not assume the approved-family duplicate warning exemption.

## Template 19 — NE05E VLAN Database

Status: **catalogue/provisional, not owner-approved or live-validated**.

| Input column | Requirement | Allowed values / forbidden values / example |
|---|---|---|
| `management_ip` | Required | IPv4/IPv6 literal; e.g. 192.0.2.91. No hostname, credentials or URL. |
| `vlan_id` | Required | One integer VLAN ID; family bounds below. No list/range, ALL, 0 or 4095. |
| `name` | Required | Family-specific VLAN name limits below; no empty name, quotes, semicolon or backslash. |

Bounds: 1–4094; name =80 ASCII characters including spaces. VLAN 445,545 or 200-100 in vlan_id is invalid. Empty/overlong names block; Customer Site is invalid on Cisco, valid on EdgeSwitch/NE05E within length bounds.

| Filled input (plus management_ip) and observed state | Expected result |
|---|---|
| vlan_id=901; name=Customer; absent global VLAN | `system-view / vlan 901 / description Customer / quit / quit` |
| vlan_id=901; name=Customer; existing name Customer | No-op, empty CLI |
| vlan_id=901; name=Customer; existing name Old | Rename with VLAN_RENAME_IMPACT; same CLI, no deletion |
| vlan_id=0; name=Customer | Invalid input, no CLI |
| vlan_id=901; name=Customer; unknown evidence | Blocked; never infer absent |

Provisional NE05E uses observed explicit global VLAN objects and their description, not VSI references; read-only saved-configuration facts supply evidence. No approved operational lookup/fallback contract is claimed. Rename impact is a finding that currently blocks readiness, unlike approved Cisco/EdgeSwitch warning semantics. Same-device same-ID rows overlap and block; an earlier approved database proposal can support later shared dependencies.

## Template 20 — NE05E Subinterface VSI

Status: **catalogue/provisional, not owner-approved or live-validated**.

| Input column | Requirement | Allowed values / forbidden values / example |
|---|---|---|
| `management_ip` | Required | IPv4/IPv6 literal; e.g. 192.0.2.91. No hostname, credentials or URL. |
| `interface` | Required | Existing explicit interface identifier; platform details and sample below. No whitespace except EdgeSwitch lag N; no shell metacharacters. |
| `subinterface` | Required | Integer suffix: NCS540 0–2147483647; NE05E 1–4094. Parent field must omit the suffix to avoid accidental double suffix. |
| `vlan_id` | Required | One integer VLAN ID; family bounds below. No list/range, ALL, 0 or 4095. |
| `encapsulation` | Required | Exact selector below; conditional outer/inner input rules apply. |
| `vsi` | Required | Existing VSI identifier [A-Za-z0-9][A-Za-z0-9./:-]*, e.g. CUSTOMER; no spaces or implicit creation. |
| `description` | Optional | Printable ASCII text with spaces/case, e.g. Customer Site Alpha; no secrets, quotes, semicolon or backslash. Blank optional preserves existing description. |
| `control_vid` | Conditional | Optional integer 1–4094 only with dot1q termination; forbidden with vlan-type dot1q. |

**Provisional existing implementation only.** Parent example GigabitEthernet0/1/0; subinterface=445; vlan_id integer 1–4094. encapsulation exactly dot1q termination or vlan-type dot1q; no QinQ. Existing VSI required; no VSI creation. Optional control_vid only for dot1q termination, integer 1–4094.

| Filled input (plus management_ip/interface/subinterface above) | Expected proposal/result |
|---|---|
| vlan_id=445; encapsulation=dot1q termination; vsi=CUSTOMER | `system-view / interface GigabitEthernet0/1/0.445 / dot1q termination vid 445 / l2 binding vsi CUSTOMER / quit / quit` |
| same plus control_vid=446; description=Customer | Description then `control-vid 446 dot1q-termination` before termination/binding |
| vlan_id=445; encapsulation=vlan-type dot1q; vsi=CUSTOMER | `system-view / interface GigabitEthernet0/1/0.445 / vlan-type dot1q 445 / l2 binding vsi CUSTOMER / quit / quit` |
| exact existing encapsulation/VSI/requested optional settings | No-op |
| VSI absent | EXISTING_VSI_REQUIRED blocker; no implicit creation |
| existing other encapsulation or VSI | SUBINTERFACE_ENCAPSULATION_CONVERSION / VSI_BINDING_CHANGE blockers |
| vlan-type dot1q plus control_vid; QinQ; subinterface=0; vlan_id=4095 | Invalid input |

Shared Huawei saved configuration and audit supply declared-interface/termination/VSI evidence. Missing actual parent or unreliable observation blocks. VLAN global database declaration and VSI existence are separate. Same-resource overlaps remain conservative blockers; optional description blank preserves. No new read-only commands, approval or firmware support are claimed by this reference.

## Template 21 — NE05E Description

Status: **catalogue/provisional, not owner-approved or live-validated**.

| Input column | Requirement | Allowed values / forbidden values / example |
|---|---|---|
| `management_ip` | Required | IPv4/IPv6 literal; e.g. 192.0.2.91. No hostname, credentials or URL. |
| `interface` | Required | Existing explicit interface identifier; platform details and sample below. No whitespace except EdgeSwitch lag N; no shell metacharacters. |
| `description` | Required | Printable ASCII text with spaces/case, e.g. Customer Site Alpha; no secrets, quotes, semicolon or backslash. Blank optional preserves existing description. |

Required description; target example `GigabitEthernet0/1/0`. Catalyst requires full canonical FastEthernet/GigabitEthernet/TenGigabitEthernet/FortyGigabitEthernet/HundredGigE/Port-channel/Vlan/Loopback names with numeric slash components and optional numeric suffix; abbreviations like Gi1/0/1 are invalid. Other catalogue identifiers accept [A-Za-z0-9][A-Za-z0-9./:-]* (EdgeSwitch also lag N), but actual unambiguous observed existence is mandatory. Physical and supported logical/aggregate targets stay exact; no LAG redirect.

| Filled input (plus management_ip) and observed state | Expected result |
|---|---|
| interface=GigabitEthernet0/1/0; description=Customer Site Alpha; old/empty text | `system-view / interface GigabitEthernet0/1/0 / description Customer Site Alpha / quit / quit` |
| same input; matching text | No-op |
| same input; physical member of aggregate | Change exact member description only |
| description blank, target missing/ambiguous, or unreliable source | Invalid input or evidence blocker |
| same target in two rows; identical description | Later No-op, compatible overlap warning for approved families |
| same target in two rows; different descriptions | Ordered overlap blocker |

Evidence: exact interface declaration plus preserved configuration and original observed description, never redirected to aggregate. Approved Cisco keeps complete parent/child stanza through `!`; EdgeSwitch through `exit`, including unrelated PoE/MTU/STP/VLAN/PVID. VLAN defects can warn but no VLAN repair occurs. NCS540 provisional renderer retains `l2transport` when evidenced, and rejects unresolved declarations; NE05E remains provisional, with existing scoped facts rather than a new full-stanza guarantee. Provisional family overlap behavior is conservative, so do not assume the approved-family duplicate warning exemption.

## Template 22 — Manual CLI

Status: **catalogue/provisional, not owner-approved or live-validated**.

| Input column | Requirement | Allowed values / forbidden values / example |
|---|---|---|
| `management_ip` | Required | IPv4/IPv6 literal; e.g. 192.0.2.91. No hostname, credentials or URL. |
| `platform` | Required | Exactly cisco_ios, cisco_xe, cisco_xr, huawei_vrp or ubiquiti_edgeswitch. |
| `mode` | Required | Exactly configuration, interface or service; metadata only, no wrapper generation. |
| `scope` | Required | Printable ASCII 1–256 affected-resource metadata; e.g. interface GigabitEthernet0/1. Not interpreted as CLI. |
| `commands` | Required | Literal multiline printable ASCII up to 16000 including CR/LF/tab; no secrets. Full hierarchy is engineer responsibility; no semantic safety claim. |

**Provisional catalogue semantics, not owner-approved/live-validated.** No device connection or evidence collection even with Approve. Explicit scope/mode are metadata, not inferred hierarchy. The literal command string is preserved including whitespace/newlines; no wrapper, save or commit is added, no semantic safety check or allowlisted effect validation is claimed. Secret screening/bounded structure still apply.

| Filled input (plus management_ip) | Expected result |
|---|---|
| platform=cisco_ios; mode=configuration; scope=interface GigabitEthernet0/1; commands multiline: configure terminal, interface GigabitEthernet0/1, description Customer, end | Exactly those four literal lines; MANUAL_EFFECTS_UNKNOWN, not_live_validated, impact unknown, not deployment-ready even Approve |
| platform=cisco_xr; mode=service; scope=CUSTOMER; commands=description Customer | Literal text only; mode/scope never add missing hierarchy or commit |
| platform=huawei_vrp; mode=interface; scope=GigabitEthernet0/1/0; commands=description Customer | Literal text only; no system-view/interface wrapper |
| mode=exec, platform=ios, blank scope/commands or commands containing credentials | Invalid input, no CLI artifact |
| Manual row plus another same-device row | Conservative overlap conflict; effects cannot be projected safely |

No No-op semantics are inferred, no fallback exists, and observation supplied for a Manual-only target is not evidence of validation. JSON/Excel decisions and digest checks are the same ordinary offline surface; no elevated approver role is introduced. V1 Manual allowlists remain unchanged in the separate v1 API.


## EVC complete encapsulation x rewrite matrix (Templates 10 and 12)

This matrix applies independently to ME3600X and ASR920. Supported means the signed-off planning contract permits rendering; it does not certify every release. Unverified and lab-rejected both block with distinct reasons. No rewrite is omission, never an inferred default.

| Encapsulation | None / blank | Pop 1 symmetric | Pop 2 symmetric | Push dot1q | Push dot1q symmetric |
|---|---|---|---|---|---|
| Untagged, no tags | Supported | Unverified/unsupported | Unverified/unsupported | Supported | Supported |
| Dot1q single outer | Unverified, not independently lab-proven | Supported | Lab rejected | Supported | Supported |
| Dot1q outer list/range | Supported | Lab rejected | Lab rejected | Supported | Supported |
| QinQ fixed inner | Unverified, not independently lab-proven | Supported | Supported | Lab rejected | Supported |
| QinQ inner list/range (including 1-4094) | Supported | Supported | Lab rejected | Lab rejected | Supported |

UNVERIFIED_REWRITE_COMBINATION explains that device support is not independently lab-proven and fails closed. LAB_REJECTED_REWRITE_COMBINATION identifies the approved lab rejection. Neither silently substitutes rewrite or changes encapsulation. Cardinality is normalized: a one-member expression is a single/fixed tag; lists/ranges expand inclusively. QinQ overlap preserves outer/inner pairs. Release-specific generalized outer QinQ range and inner subset combinations still require owner read-only validation; acceptance in the current schema is not independent hardware proof.

All filled examples below also have management_ip=192.0.2.91, interface=GigabitEthernet0/1, service_instance_id=3000, bridge_domain=445, optional fields blank unless listed. Every supported row uses the remove/recreate wrapper above; no No-op. ME requires global VLAN 445. These input values are independent; an ID of 3000 does not infer any tag or BD.

| Filled encapsulation / outer_vlan / inner_vlan / rewrite / push_vlan | Complete child CLI (lines separated by ;) |
|---|---|
| Untagged / blank / blank / None / blank | encapsulation untagged; bridge-domain 445 |
| Untagged / blank / blank / Push dot1q / 100 | encapsulation untagged; rewrite ingress tag push dot1q 100; bridge-domain 445 |
| Untagged / blank / blank / Push dot1q symmetric / 100 | encapsulation untagged; rewrite ingress tag push dot1q 100 symmetric; bridge-domain 445 |
| Dot1q / 445 / blank / Pop 1 symmetric / blank | encapsulation dot1q 445; rewrite ingress tag pop 1 symmetric; bridge-domain 445 |
| Dot1q / 500 / blank / Push dot1q / 100 | encapsulation dot1q 500; rewrite ingress tag push dot1q 100; bridge-domain 445 |
| Dot1q / 500 / blank / Push dot1q symmetric / 100 | encapsulation dot1q 500; rewrite ingress tag push dot1q 100 symmetric; bridge-domain 445 |
| Dot1q / 100-200 / blank / None / blank | encapsulation dot1q 100-200; bridge-domain 445 |
| Dot1q / 2-444,446-544 / blank / Push dot1q / 1402 | encapsulation dot1q 2-444,446-544; rewrite ingress tag push dot1q 1402; bridge-domain 445 |
| Dot1q / 2-444,446-544 / blank / Push dot1q symmetric / 1402 | encapsulation dot1q 2-444,446-544; rewrite ingress tag push dot1q 1402 symmetric; bridge-domain 445 |
| QinQ / 300 / 200 / Pop 1 symmetric / blank | encapsulation dot1q 300 second-dot1q 200; rewrite ingress tag pop 1 symmetric; bridge-domain 445 |
| QinQ / 300 / 200 / Pop 2 symmetric / blank | encapsulation dot1q 300 second-dot1q 200; rewrite ingress tag pop 2 symmetric; bridge-domain 445 |
| QinQ / 300 / 200 / Push dot1q symmetric / 100 | encapsulation dot1q 300 second-dot1q 200; rewrite ingress tag push dot1q 100 symmetric; bridge-domain 445 |
| QinQ / 100 / 1-4094 / None / blank | encapsulation dot1q 100 second-dot1q 1-4094; bridge-domain 445 |
| QinQ / 100 / any / Pop 1 symmetric / blank | encapsulation dot1q 100 second-dot1q 1-4094; rewrite ingress tag pop 1 symmetric; bridge-domain 445 |
| QinQ / 100 / 1-4094 / Push dot1q symmetric / 200 | encapsulation dot1q 100 second-dot1q 1-4094; rewrite ingress tag push dot1q 200 symmetric; bridge-domain 445 |

Long valid range/list outer example: 2-444,446-544,546-744,747-1100,1120-2448,2450-3998 with Dot1q + Push dot1q symmetric, push_vlan=1402. It preserves that compact CLI expression, excludes 445/545/745/746/2449, and expands every included member for overlap checks. Single outer/fixed inner with None is blocked as unverified; single Dot1q Pop 2, ranged Dot1q either Pop, QinQ non-symmetric Push, ranged QinQ Pop 2 are lab rejected. Untagged Pop is unverified/unsupported. Untagged with outer, Dot1q with inner, QinQ without inner, Push without push_vlan, non-Push with push_vlan, reversed 200-100 and group=16 are invalid regardless of observed state.

Optional scenario: description=New Child adds description New Child inside the instance; interface_description=New Parent adds description New Parent under parent before deletion only when different. split_horizon_group=0 changes final line to bridge-domain 445 split-horizon group 0. Blank group omits an old group; blank rewrite omits an old rewrite only in matrix-supported combinations. Existing service-policy input OLD with no corresponding desired child field is omitted and warned; never copy it into recreation automatically. A requested change in tag/rewrite/BD appears in before/after differences; parent MTU/shutdown/description and unrelated child 20 never appear as omitted child commands.

| Observed state for a valid supported filled row above | Expected result |
|---|---|
| Scoped target absent; reliable compatible parent | Full no service instance 3000 then recreate, no existing-child deletion warning |
| Matching target including group 0 | Full recreation, SERVICE_INSTANCE_RECREATE_IMPACT, empty added/removed lists |
| Different target or omitted old child policy/description/group | Full recreation plus impact and unique omitted-command warning; inspect before/after |
| Another instance matches intersecting outer/inner pairs | INGRESS_TAG_OVERLAP; retain draft CLI, blocked |
| Another QinQ instance has same outer 300, disjoint inner 201 | No tag overlap with fixed inner 200; other safety checks still apply |
| Target/unrelated child encapsulation unknown | SERVICE_STATE_UNKNOWN; never infer safe absence |
| Detail absent but config target present, or reliable detail/config disagree | SERVICE_OBSERVATION_CONFLICT |
| ME empty compatible parent, VLAN 445 exists | Add mode trunk + allowed vlan none; full recreation |
| ASR empty compatible parent | no ip address only as approved initialization; full recreation |
| Routed/owned/incompatible parent; missing ME global VLAN without approved predecessor | Blocked conversion/ownership/GLOBAL_VLAN_REQUIRED |
| ASR saved global binding for inline requested child | ASR920_GLOBAL_BINDING_CONFLICT; no migration |

## EdgeSwitch complete action x tagged/PVID cases (Template 15)

All rows below have management_ip=192.0.2.91, interface=0/1, optional description blank. Baseline configured PVID=445, includes 445,545, excludes 746, tags 545,746. Operational Current may differ without changing these configured facts. CLI below is inside configure / interface 0/1 / ... / exit / exit. Missing global VLAN is informational; no global VLAN creation.

| action | tagged_vlans | pvid | Expected inner CLI / result |
|---|---|---|---|
| Add/Change | 901 | blank | vlan participation include 901; vlan tagging 901 |
| Add/Change | blank | 901 | vlan participation include 901; vlan pvid 901 (no tagging disable) |
| Add/Change | 901 | 901 | vlan participation include 901; vlan tagging 901; vlan pvid 901 (same ID legal) |
| Add/Change | 545 | 901 | vlan participation include 901; vlan pvid 901; existing tag remains |
| Add/Change | 746 | blank | vlan participation include 746; tagging already configured, no redundant tagging |
| Add/Change | 445 | 445 | vlan tagging 445 only; tagged PVID remains legal |
| Add/Change | 545 | 445 | No-op |
| Add/Change | blank | 445 | No-op (membership already included) |
| Add/Change | blank | blank | Invalid: membership or PVID required |
| Remove | 545 | blank | no vlan tagging 545; vlan participation exclude 545 |
| Remove | 746 | blank | no vlan tagging 746 only; exclude already configured |
| Remove | 902 | blank | vlan participation exclude 902 (not previously explicitly excluded); VLAN_NOT_IN_DATABASE warning |
| Remove | blank | blank | Invalid: tagged_vlans required |
| Remove | 545 | 901 or 445 | REMOVE_OPERATION_CANNOT_INCLUDE_PVID, no CLI |
| Remove | 445 | blank | PVID_REMOVAL_REQUIRES_REVIEW until preceding approved PVID change |
| Replace | 545 | blank | Invalid: action not supported |

Further scenarios: on an excluded and untagged VLAN 746, Remove 746 is No-op. On a included PVID 901 that is already tagged, PVID-only 901 is No-op and never untags it. On PVID 901 configured but not included, Add/Change pvid=901 includes membership even though the PVID number is unchanged. Add/Change tagged_vlans=545,745-746 retains compact expression if the whole requested set is a difference; a partial difference is rendered as sorted IDs. Optional description=New Customer adds only differing quoted description, before VLAN commands; matching membership plus changed description is not No-op. Description-only use belongs on Template 16 with no action/tagged/PVID fields.

Ordered example, rows 3–4 on same interface: Remove tagged_vlans=545,746 then Add/Change tagged_vlans=545,746 pvid=746. First row untags both and excludes 545 (746 already excluded); second includes/tags both and sets PVID 746. Final includes 445,545,746; tags 545,746; excludes none; PVID 746. Both rows carry compatible overlap warning and row references; original exclusion/tagging evidence remains unchanged.

Ordered example: row 3 Add/Change pvid=901; row 4 Remove tagged_vlans=445. Final includes 545,901; excludes 445,746; tags 545,746; PVID 901. Row 4 excludes 445 without untagging (445 was not tagged). Pending row 3 blocks dependency readiness; Reject row 3 restores observed PVID 445 and exposes PVID removal blocker. Reverse row order is unsafe. Do not infer Current Exclude as configured removal or normalize away excluded-but-tagged 746.

## Owner read-only validation and limitations

Run the linked operations guide's input/plan commands with authorized operator-managed credentials and one device worker first. Never send the generated proposals. Validate representative C3750X/C3850X/ME3600X/ASR920/EdgeSwitch releases independently before merge; record model/release, timestamps, digest, rows, observed evidence, expected CLI/warnings/blockers, owner verdict.

1. For Cisco independently inspect show running-config, show vlan id <ID> where applicable, and ME/ASR show ethernet service instance id <ID> interface <INTERFACE> detail. Check full nested endings, operational heading/scoped absence, ranges/any, Push symmetry/ethertype, group 0, Down and fallback. Single Dot1q/fixed QinQ no-rewrite must remain unverified blockers. Do not create device configurations to manufacture tests in this read-only step; use existing authorized lab states.
2. For EdgeSwitch inspect show running-config and show vlan <ID>. Check global VLAN list/name, full interface exit including PoE/storm-control/MTU, excluded+tagged lists, Current/Configured/Tagging differences, and missing global informational behavior. Plan Remove→Add/Change, PVID change→Remove, tagged=PVID, No-ops and unsafe reverse order against observed lab states.
3. Compare original input/evidence in JSON and Excel, exact per-row CLI, unique omitted child settings, before/after differences and ordered projection. Include an invalid row and unavailable target with successful peers. Edit only ordinary decisions in the one workbook and check digest-pinned consumption; approval never enables device writes.

Untested hardware/firmware behavior includes release-specific operational command syntax/output variants, full-config completion markers, default VLAN naming, generalized QinQ range/list support, rewrite forwarding/symmetry, empty-parent initialization, EdgeSwitch tagging of excluded/PVID VLANs and operational table layouts. Mocked tests prove parsing and deterministic planning, not hardware forwarding or command acceptance. Unknown output fails closed or uses labeled reliable fallback; it never certifies a firmware family. Templates 17–22 remain provisional regardless of successful schema/render tests. Owner live validation and explicit merge approval remain pending.
