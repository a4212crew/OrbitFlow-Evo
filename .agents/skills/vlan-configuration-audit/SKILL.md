---
name: vlan-configuration-audit
description: Use for read-only saved-configuration VLAN audit/compliance in OrbitFlow-Evo. Covers common policy semantics, family-specific AuditResolver rules, evidence, interface/database findings, and the boundary between VlanService observation and compliance. Do not use for configuration apply.
---

# VLAN Configuration Audit

## Purpose

Implement deterministic, read-only VLAN configuration audit from saved running configuration.

The authoritative flow is:

```text
Saved configuration
    -> vendor parser / VlanService observation
    -> preserved raw relationships and evidence
    -> family-specific AuditResolver
    -> validated audit facts
    -> common compliance engine
    -> report / future remediation planning
```

Separation of responsibility:

- **VlanService**: what is configured.
- **AuditResolver**: whether configured relationships are valid and what numeric/interface/database facts are authoritative for audit.
- **Compliance**: whether validated facts meet policy.
- **Reporting**: display structured findings; never reinterpret vendor syntax.
- **Apply/remediation**: out of scope for this read-only audit.

Saved configuration is authoritative for audit semantics. InterfaceService may supply observed identity/state and must be correlated by canonical interface name, but it does not override saved-configuration meaning.

Do not configure devices.

## Common Policy

```python
DATABASE_REQUIRED = {445, 545, *range(2400, 2445), 2449, 4001}
INTERFACE_REQUIRED = {*range(2400, 2445), 2449, 4001}
```

For every device:

```python
missing_database_vlans = DATABASE_REQUIRED - valid_database_vlans
```

For each Trunk, EVC, or Hybrid interface:

```python
trigger = (
    445 in valid_interface_vlans
    and 545 in valid_interface_vlans
    and (2449 in valid_interface_vlans or 4001 in valid_interface_vlans)
)
```

If triggered:

```python
missing_interface_vlans = INTERFACE_REQUIRED - valid_interface_vlans
```

If not triggered, interface compliance is **Not applicable**, not Pass.

Access interfaces are excluded from interface compliance.

Configuration problems are reported independently of trigger/compliance status.

## Common Parsing and Evidence Rules

- Parse comma/space lists and inclusive ranges; Huawei also supports `to`.
- Supported VLAN range for this audit is 2-4001.
- Preserve stanza/block nesting and source order where semantics depend on it.
- Preserve actual source text, source filename, and one-based line references.
- Never fabricate evidence for a missing statement.
- Never infer a VLAN solely from:
  - service-instance number;
  - subinterface suffix;
  - bridge-domain name;
  - VSI name or VSI ID;
  - pseudowire ID.
- Repeated stanzas must not create duplicate final interface rows.
- Shutdown interfaces are still audited and displayed as shutdown.
- Uncertain family selection is an explicit Review/Unable-to-assess outcome; never silently substitute another family.

## Interface Identity Correlation

Use canonical normalization only; do not fuzzy-guess.

Fields:

```text
interface_name
config_interface_name
interface_match_status
```

Statuses:

```text
matched
not_in_config
config_only
```

Rules:

1. Canonical match:
   - combine records;
   - `interface_name` = InterfaceService original;
   - `config_interface_name` = configuration/VlanService original;
   - status = `matched`.
2. InterfaceService only:
   - `config_interface_name = "not in config file"`;
   - status = `not_in_config`;
   - finding: Interface observed by InterfaceService is not present in inspected configuration.
3. Config only:
   - saved config remains authoritative;
   - `interface_name = "not observed"`;
   - retain actual config interface name;
   - status = `config_only`.

## Common Output

### Interface Results

One row per physical interface after child consolidation; logical aggregates remain separate.

Required concepts:

```text
device/family
interface_name
config_interface_name
interface_match_status
interface_type
description
shutdown
consolidated VLANs / forwarding domains
numeric mappings
tagged / untagged / native / PVID
child interfaces
trigger applicability
exact missing VLANs
configuration findings
explanation
recommendation
source filename
line references
source excerpts
```

### Database Results

One row per device with:

```text
database inventory
bridge-domain/VSI inventory and mappings where relevant
valid_database_vlans
exact missing required VLANs
configuration findings
explanation
recommendation
source filename
line references
source excerpts
```

## ME3600X

### Database

Only explicit global `vlan` definitions count as `valid_database_vlans`.

Do not substitute:

