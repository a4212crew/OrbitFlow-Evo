---
name: cisco-network-cli
description: Use for Cisco IOS, IOS-XE, or IOS-XR behaviour in OrbitFlow, including interface collection, paging, access VLAN configuration, IOS-XR L2 subinterfaces, pre/post checks, commits, verification, and Cisco-specific caveats.
---

# Cisco Network CLI

## Use This Skill When

Use when a task changes Cisco-specific commands, configuration generation, verification, parsing assumptions, paging, or platform behaviour.

Also use the relevant task skill:
- interface collection -> `../interface-collector/SKILL.md`
- VLAN observation -> `../vlan-observation/SKILL.md`
- access VLAN provisioning -> `../access-vlan-provisioning/SKILL.md`

Do not implement Teleport transport here.

## Supported Families

- Cisco IOS
- Cisco IOS-XE
- Cisco IOS-XR

Keep IOS/IOS-XE and IOS-XR behaviour separate. Also keep OS family separate from device family/capability profile: model-specific features must not be inferred from the OS label alone.

## Interactive CLI

Cisco IOS, IOS-XE and IOS-XR CLI sessions use these EXEC session settings:

```text
terminal length 0
terminal width 511
```

These commands change only the interactive session, not running or saved device configuration. The selected Cisco adapter requires width setup before operational capability commands; short inventory identification probes continue to run before platform-specific setup.

Temporary `CiscoIOSCLI` and `CiscoXRCLI` shells require both settings when opening their owned channel. Borrowed `DeviceCLI` sessions request width using `configure(..., setup_commands=("terminal width 511",))`, and cache successful width setup on that shell across subsequent adapter calls and service lookups. A rejected width command fails explicitly and prevents further use of the affected shared shell; a timeout invalidates synchronization. Temporary-shell setup failures close their channel while leaving ownership of the parent transport unchanged.

Keep strict command-echo and prompt synchronization, dynamic prompt recognition, and normalized interface identities. Do not silently ignore setup rejection or add unverified wrapped-echo parsing. Deterministic wrapped-echo fixtures demonstrate a plausible timeout mechanism; the original live device echo bytes have not been captured.

Cisco's IOS-XR EXEC command reference documents session-only `terminal width` with a range of 0–512, but acceptance of 511 on a particular NCS540 release still requires operator validation. Manual width-511 lookups have succeeded on ME3600X (IOS) and ASR920 (IOS-XE); automatic initialization has not been live-validated. Acceptance and workflow behavior on NCS540 (IOS-XR), C3750X (IOS) and C3850 (IOS-XE) remain pending. See [Cisco width operator validation](../../../docs/user_manual/live-validation.md#cisco-terminal-width-issue-114).

## Interface Collection

Baseline:

```text
show interfaces description
```

Normalize platform output through collector logic.

## IOS / IOS-XE — Access VLAN Baseline

Use only where the interface/service model supports classic switchport access mode.

Conceptual candidate:

```text
configure terminal
interface <Port Name>
 description <Description>
 switchport
 switchport mode access
 switchport access vlan <VLAN>
 no shutdown
end
write memory
```

Pre/post checks may include:

```text
show running-config interface <Port Name>
show interfaces description | include <Port Name>
show interfaces switchport <Port Name>
show vlan id <VLAN>
```

Verification should confirm interface existence, description, access VLAN, appropriate administrative state, and command acceptance.

### Important IOS/IOS-XE Caveat

ASR920 or ME3600X services may use EVC/service-instance models rather than classic switchport access mode.

Do not assume every Ethernet interface supports `switchport`.

If the model is rejected, record failure. Do not guess another service model unless the task explicitly defines it.

## IOS-XR — L2 Subinterface Baseline

IOS-XR does not use classic IOS `switchport access vlan` syntax.

Conceptual L2 subinterface candidate:

```text
configure terminal
interface <Port Name>.<VLAN> l2transport
 description <Description>
 encapsulation dot1q <VLAN>
 no shutdown
commit
end
```

