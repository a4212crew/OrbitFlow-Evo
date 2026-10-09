# Interface VLAN Methodology Resolution and Engineer Review — Proposed

Status: approved design direction; **Gap A implemented in Issue #79** with
synthetic validation. Engineer decision import and template integration (B/C)
remain proposed. This design extends
existing read-only audit and offline Configurator Phases 1–2. It does not
introduce network device configuration or change the v1 Change Plan contract.

## Authority and existing implementation

Reference: operator-provided `VLAN Configuration Methodologies - Documentation Expanded(1).xlsx`
(workbook design reference, not an executable policy or committed repository
asset). Compare examples and parser contracts with real sanitized backup
fixtures before adopting them as tested behavior.

Reuse `src/orbitflow/vendors/configuration_facts.py` and
`src/orbitflow/compliance/resolvers.py` (`AuditResolver` family dispatch), plus
existing `VlanService`, inventory, configuration backup, shared reporting and
execution infrastructure. The resolver already validates conventional Cisco
switching, EVC local/global binding, XR bridge-domain attachments, Huawei VSI,
and EdgeSwitch membership. Issue #79 adds M01–M08 review records and a separate
Excel export; it does not import engineer decisions or select templates. The current Configurator only
renders allowlisted Cisco VLAN creation from normalized JSON and requires
per-plan approval; raw Excel import and pre-approved template policy do not
exist. Keep audit policy outputs backward compatible.

## Proposed methodology mapping

| ID | Existing interpretation to reuse | Planned classification granularity |
|---|---|---|
| M01 | Cisco conventional access/trunk, VLAN database | Interface and switchport mode |
| M02 | Global bridge-domain member to EVC service-instance relation | EVC service instance, global binding |
| M03 | Service-instance-local bridge-domain relation | EVC service instance, local binding |
| M04 | IOS-XR L2VPN bridge group/domain to L2 attachment | Subinterface and attachment relation |
| M05 | EdgeSwitch explicit VLAN participation, tagging, PVID | Interface/LAG member owner |
| M06 | Huawei conventional access/trunk/hybrid | Interface and switchport mode |
| M07 | Huawei VLAN termination bound to VSI | Termination/subinterface and VSI relation |
| M08 | Huawei NE05E VLAN-tagged subinterface | Logical interface with explicit `vlan-type dot1q <VID>` |

The methodology is a classification of observed configuration, **not** an
automatic template selection. A single device, and even a single physical
interface, can host multiple service constructs/methods. Preserve service IDs,
outer/inner tags, encapsulation, domain/VSI ownership and source lines; do not
flatten QinQ or convert unrelated domain IDs into VLANs. A global and local EVC
binding on the same service must be reported with both sources; distinguish an
equivalent duplicate from a conflict. Issue #85 classifies proven equivalent
bindings as standard while retaining both sources; conflicts require review.
Preserve unresolved references and unknown syntax explicitly.

### Huawei VLAN-tagged subinterfaces (Issue #79 revision)

M08 is independent of M06 switching and M07 termination/VSI. A configured NE05E
logical subinterface with `vlan-type dot1q <VID>` has subtype
`vlan_tagged_subinterface`. Its workbook Mapping retains `outer_vlan`, an empty
`inner_vlan`, `encapsulation_type=vlan-type-dot1q` and `role=not_determined`.
The interface, parent and source evidence preserve the configured spelling and
line numbers. Neither a subinterface suffix nor a description establishes a tag
or forwarding role. Encapsulation alone does not establish L2 forwarding, VSI
binding, audit/database membership or template eligibility.

Valid encapsulation resolves without review solely for an undetermined role.
Missing parents, distinct conflicting tags, mixed switching/termination/VSI
constructs and unsupported syntax retain source-backed review findings.
Repeated identical tags are not a conflict. Absent/malformed encapsulation never
establishes M08. The existing numeric syntax range (1–4094) and canonical invalid
numeric tag `ValueError` behavior are unchanged; this is separate from the audit
policy range. Case/whitespace variants of Huawei interface declarations and
encapsulation are observed as review-only facts and promoted only for methodology
resolution through the same family resolver. Compliance excludes these facts.

The existing workbook columns and Details JSON carry M08 without schema changes.
Operator-provided NE05E examples are covered by offline deterministic fixtures;
no deployment or live-device validation is implied.

### Observed tag-rewrite attributes (Issue #79 revision)