- `interface VlanX`;
- `encapsulation dot1q X`;
- `bridge-domain X`;
- service-instance number.

For global-member syntax:

```text
bridge-domain 2200
 member Gi0/1 service-instance 10
```

the global VLAN database must also contain VLAN 2200. Report missing global VLAN independently, including outside the common compliance set.

### Interface / EVC

Support conventional access/trunk and service instances.

Inline:

```text
service instance 10 ethernet
 encapsulation dot1q 4000
 bridge-domain 2449
```

Audit membership is bridge-domain **2449**, not SI 10 or ingress tag 4000.

Global member:

```text
bridge-domain 2449
 member Gi0/1 service-instance 10
```

Resolve exact `(interface, service-instance)` to BD 2449.

If inline and global exist:

- same BD -> valid;
- different BD -> conflict;
- neither -> unresolved;
- global reference to absent interface/SI -> invalid reference.

Only valid resolved BD memberships contribute.

Conventional allowed-list scope for this audit supports only:

```text
switchport trunk allowed vlan <basic list/range>
switchport trunk allowed vlan all
switchport trunk allowed vlan none
```

Do not implement `add`, `remove`, or `except`.

Findings include:

```text
UNRESOLVED_SERVICE_INSTANCE
CONFLICTING_BRIDGE_DOMAIN_BINDING
INVALID_BRIDGE_DOMAIN_MEMBER_REFERENCE
BRIDGE_DOMAIN_MISSING_GLOBAL_VLAN
DATABASE_REQUIRED_VLAN_MISSING
INTERFACE_REQUIRED_VLAN_MISSING
```

## ASR920

Treat supported ASR920 behaviour as EVC/service-instance forwarding, not conventional VLAN-database switching.

### Database

```text
valid_database_vlans =
    global bridge-domains
    UNION
    inline service-instance bridge-domains
```

Global BD counts even without a member. Inline BD counts.

Do not use:

- service-instance ID;
- encapsulation VLAN alone;
- global `vlan`;
- VFI vpn-id.

### Service Binding

For each service instance retain:

```text
interface_name
service_instance_id
description
encapsulation_type
outer_vlan
inner_vlan
inline_bridge_domain
global_bridge_domain
resolved_bridge_domain
binding_status
tagging_role
audit_vlan
evidence
```

Binding statuses:

```text
valid
unresolved
conflict
invalid_reference
```

Resolution:

- inline only -> valid;
- global only -> valid;
- inline == global -> valid;
- inline != global -> conflict;
- neither -> unresolved;
- global member references missing interface/SI -> invalid reference.

Only valid relationships contribute.

### Classification

Keep valid tagged and untagged resolved BDs separately before union.

```text
exactly 1 untagged + 0 tagged -> Access
0 untagged + >=1 tagged       -> EVC/Trunk
exactly 1 untagged + >=1 tagged -> Hybrid
>1 untagged                   -> Review
```

More than one untagged service instance is abnormal:

```text
MULTIPLE_UNTAGGED_SERVICE_INSTANCES
```

Do not trust ambiguous untagged memberships for compliance. Independently valid tagged memberships may remain usable.

Findings include:

```text
UNRESOLVED_SERVICE_INSTANCE
CONFLICTING_BRIDGE_DOMAIN_BINDING
INVALID_BRIDGE_DOMAIN_MEMBER_REFERENCE
MULTIPLE_UNTAGGED_SERVICE_INSTANCES
UNCLEAR_EVC_CLASSIFICATION
DATABASE_REQUIRED_VLAN_MISSING
INTERFACE_REQUIRED_VLAN_MISSING
```

## Catalyst 3750X / 3850

### Database

Only explicit global `vlan` definitions count.

`interface VlanX` does not create a database VLAN.

### Interfaces

Access interfaces are excluded from interface compliance.

Explicit trunk membership comes from the basic allowed VLAN list only.

Keep native VLAN separate. A native VLAN does not make a conventional Catalyst trunk Hybrid.

Validate configured allowed VLANs against the device VLAN database. A configured VLAN absent from the DB is a configuration finding and does not silently become a valid audit VLAN.

### All VLAN

3750X:

```text
switchport trunk encapsulation dot1q
+ switchport mode trunk
+ no explicit allowed-list
=> All VLAN
```

3850:

```text
switchport mode trunk
+ no explicit allowed-list
=> All VLAN
```

Do not display/expand All VLAN as 1-4094.

For audit:

```text
effective All-VLAN membership = device VLAN database
```

