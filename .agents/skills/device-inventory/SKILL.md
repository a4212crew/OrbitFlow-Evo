---
name: device-inventory
description: Use for OrbitFlow device identification, platform detection, normalized DeviceContext, physical-device identity reconciliation, stable observed device facts, inventory snapshots, and first/subsequent-run behaviour.
---

# Device Inventory and Identification

## Use This Skill When

Use for:
- identifying a network device from management IP plus runtime credentials;
- detecting vendor/platform safely;
- collecting relatively stable device facts;
- resolving physical-device identity across changing management IPs;
- reconciling replacements, hostname collisions, and duplicate observations;
- storing or reading latest observed device snapshots;
- producing a normalized DeviceContext for other capabilities.

Do not use this skill for interface/VLAN/routing/service/log observation logic, compliance decisions, provisioning commands, or Teleport transport implementation.

## Adjacent Capability Boundaries — Do Not Load by Default

These references identify owners of adjacent behaviour. Load one only when the task modifies that boundary or targeted source inspection shows the change must cross it.

- `../jumphost-connectivity/SKILL.md` — transport/session behaviour.
- `../excel-inventory/SKILL.md` — batch/list input and credential precedence.
- `../interface-collector/SKILL.md` — live interface observation.
- `../vlan-observation/SKILL.md` — live VLAN/service observation.
- vendor CLI skills — platform-specific identification commands/fingerprints.

## Principle

Inventory is an **observed device identity/context layer**, not a CMDB and not the authoritative definition of the network.

The live network is operational reality. Stored inventory is a reusable latest-known observation that helps OrbitFlow select the correct platform adapter and avoid repeated full discovery.

## Input Contract

Minimum intended target input:
- management IP/address;
- runtime credentials or approved credential reference.

Optional:
- SSH port;
- platform override/hint;
- supplied device name for compatibility/display only.

Credentials must never be written to an inventory snapshot.

## DeviceContext / Stable Facts

The normalized device identity should be able to represent, where available:
- `device_id`;
- management IP and optionally other observed management IPs;
- preferred/recent management IP;
- hostname;
- vendor;
- OrbitFlow platform/OS-family identifier;
- device family/profile;
- hardware model;
- normalized capability flags/profile where required for safe adapter behaviour;
- serial number;
- software/firmware version;
- uptime;
- last successful collection time;
- last collection attempt time;
- collection status/error.

Do not include interface status/descriptions, VLAN state, MAC tables, BGP/OSPF/VPLS state, counters, MTU findings, logs, or other volatile operational observations as permanent device-inventory facts.

## Physical Device Identity

Prefer serial number as the strongest physical-device key when reliably available.

Rules:
- same serial + different IP -> same physical device; associate the newly observed reachable IP rather than create a duplicate device;
- same IP + different serial -> re-identify the device and report a likely hardware replacement/reassignment event;
- same hostname + different serial -> keep separate device identities and report hostname collision;
- same hostname/model but serial unavailable -> do not auto-merge;
- insufficient identity evidence -> preserve separate/unresolved observation rather than guess.

Management IP is a reachability attribute, not the permanent physical identity.

## Platform Detection

Detection should be conservative and deterministic:
1. establish the approved DeviceSession;
2. observe safe connection/banner/prompt signals where useful;
3. run the smallest approved read-only identification probes;
4. match multiple vendor/platform fingerprints;
5. choose a platform only when evidence is sufficient;
6. allow an explicit operator platform override for controlled testing/edge cases.

Do not guess a platform from a single weak keyword or interface naming convention.

Platform/OS family and device family/capability profile are separate outputs. A device may run one OS family while requiring model-specific capability behaviour. For example, an ME3600X should be identified as Cisco IOS from its software output, while still carrying an ME3600X/EVC-capable device profile so VLAN service-instance parsing remains enabled.

Vendor-specific probe commands and signatures belong in vendor adapters/skills. Higher-level workflows must not contain their own Cisco/Huawei/Ubiquiti fingerprint logic.

## First Run

For an unknown management IP:

```text
IP + credentials
  -> connect
  -> detect platform
  -> collect stable device facts
  -> resolve physical-device identity
  -> create/update latest inventory snapshot
  -> return DeviceContext
  -> requested live capability runs
```

Where practical, reuse one established session for identification and subsequent requested live capabilities rather than reconnecting unnecessarily.

## Subsequent Run

For a known management IP/device:

```text
IP + credentials
  -> inventory lookup
  -> load known platform/context
  -> connect
  -> lightweight identity verification / refresh
  -> reconcile changes if needed
  -> update latest stable snapshot
  -> requested live capability runs again
```

Do not use stored live operational state as a substitute for recollection. Interface, VLAN, routing, service, and log capabilities must collect current state each run.

## Snapshot Behaviour

The initial storage implementation may keep only the latest successful stable-device snapshot.

On success:
- refresh stable facts and collection timestamps;
- report changed stable fields where useful.

On collection failure:
- preserve the last successful device facts;
- record the failed attempt timestamp/status/error separately;
- do not replace a good snapshot with an empty failed record.

Historical snapshot retention/change history is a separate future concern unless explicitly requested.

## Capability Integration

The inventory resolver should produce a DeviceContext usable by reusable capabilities:

```text
Input source
   -> Device Inventory / Resolver
   -> DeviceContext
      -> InterfaceService
      -> VlanService
      -> future MAC/BGP/OSPF/VPLS/log capabilities
      -> workflows such as compliance/troubleshooting/provisioning
```

Interface/VLAN/etc. capabilities must not reimplement platform discovery.

## Testing

Deterministic tests should cover:
- successful platform identification for supported fingerprints;
- device-family/model identification and capability-profile selection independent of OS family;
- unknown/ambiguous platform handling;
- explicit platform override;
- stable fact normalization;
- same serial on a different IP;
- different serial on the same IP;
- hostname collision with different serials;
- missing serial/no unsafe merge;
- failure preserving last successful facts;
- credentials absent from snapshots/log/error output.

Live-device testing is integration validation and does not replace deterministic tests.
