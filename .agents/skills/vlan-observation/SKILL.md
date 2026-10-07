---
name: vlan-observation
description: Use for read-only multi-vendor VLAN and forwarding-domain observation in OrbitFlow, including per-interface ingress classification, bridge-domain/service mappings, VLAN database/equivalent service objects, normalization, and vendor adapter boundaries. Consistency/policy checking is explicitly out of scope.
---

# VLAN Observation Capability

## Purpose

Build one reusable read-only capability that answers:

1. What tagged or untagged traffic does each real interface accept?
2. What forwarding domain does that traffic enter?
3. What VLAN, bridge-domain, or VSI forwarding-domain objects exist on the device?

Vendor parsers report observed facts only. A separate analysis/policy layer decides whether those facts are consistent or compliant.

## Architecture Rules

- Consume a resolved DeviceContext from device inventory; do not implement independent platform discovery here.
- Adapter/parser behaviour may depend on platform plus device family/capability profile.
- Reuse DeviceSession and the shared CLI lifecycle; do not create transport logic here.
- Keep vendor commands and parsers isolated.
- Vendor parsers own reusable observation semantics. Reporting must consume normalized output rather than reconstructing vendor syntax. A routed audit resolver may validate preserved saved-configuration relationships/evidence and derive audit-specific facts; that logic belongs in the audit skill, not reporting.
- Interface existence and references to an interface from another configuration section are separate facts.
- Never create a normal interface identity solely because L2VPN, bridge-domain, VSI, VLAN, or service configuration references that name.
- Unmatched service references should be retained as validation findings for a later analysis layer, not promoted to real interfaces.
- Keep observation separate from consistency analysis, planning, apply, and verification.
- Do not add or change device commands without explicit operator approval.

## Normalized Interface Forwarding Contract

Every supported platform should normalize real interfaces into:

```text
interface_name
port_type
untagged_vlan
tagged_vlans
bridge_domains
service_mappings
```

Allowed `port_type` values:

```text
access
trunk
hybrid
evc
service
routed
```

Semantics:

- `interface_name`: an actual configured/observed interface identity.
- `untagged_vlan`: the forwarding VLAN/domain selected for an accepted untagged frame when a numeric VLAN identity exists. Use `UNTAGGED` when untagged traffic is accepted but no numeric VLAN identity exists. Blank means untagged ingress is not applicable/accepted by the observed construct.
- `tagged_vlans`: outer tagged VLANs accepted by the interface. Preserve `ALL`, `NONE`, explicit lists, and blank as distinct states.
- `bridge_domains`: forwarding-domain identities used by the interface. These may be numeric VLAN/BD values or named domains.
- `service_mappings`: exact normalized ingress-to-forwarding relationships, for example `untagged -> 100`, `2400 -> 500`, or `2400 -> RSVD-RSP0`.
- Routed interfaces remain visible. A routed dot1q subinterface may show the accepted tagged VLAN and a mapping such as `860 -> routed`, with no bridge-domain.
- SVI/BVI/Vlanif interfaces are routed interfaces associated with a forwarding domain, but do not themselves imply tagged/untagged Ethernet ingress.

One report row/profile is produced per actual interface. Multiple vendor service constructs on the same physical interface may aggregate into that profile only when exact `service_mappings` are retained.

QinQ/second-tag details may remain as supporting normalized detail. Do not flatten an inner VLAN into the top-level `tagged_vlans` list as though it were an independent outer ingress VLAN.

## Tagged VLAN Rules

For conventional Cisco trunks:

- explicit `switchport trunk allowed vlan ...` -> normalized explicit tagged VLAN set;
- no allowed-VLAN statement -> `ALL`;
- explicit `switchport trunk allowed vlan none` -> `NONE`;
- no explicit native VLAN -> native/default untagged VLAN 1 where that platform behaviour applies.

Do not expand `ALL` into VLAN 1-4094.

## Vendor Semantics

### Cisco IOS — 3750X

Classic access/trunk switching.

Access:

```text
switchport mode access
switchport access vlan 100
```

normalizes to:

```text
port_type: access
untagged_vlan: 100
bridge_domains: 100
service_mappings: untagged -> 100
```

Trunk:

```text
switchport mode trunk
switchport trunk native vlan 10
switchport trunk allowed vlan 100,200,300
```

normalizes to:

```text
port_type: trunk
untagged_vlan: 10
tagged_vlans: 100,200,300
bridge_domains: 10,100,200,300
service_mappings: untagged -> 10; 100 -> 100; 200 -> 200; 300 -> 300
```

### Cisco IOS — ME3600X

ME3600X supports both conventional switchport behaviour and EVC/service-instance behaviour.

Conventional access/trunk follows the classic Cisco model above.

EVC example:

```text
service instance 10 ethernet
 encapsulation dot1q 100
 bridge-domain 500
```

normalizes the relationship as:

```text
port_type: evc
tagged_vlans: 100
bridge_domains: 500
service_mappings: 100 -> 500
```

Multiple service instances on one interface aggregate into one interface profile while preserving each exact service mapping.

For `encapsulation untagged`, normalize the accepted untagged traffic to the bridge-domain/VLAN used internally.

### Cisco IOS-XE — ASR920

Treat the supported ASR920 model as EVC/service-instance forwarding.

Multiple service instances may aggregate into one physical-interface profile:

```text
untagged -> 700
100 -> 500
200 -> 600
```

with:

```text
port_type: evc
untagged_vlan: 700
tagged_vlans: 100,200
bridge_domains: 500,600,700
```

Do not model ASR920 as a conventional VLAN-database switch for the supported OrbitFlow behaviour.

### Cisco IOS-XR — NCS540