If a required VLAN is missing from the database on an All-VLAN trunk, recommendation is to add the global VLAN, not edit the allowed list.

Dynamic/unspecified switchport modes are not assumed operational trunks.

### Port-channel

Resolve physical `channel-group` members to the logical Port-channel.

The aggregate owns forwarding configuration. Member rows may show inheritance/evidence, but remediation belongs to the aggregate when the aggregate is authoritative.

Report explicit member/aggregate conflicts.

Findings include:

```text
ALLOWED_VLAN_NOT_IN_DATABASE
INVALID_ALL_VLAN_TRUNK
UNRESOLVED_SWITCHPORT_MODE
PORT_CHANNEL_CONFIG_CONFLICT
DATABASE_REQUIRED_VLAN_MISSING
INTERFACE_REQUIRED_VLAN_MISSING
```

## Huawei VRP

### Database

```text
valid_database_vlans =
    global vlan / vlan batch VLANs
    UNION
    valid VSI-bound dot1q termination VLANs
```

A termination VLAN contributes only when it is an L2 service bound to an existing VSI.

Do not use:

- VSI ID;
- numeric suffix in VSI name;
- Vlanif number;
- routed-subinterface dot1q;
- control-vid by itself.

### Parent / Child Consolidation

For a physical trunk:

```text
valid_interface_vlans =
    parent port trunk allow-pass VLANs
    UNION
    valid child L2 service termination VLANs
```

Consolidate valid child service subinterfaces into the physical parent and mark as consolidated subinterface.

Preserve:

- parent membership;
- child interface names;
- child descriptions;
- termination VLAN;
- control VID;
- VSI name;
- exact VSI binding evidence.

### L2 vs Routed

```text
dot1q termination
+ l2 binding vsi <name>
+ VSI exists
=> tagged L2 service; termination VLAN contributes
```

```text
dot1q termination
+ no l2 binding vsi
=> routed/detail only; no L2 audit contribution
```

Direct physical interface binding:

```text
physical interface
+ l2 binding vsi <name>
+ no dot1q termination
=> valid untagged L2 service
```

Do not invent a numeric audit VLAN for that untagged service from VSI name or VSI ID.

A referenced VSI that does not exist is invalid.

Do not invent VSI names in recommendations.

### PVID

- `port default vlan X` -> Access membership.
- `port trunk pvid vlan X` -> trunk PVID, not Access.
- `port hybrid pvid vlan X` -> hybrid PVID, not Access.

Findings include:

```text
VSI_REFERENCE_NOT_FOUND
L2_TERMINATION_WITHOUT_VALID_VSI
PARENT_INTERFACE_NOT_FOUND
PARENT_INTERFACE_NOT_TRUNK
DATABASE_REQUIRED_VLAN_MISSING
INTERFACE_REQUIRED_VLAN_MISSING
```

## IOS-XR / NCS540

This supersedes any older named-service baseline as the authoritative audit design.

### Bridge-domain Identity

Inventory BDs under:

```text
l2vpn
 bridge group <group>
  bridge-domain <name>
```

Identity is:

```text
(bridge_group, bridge_domain_name)
```

BD names remain names; they do not establish numeric VLANs.

### Numeric Mapping

A numeric business VLAN exists only through:

```text
existing bridge-domain
    -> attached existing l2transport subinterface
    -> explicit numeric encapsulation dot1q X
```

Only that `X` is the authoritative numeric audit VLAN.

Never infer from:

- BD name;
- subinterface suffix;
- pseudowire ID;
- unattached encapsulation.

### Untagged

An attached `l2transport` interface with `encapsulation untagged` can be a valid L2 attachment, but it does not establish a numeric VLAN under this audit.

Retain the service/BD as evidence and mark numeric mapping unresolved.

### Validation

Every BD interface reference must resolve to an existing configured `l2transport` interface.

Detect:

- missing referenced interface;
- non-l2transport attachment;
- unbound l2transport subinterface;
- multiple/conflicting BD attachments;
- l2transport without usable encapsulation.

Do not silently overwrite multiple BD attachments. Retain interface -> list[BD].

Routed dot1q subinterfaces are details only and are not unbound-L2 errors.

### Database

```text
valid_database_vlans =
    numeric dot1q values obtained through
    valid BD -> valid existing l2transport subinterface -> numeric dot1q
```

Do not union all configured l2transport dot1q values.

### Interface Consolidation

Consolidate valid child l2transport mappings into the physical parent.