Pre/post checks may include:

```text
show running-config interface <Port Name>
show running-config interface <Port Name>.<VLAN>
show interfaces description | include <Port Name>
show interfaces <Port Name>.<VLAN>
```

Verification should confirm subinterface existence, dot1q encapsulation, description, successful commit, and appropriate interface state.

Store commit output in audit evidence.

Rollback should rely on captured pre-change state and explicit rollback logic, not guesses.

## Mapping Principle

Keep OrbitFlow platform identifiers separate from library-specific driver identifiers.

Do not assume `cisco_ios`, `cisco_xe`, and `cisco_xr` are interchangeable merely because a command happens to match.

Do not use the platform identifier as a proxy for hardware/service capability. Device family/profile may additionally control capability behaviour. Example:
- C3750X: `platform=cisco_ios`, classic switchport/VLAN capability profile.
- ME3600X: `platform=cisco_ios`, ME3600X profile with EVC/service-instance support.
- ASR920: `platform=cisco_xe`, ASR920 profile with EVC/service-instance support.
- C3850: `platform=cisco_xe`, classic switchport-oriented profile unless observed configuration requires otherwise.


## VLAN Observation

Approved read-only configuration source for Cisco IOS / IOS-XE:

```text
show running-config
```

### IOS / 3750X

Parse global `vlan <id>` sections as the traditional VLAN database.

Parse classic access/trunk interface facts including:
- `switchport mode access`
- `switchport access vlan <id>`
- `switchport mode trunk`
- optional `switchport trunk allowed vlan ...`
- optional `switchport trunk native vlan ...`

If an explicit trunk allowed list is absent, record it as not explicitly configured rather than inventing an explicit list.

Login/MOTD banners may themselves contain `#`; preserve the existing stable dynamic-prompt and command-echo synchronization behavior.

### EVC-capable IOS / IOS-XE families — ME3600X / ASR920

EVC capability is device-family/profile driven, not IOS-XE-only.

ME3600X live software output identifies the device as Cisco IOS, while its configuration still uses EVC/service-instance constructs. ASR920 runs IOS-XE and also supports EVC/service-instance constructs.

For EVC-capable profiles, in addition to classic switchport syntax, support observations such as `service instance <id> ethernet`, `encapsulation dot1q <vlan>`, and `bridge-domain <id>`.

Keep encapsulation VLAN and bridge-domain/service identity separate; do not force EVC state into the classic switchport model.

### IOS-XR / NCS540

Treat VLANs as service/subinterface constructs rather than assuming a classic VLAN database. The VLAN-observation collection command for IOS-XR is not yet approved; discuss it before implementation.

## Owner-approved execution requirements — 2026-10-17

Read [approved device execution](../../../docs/architecture/configuration/approved-device-execution.md)
for the initial Catalyst/EdgeSwitch milestone. **Implemented in PR #118 (Issue #117); owner lab validation and merge pending.**
Its exact template, prompt, switchport parsing, evidence, error and save requirements
override older conceptual execution examples for these families. Preserve existing
read-only behavior; new collectors must be independently callable through shared
sessions, with pure parsers, typed facts, original fields and correlated logging.

Use `show interfaces <interface> switchport`: static access/access VLAN, or trunk/
complete allowed set/native VLAN. Expand ranges, retain ALL and VLAN 1. Operational
Down does not fail configured-intent verification. VLAN database non-active status
is warning only. Accept learned-host VLAN modes config-vlan/config-vl. C3850 trunk
CLI omits the encapsulation selector. `write memory` completes when the original
EXEC prompt returns; record errors independently without requiring `[OK]`.

See [execution API](../../../docs/operations/configuration-execution-api.md) for
standalone calls and optional shared run/row/digest logging correlation, command/
target metadata, elapsed timing and safe failure diagnostics. Live validation of
the executor remains owner-controlled; sample transcripts are not validation.
Require matching normalized Name evidence. The approved C3750X trunk selector
change must verify without failing preservation; unrelated settings remain checked.