IOS-XR service/subinterface semantics are normalized from actual configured interfaces plus L2VPN forwarding relationships.

L2 subinterface:

```text
interface TenGigE0/0/0/18.2400 l2transport
 encapsulation dot1q 2400
```

attached to named bridge-domain `RSVD-RSP0` normalizes to:

```text
port_type: service
tagged_vlans: 2400
bridge_domains: RSVD-RSP0
service_mappings: 2400 -> RSVD-RSP0
```

A routed dot1q subinterface normalizes to:

```text
port_type: routed
tagged_vlans: <outer VLAN>
bridge_domains: blank
service_mappings: <outer VLAN> -> routed
```

BVI interfaces are `routed` and may reference an existing bridge-domain.

If L2VPN references an interface that does not exist as a configured/observed interface, retain that as a validation finding only. Do not create a synthetic interface row.

### Huawei VRP — NE05E

Traditional switching:

- `port default vlan X` -> access/untagged X;
- trunk allow-pass VLANs -> tagged set and corresponding forwarding domains;
- a combination of untagged/PVID plus tagged membership -> hybrid.

Service subinterface with dot1q/termination plus `l2 binding vsi <name>`:

```text
port_type: service
tagged_vlans: <outer VLAN>
bridge_domains: <VSI name>
service_mappings: <outer VLAN> -> <VSI name>
```

Dot1q plus Layer-3 configuration with no L2 binding:

```text
port_type: routed
tagged_vlans: <outer VLAN>
service_mappings: <outer VLAN> -> routed
```

A physical Layer-3 interface is `routed` with no forced VLAN semantics.

`VlanifX` is `routed` and related to VLAN/domain X; it is not an ingress Ethernet tagging point.

### Ubiquiti EdgeSwitch

Use:

```text
vlan pvid
vlan participation include
vlan participation exclude
vlan tagging
```

Normalization:

- participation determines membership; PVID and tagging do not create membership;
- a PVID may describe untagged handling only when that VLAN is a participating member;
- all participating VLANs tagged and no valid untagged member -> `trunk`;
- exactly one valid participating untagged/PVID VLAN and no tagged members -> `access`;
- one valid participating untagged/PVID VLAN plus tagged members -> `hybrid`.

Observation should preserve configured participation, tagging, PVID, and exclusions distinctly enough for the audit layer to report invalid combinations rather than silently normalize them away.

Example:

```text
vlan pvid 100
vlan participation include 100,200,300
vlan tagging 200,300
```

becomes:

```text
port_type: hybrid
untagged_vlan: 100
tagged_vlans: 200,300
bridge_domains: 100,200,300
service_mappings: untagged -> 100; 200 -> 200; 300 -> 300
```

Excluded VLANs may be retained as supporting facts but are not active forwarding domains. Repeated participation include/exclude statements should preserve source-order semantics; consistency findings remain the audit layer's responsibility.

## Normalized Forwarding-Domain Database Contract

The database/equivalent service-object model is:

```text
object_type
object_id
name
domain_id
```

Supported object types:

```text
vlan
bridge_domain
vsi
```

Naming rule:

- if a configured object name exists, use it;
- otherwise `name = object/domain ID`.

Do not infer database-object existence solely from an interface reference.

### Cisco 3750X / 3850

- conventional VLAN object -> `object_type = vlan`;
- `object_id = VLAN ID`;
- `domain_id = VLAN ID`;
- preserve configured VLAN name, otherwise name falls back to VLAN ID.

### EdgeSwitch

Use the device VLAN database as the source of conventional VLAN objects.

- `object_type = vlan`;
- interface participation does not create a VLAN database object.

### ME3600X

Both object types may legitimately exist:

- conventional VLAN -> `vlan`;
- EVC bridge-domain -> `bridge_domain`.

Do not collapse distinct configured object types merely because their numeric identifiers match.

### ASR920

For the supported OrbitFlow model:

- EVC forwarding domain -> `bridge_domain`;
- ingress encapsulation VLANs remain interface/service mappings, not database objects.

### NCS540 / IOS-XR

The forwarding-domain database source of truth is the L2VPN hierarchy only:

```text
bridge group <BG>
 bridge-domain <BD>
```

Normalize as:

```text
object_type: bridge_domain
object_id: <bridge-group>/<bridge-domain>
name: <bridge-domain>
domain_id: <bridge-domain>
```

Do not inspect interface encapsulation or interface bindings to create NCS540 observation database objects. Audit-specific numeric VLAN availability is derived later by the IOS-XR AuditResolver only from a valid bridge-domain -> existing l2transport interface -> numeric dot1q relationship.

### Huawei VRP

- conventional VLAN -> `vlan`;
- VSI -> `vsi`;
- `domain_id` is the VLAN ID or VSI name respectively;
- `Vlanif` does not create a database object;
- service/interface references do not implicitly create a VLAN or VSI object.

## Observation vs Validation

The observation capability records normalized facts. Examples of later validation findings include:

- interface references a forwarding domain that does not exist;
- bridge-domain/VSI references an interface that does not exist;
- conventional switchport references a VLAN absent from the VLAN database.

Do not implement compliance decisions here unless explicitly requested.

## Testing Expectations

Deterministic tests should cover:

- normalized access/trunk/hybrid/EVC/service/routed semantics;
- `ALL`, `NONE`, explicit tagged VLANs, and blank as distinct states;
- multiple EVC mappings aggregated without losing mapping identity;
- routed physical and routed subinterface behaviour;
- SVI/BVI/Vlanif handling;
- unmatched service-binding references not creating interfaces;
- per-platform forwarding-domain database objects;
- database objects not inferred from interface references;
- name fallback to domain/object ID;
- QinQ supporting detail without corrupting outer tagged VLAN normalization.