```text
valid_interface_vlans =
    valid numeric mappings of child l2transport interfaces
```

Findings include:

```text
MISSING_BRIDGE_DOMAIN_INTERFACE_REFERENCE
UNBOUND_L2TRANSPORT_SUBINTERFACE
NON_L2TRANSPORT_BRIDGE_DOMAIN_ATTACHMENT
CONFLICTING_BRIDGE_DOMAIN_ATTACHMENTS
UNTAGGED_BRIDGE_DOMAIN_MAPPING_UNRESOLVED
L2TRANSPORT_WITHOUT_ENCAPSULATION
DATABASE_REQUIRED_VLAN_MISSING
INTERFACE_REQUIRED_VLAN_MISSING
```

## Ubiquiti EdgeSwitch

### Database

Only explicit VLAN declarations inside `vlan database` create database VLANs.

`vlan name X ...` annotates an existing VLAN; it must not independently create a database VLAN.

### Membership

Participation is authoritative.

Replay participation operations in source order:

```text
vlan participation include X -> membership += X
vlan participation exclude Y -> membership -= Y
```

Do not add PVID or tagged VLANs to membership.

Keep separately:

```text
configured_membership_vlans
configured_tagged_vlans
configured_pvid
```

Validate membership against the explicit VLAN database:

```text
valid_membership_vlans =
    configured_membership_vlans INTERSECT database_vlans
```

Then:

- tagged VLAN outside valid membership -> `TAGGED_VLAN_NOT_IN_MEMBERSHIP`;
- PVID outside valid membership -> `PVID_NOT_IN_MEMBERSHIP`;
- participating VLAN absent from DB -> `INTERFACE_VLAN_NOT_IN_DATABASE`.

Do not silently remove invalid configured tagging from evidence; retain both configured and valid tagged sets.

### Classification

```text
1 valid untagged + 0 valid tagged -> Access
0 valid untagged + >=1 valid tagged -> Trunk
1 valid untagged + >=1 valid tagged -> Hybrid
multiple/unclear untagged state -> Review
```

For a valid PVID that is a participating member and is not tagged, treat it as the untagged VLAN.

Description text such as "Access_port" or "Trunk_port" does not override actual VLAN semantics.

### LAG

Preserve EdgeSwitch aggregate/member relationships (for example `addport` and `interface lag N`).

When a LAG is the authoritative forwarding interface, configuration ownership/remediation belongs to the aggregate. Report explicit aggregate/member conflicts.

Findings include:

```text
TAGGED_VLAN_NOT_IN_MEMBERSHIP
PVID_NOT_IN_MEMBERSHIP
INTERFACE_VLAN_NOT_IN_DATABASE
MULTIPLE_UNTAGGED_MEMBERSHIPS
UNCLEAR_VLAN_CLASSIFICATION
AGGREGATE_CONFIG_CONFLICT
DATABASE_REQUIRED_VLAN_MISSING
INTERFACE_REQUIRED_VLAN_MISSING
```

## Common Finding Semantics

Configuration findings and compliance findings are separate.

Typical common identity findings:

```text
INTERFACE_NOT_IN_CONFIG
CONFIG_ONLY_INTERFACE
```

A configuration finding does not automatically make an otherwise unrelated interface non-compliant. Use the validated subset of facts when it remains trustworthy; use Review/Unable-to-assess only where ambiguity affects the audited relationship.

## Testing Expectations

Deterministic tests must cover every supported family and the common engine.

At minimum:

- exact database sets;
- exact trigger/not-applicable behaviour;
- exact missing VLANs;
- source/evidence fidelity;
- canonical interface matching;
- config-only / not-in-config identities;
- shutdown interfaces;
- invalid/unresolved bindings;
- no inference from names/suffixes/IDs;
- parent/subinterface consolidation;
- aggregate ownership/conflicts;
- unsupported/uncertain family -> explicit review;
- credential/raw-secret exclusion from reports/logs/spools.

Use synthetic cases for edge conditions not present in current samples, including duplicate/conflicting bindings and multiple untagged ASR920 services.

## Codex Task Guidance

Codex instructions for this work should remain concise. The normal implementation instruction is:

```text
Implement the revised VLAN configuration audit for Issue #65 using this routed skill.
Preserve existing shared architecture and read-only behaviour.
Update the existing PR and deterministic tests. Do not merge.
```

Do not duplicate this skill's platform rules into an Issue comment or Codex prompt unless a specific revision needs one narrow clarification.