The existing configuration-fact observer retains `TagRewrite` facts separately
from encapsulation and forwarding-domain binding. Methodology mappings expose
`rewrite_profiles` with direction, operation, tag count, symmetric flag, exact
parameters, ordered output tags, interface/service identity and sanitized source
evidence. Tag count means removed tags for POP, added tags for PUSH and input
tags for TRANSLATE. These review facts are excluded from compliance resolution.

Strict recognized syntax includes ingress POP 1/2, PUSH dot1q (optionally
second-dot1q) or dot1ad/dot1q stacks, and TRANSLATE 1-to-1, 1-to-2, 2-to-1,
2-to-2 with an explicit matching output stack. Optional `symmetric` is retained.
Unknown modifiers, malformed stacks and other spellings go to sanitized review.
Recognition follows [Cisco's Ethernet interface command grammar](https://www.cisco.com/c/en/us/td/docs/routers/asr9000/software/lxvpn/command/reference/b-lxvpn-cr-asr9000/ethernet-interfaces-commands.html);
it does not establish model/release support or template eligibility. Every
profile records `platform_support=not_assessed`. Family projection supports
ME3600X/ASR920 EVC services and NCS540 L2 transport subinterfaces; other scopes
require review. Distinct profiles on the same service remain conflicting evidence.

ME3600X explicit trunk mode plus `allowed vlan none` may coexist with EVC service
instances. The M01 context retains configured switching statements separately
from M03 service mappings, without a mixed-construct warning solely for that
coexistence. Other switching conflicts, unresolved bindings and missing parents
remain visible. No compliance facts, workbook contracts or template decisions
change.

## Approved standards review (Issue #81)

`methodology_standards.py` classifies the methodology projection independently
of authoritative audit findings, health and compliance. It consumes typed
configuration facts and exact relationships; reporting never interprets CLI.
Each record retains its resolution, original audit findings, a separate
`standard_findings` list and a primary `standard_finding`. The primary finding
prioritizes confirmed wrong configuration, then review, non-standard and standard
configuration; severity breaks ties. `wrong_configuration` uses `error`, review
and working non-standard use `warning`, and informational exceptions use
`informational`. `critical` is reserved; no current rule assigns it.

| Pattern | Standards outcome |
|---|---|
| EdgeSwitch final explicit exclusion with retained tagging | `standard_configuration` / informational `EXCLUDED_VLAN_TAGGING_INACTIVE`; independent PVID, membership and syntax conflicts still require review. |
| Allowed trunk VLAN absent from database | `standard_configuration` / informational `ALLOWED_VLAN_NOT_IN_DATABASE`; required-VLAN compliance remains unchanged. |
| Known EdgeSwitch switchport style with selected access/trunk mode | `working_non_standard` / `EDGESWITCH_SWITCHPORT_STYLE`; unknown, incomplete or mixed native/alternative syntax requires review. |
| IOS/IOS-XE selected access/trunk mode with residual settings | `working_non_standard` / `RESIDUAL_SWITCHPORT_SETTINGS`; competing modes, routed intent and unsupported allowed operations remain reviewable. |
| ME3600X trunk mode, allowed VLAN none and valid distinct EVC services | `standard_configuration` / `ME3600X_STANDARD_EVC_TRUNK`; absent prerequisites, unresolved bindings and overlapping ingress tags require review. QinQ inner tags remain distinct. |
| Confirmed physical-member/LAG VLAN differences | `wrong_configuration` / error `LAG_MEMBER_CONFIGURATION_MISMATCH`; retain the explicit membership reference, both original stanzas and exact field differences before inherited/database-filtered facts. Compare every configured field: an omitted counterpart with unknown effective value yields `review_needed` / warning `LAG_MEMBER_CONFIGURATION_UNRESOLVED`, with per-field explanation and a null unknown value, never assumed equality. Entirely unconfigured members may inherit supported aggregate ownership; partial settings do not prove field-level inheritance. Confirmed differences take precedence over simultaneous unknowns. Missing or ambiguous membership requires review. |
| No relevant L2 evidence | `not_applicable` / `NO_RELEVANT_L2_SERVICE`; incomplete or unsupported L2 constructs remain reviewable. Empty consolidated parent rows remain suppressed. |

Known alternate EdgeSwitch statements and bare Cisco `switchport` are review-only
facts excluded from audit inputs. Unknown forwarding evidence still uses bounded,
fail-closed disclosure. The vocabulary includes the safe `mode` keyword; it does
not authorize arbitrary operands. Original safe evidence retains indentation,
source lines and service context; shared workbook writing protects formula cells.

The main sheet adds Configuration Classification, Finding Severity, Standard
Finding and Engineering Review Decision. Only Interface, Service Instance and
Evidence Source are removed; Config Interface, Evidence Lines and Configuration
Facts Digest remain. Internal records and streamed Details retain all identities,
sources, digests and secondary findings. Run Errors and spool recovery remain.
Legacy records without standards fields export an unavailable-assessment warning.

Every generated record defaults to `not_reviewed`. `accepted`,
`accepted_exception`, `remediation_required` and `deferred` are reserved for actual
durable engineer decisions. No review import, operational verification,
remediation, executable template selection or approval is implied.

## Proposed bulk workflow

1. Accept a typed Excel target list: stable row ID, device, physical/logical
   interface, action (create, update, detach, remove or retire), service identifiers and intended change.
2. Resolve device identity and inspect captured configuration; attach a source
   snapshot digest, original CLI evidence and detailed method/subtype per
   interface or service. Missing/stale/ambiguous evidence goes to review.
3. Export a resolution workbook with target list, read-only resolution/evidence,
   review decisions and candidate templates. Group **homogeneous evidence** for
   review without losing per-row provenance. A new interface may have no stanza;
   validate parent and resource availability instead of inventing current state.
4. Engineer verifies the interpretation and explicitly selects a versioned,
   compatible template; allow exclusions and per-row override. Never make a
   template choice purely from device family or classifier ID.
5. Import reviewed decisions with reviewer identity, decision time, exact
   source snapshot/digest, template/version, parameter values and row IDs.
   Reconcile input changes; stale/replaced evidence invalidates review.
6. Generate minimal deterministic patches, explicit preconditions, desired
   postconditions and independent per-device plan digests; a parent batch
   manifest records full membership, excluded rows, ordering and rollout limits.
7. Apply policy: pre-approved **standard** templates qualify only inside their
   approved target/parameter/batch scope. Free-form CLI (including Excel CLI)
   is **advanced**, with elevated authenticated human approval. An operator
   approval label is not an authentication mechanism. No silent partial success.
8. Future Phase 3 must recheck live state, authority, backups and verification
   before applying anything; offline review or pre-approval is not proof that
   live state remains unchanged.

Excel is a review/input surface; canonical JSON plans, evidence digests and
approval records are authoritative. Never embed credentials or secret-bearing
raw configurations in Excel, logs, issues or committed fixtures.

## Gap assessment and implementation sequencing

- **Existing foundations:** family-specific audit resolution and findings;
  original evidence and parent/subinterface associations; EVC inline/global
  binding facts; XR and Huawei/VSI resolution; EdgeSwitch tagged/PVID mapping;
  synthetic regression tests in `tests/test_vlan_configuration_audit.py`.
- **Gap A — Methodology readout:** M01–M08/subtype fields and evidence-backed
  service-scoped rows, accurate mixed/conflict flags, backward-compatible audit
  output and workbook export. Keep parsers/resolver owned by existing modules.
- **Gap B — Engineer review:** source-bound review decisions, stable row IDs,
  group validation and override/exclusion import; review must not be confused
  with approval to execute.
- **Gap C — Template integration:** candidate catalogue informed by workbook
  Port Templates (`C-ACCESS`, `C-TRUNK`, `C-ADD`, `C-VOICE`,
  `H-ACCESS`, `H-TRUNK`, `E-TAGGED`, `EVC-GLOBAL`, `EVC-LOCAL`,
  `XR-AC`, `H-VSI`), versioned approval, compatibility, standard/advanced
  policies and bulk Change Plans. These are **candidates**, not approved
  executable templates.

Implement Gap A first as a dedicated Codex Issue, verify against synthetic and
accessible real backup fixtures (the workbook references a backup corpus but
is not itself that corpus), then tackle B/C separately. No implementation,
GitHub Issue, or PR is created by this document.

## Addition: creation and removal evidence

The operator-provided `VLAN Configuration Methodologies - Creation and Removal.xlsx` complements the original workbook with method-specific creation and removal examples, `Removal Templates` (RM-series), `Removal Workflow` (D-series), and `Removal Acceptance Cases` (T-series). Treat these as candidate specifications, not production-proven adapters. See [configuration removal](configuration-removal.md). Existing read-only compliance outputs and policy decisions must not be changed by adding removal/dependency evidence.
