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
and EdgeSwitch membership. Issue #79 adds M01–M07 review records and a separate
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

The methodology is a classification of observed configuration, **not** an
automatic template selection. A single device, and even a single physical
interface, can host multiple service constructs/methods. Preserve service IDs,
outer/inner tags, encapsulation, domain/VSI ownership and source lines; do not
flatten QinQ or convert unrelated domain IDs into VLANs. A global and local EVC
binding on the same service must be reported with both sources; distinguish an
equivalent duplicate from a conflict and require review rather than selecting
one silently. Preserve unresolved references and unknown syntax explicitly.

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
- **Gap A — Methodology readout:** M01–M07/subtype fields and evidence-backed
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
