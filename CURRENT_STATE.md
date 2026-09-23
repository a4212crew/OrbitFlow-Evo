# CURRENT_STATE.md — OrbitFlow Current State

Use this file as the concise source of truth for what is implemented and validated today.

> **OrbitFlow-Evo note:** This repository was cloned from OrbitFlow as an experimental evolution sandbox. Existing capability status below reflects the inherited OrbitFlow baseline unless a later OrbitFlow-Evo entry explicitly supersedes it.

Keep this document short. Historical implementation detail belongs in `docs/devlog/YYYY-MM.md`.

## Project

OrbitFlow is a multi-vendor ISP network automation platform designed to scale toward approximately 1,500 network devices.

Core rules and skill routing are defined in `AGENTS.md`.

## Architectural Direction

OrbitFlow is being developed as a reusable network-equipment capability platform and future OSS layer.

The intended dependency flow is:

```text
External OSS/BSS / REST API / GUI / schedulers
        -> Integration layer
        -> Application / workflow layer
        -> Reusable device capability layer
        -> Vendor-specific implementation
        -> DeviceSession / transport
        -> Network equipment
```

Key rules:
- separate target input from observed device identity;
- resolve management IP + credentials into a reusable DeviceContext where supported;
- treat stored inventory as latest-known observed context, not a CMDB/source of truth;
- implement each network-device capability once;
- vendor-specific command/parsing logic remains isolated;
- normalize CLI output into reusable structured models;
- workflows compose capabilities for audit, troubleshooting, provisioning, remediation, service assurance, and similar functions;
- REST/API consumers must call the same application/capability interfaces as internal workflows;
- separate observe -> analyze -> plan -> apply -> verify -> record;
- do not make raw CLI execution the primary external OSS interface.

Detailed model: `docs/architecture/device-capability-oss-model.md`.

## Current Architecture

### Device Inventory / Identification

The device inventory/identification MVP is implemented. `DeviceInventoryResolver`
accepts an existing `DeviceSession` plus management IP, reuses that session, and
returns normalized `DeviceContext` stable facts.

Current behaviour:
- deterministic detection of Cisco IOS, IOS-XE, IOS-XR, Huawei VRP, and Ubiquiti EdgeSwitch;
- family/profile selection for ASR920, C3850, C3750X, ME3600X, NCS540, NE05E, and EdgeSwitch;
- ME3600X remains `cisco_ios` while retaining an EVC-capable profile;
- serial-first physical identity reconciliation across management-IP changes;
- likely replacement/reassignment and hostname-collision event reporting, with no unsafe merge when serial evidence is absent;
- atomic latest JSON snapshots containing stable facts only and no credentials;
- failed attempts preserve the last successful facts while updating sanitized attempt status and error metadata;
- explicit controlled platform override support;
- returned context is suitable for capability and workflow consumers without duplicating detection logic.

Historical snapshots, approved-input batch orchestration, and production collection orchestration remain future work.

Documentation baseline:
- `.agents/skills/device-inventory/SKILL.md`
- `.agents/skills/excel-inventory/SKILL.md`
- `docs/architecture/device-capability-oss-model.md`

### Transport

All network-device access uses the shared OrbitFlow transport layer.

**Windows**
- Validated Teleport local-port-forward model using `tsh ssh -N -L`.
- Tunnel startup retries local-forward connections within `connect_timeout`.
- The first connected local-forward socket is retained and passed directly to
  Paramiko; OrbitFlow does not read or consume the device's SSH banner.
- Live validated successfully.

**Linux / Ubuntu**
- Validated `tsh proxy ssh` + Teleport private key/certificate + Paramiko `direct-tcpip` model.
- A second Paramiko session connects to the target device through the bastion channel.
- Live validated successfully.

Both target-device paths first use normal Paramiko authentication. If password
authentication is rejected, the shared target authenticator retries with
keyboard-interactive authentication using the same `DeviceCredentials.password`.
It responds only to prompts explicitly identified as password prompts. This
fallback does not affect Teleport/bastion authentication.

Higher-level workflows must use `connect_device(...)` / `DeviceSession` and must not recreate OS-specific transport.

### SSH Host-Key Behaviour

Current deployment defaults:
- `verify_bastion_host_key=False`
- `verify_device_host_key=False`

Permissive mode uses Paramiko `AutoAddPolicy` without persisting learned keys.

Strict verification remains configurable for future use. Custom Teleport CA verification is not implemented.

### Interactive CLI and Device Capabilities

Implemented reusable `CiscoIOSCLI` above `DeviceSession`.

Current behaviour:
- dynamic prompt detection for prompts ending in `#` or `>`;
- automatic `terminal length 0`;
- timeout-aware prompt reads using monotonic deadlines;
- command-echo synchronization to prevent stale prompts from completing a newly sent command;
- command echo removal;
- ANSI/control-sequence cleanup;
- trailing prompt removal;
- prompt changes tracked dynamically.

Windows live-device validation passed against Cisco ASR920 `NSW-STLEON-21CANB-BAS1` running IOS XE 17.06.07. The validation confirmed correct prompt detection, paging disablement, complete `show version` output, clean output handling, stale-prompt fix, and clean session teardown.

Implemented one reusable `InterfaceService` and normalized `InterfaceRecord` for
Cisco IOS, IOS-XE, IOS-XR, Huawei VRP / NE05E, and Ubiquiti EdgeSwitch. Each
platform has an isolated command/parser adapter, uses `DeviceSession`, disables
paging with the approved platform command, and returns a clear error for a
rejected setup or collection command. Empty command output produces an empty
collection; unrecognized non-empty output is a parser failure. The capability
does not guess fallback commands after a rejection. Huawei accepts both the
status-bearing and description-only forms of `display interface description`;
for the description-only form it uses the approved `display interface brief`
fallback and joins status by Huawei-canonical interface name (`Eth`/`Ethernet`,
`GE`/`GigabitEthernet`, `Loop`/`LoopBack`, and `Tun`/`Tunnel`), while preserving
the description-side name and subinterface suffix in normalized output. Known VRP
brief legends and protocol
suffixes such as `up(s)` are accepted; PHY remains authoritative for normalized
status. The
IOS-XR parser accepts
the platform's timestamp line before the interface table while remaining strict
about other unexpected content. `device_name` is optional:
vendor adapters extract it from their already-detected CLI prompt, while an
explicit caller-supplied name remains a compatibility override.
EdgeSwitch uses only `terminal length 0` and `show interfaces status all`; its
parser supports the confirmed multi-line status header, blank names, short
rows, and `(hostname) #` prompts while leaving unavailable admin state empty.

Implemented reusable read-only `VlanService` for Cisco IOS, IOS-XE, IOS-XR,
Huawei VRP, and Ubiquiti EdgeSwitch. It uses each platform's approved full
running-configuration command through the existing prompt-aware session layer.
The normalized snapshot separates interface VLAN references from VLAN,
bridge-domain, and service identities. Vendor adapters preserve classic
switchport/database, IOS-XE EVC, IOS-XR subinterface/L2VPN, Huawei
VLAN/Vlanif/dot1q/VSI, and EdgeSwitch participation/PVID/tagging semantics.
IOS-XE and IOS-XR bridge domains and Huawei VSIs are normalized as equivalent
service objects without treating their identity as a VLAN ID. IOS-XE EVC
bridge-domain modifiers such as split-horizon settings are excluded from that
identity. IOS-XR L2VPN
bindings preserve hierarchy and routed BVI membership, including interface
descriptions from bound interface blocks that have no encapsulation statement,
without deriving VLAN IDs from interface names. Huawei termination
observations retain both control VID and dot1q termination VID facts.
Observation performs no consistency or compliance decisions.

`scripts/live_validate_interfaces.py` provides a deliberately limited
single-device integration entry point for live validation of this existing
capability. It accepts caller-supplied credentials and `TransportConfig`, prints
normalized records, and does not implement inventory or production collection.

`scripts/live_validate_vlans.py` provides the equivalent single-device,
operator-prompted integration harness for `VlanService`. Its current target and
non-secret Teleport routing defaults are grouped at the top of the script; a
direct invocation prompts only for the device password. It prints normalized
VLAN/service objects and interface observations for manual comparison; its
existence does not constitute live validation of the VLAN capability.

## Repository Structure

Current major implementation areas:
- `src/orbitflow/transport/` — shared and OS-specific transport;
- `src/orbitflow/vendors/cisco/` — Cisco IOS/IOS-XE CLI behaviour;
- `src/orbitflow/vendors/huawei/` and `src/orbitflow/vendors/ubiquiti/` — vendor interface collection/parsing;
- `src/orbitflow/capabilities/` and `src/orbitflow/models.py` — reusable interface/VLAN capabilities and normalized records;
- `src/orbitflow/inventory/` — identification, reconciliation, and latest JSON snapshot storage;
- `scripts/live_validate_interfaces.py` — single-device interface integration validation;
- `scripts/live_validate_vlans.py` — single-device VLAN integration validation harness;
- `tests/` — deterministic mocked/unit tests;
- `.agents/skills/` — task/vendor-specific implementation guidance.

## Validation Baseline

- Windows transport: live validated.
- Linux transport: live validated.
- Cisco IOS/IOS-XE interactive CLI on Windows: live validated.
- Current automated test suite includes transport and Cisco CLI regression coverage.
- Device inventory tests cover all five platform identifiers and seven required families, override/ambiguity handling, reconciliation, failure retention, and secret exclusion.
- Interface capability tests cover all five platform identifiers with deterministic fake sessions.
- Interface capability has now been live validated on Cisco IOS, Cisco IOS-XE, Cisco IOS-XR, Huawei VRP, and Ubiquiti EdgeSwitch.
- VLAN observation has deterministic parser and command-selection coverage for
  all five platform identifiers and is now live validated across all five
  supported platforms: Cisco IOS, Cisco IOS-XE, Cisco IOS-XR, Huawei VRP, and
  Ubiquiti EdgeSwitch. Cisco IOS VLAN observation is live validated
  on the 3750X-class device `R-GEEL-MERCER-BCS1` at `172.25.20.2`, covering VLAN
  database discovery and names, access ports and non-default access VLANs, trunk
  mode, native VLANs, explicit trunk allowed VLAN lists, absent allowed-list
  behavior, VLAN list/range expansion, and interface descriptions. Validation
  also confirms the observation/policy boundary: the observer retains VLANs
  referenced on an interface even when they are absent from the observed VLAN
  database, without making a compliance decision. Cisco IOS-XE VLAN observation
  is live validated on the ME3600X at `10.251.10.50`, covering VLAN database
  entries and names,
  access VLANs, trunk allowed VLAN lists (including explicit `none`), VLAN range
  expansion, EVC dot1q and untagged encapsulations, multiple service instances
  per interface, and bridge-domain discovery/binding. Validation also confirms
  that bridge-domain modifiers are excluded from service identity and that VLAN
  IDs are not inferred from service-instance or bridge-domain identifiers.
  `mode=unknown` is expected when an access VLAN is configured without an
  explicit `switchport mode access` statement. Huawei VRP VLAN observation is
  live validated on NE05E device `R-WIND-168HIGH-RTR1` at `10.251.0.17`,
  covering the `vlan batch` VLAN database, `Vlanif`, `port default vlan`,
  `port trunk allow-pass vlan`, tagged trunk VLANs, `vlan-type dot1q`, `dot1q
  termination`, `control-vid`, and `l2 binding vsi` constructs. Validation
  confirms that VSI identity remains separate from VLAN identity and that VLAN
  identity is not inferred from VSI names. The live device used matching
  control VID and termination VLAN values; differing values remain covered by
  regression tests rather than this live validation. Ubiquiti EdgeSwitch VLAN
  observation is live validated on `R-ELST-TMARK-BAS8` at `10.125.13.138`,
  covering the VLAN database and VLAN ranges, VLAN names, `vlan pvid`, `vlan
  participation include`, `vlan participation exclude`, and `vlan tagging`.
  The validation confirmed tagged and untagged/PVID normalization across both
  physical and LAG interfaces, while preserving the observation/policy
  separation. Live validation records only the constructs exercised on the
  validation devices; other supported syntax remains covered only by
  deterministic regression tests where previously noted.

## Codex Orchestration — OrbitFlow-Evo

A local ChatGPT/Atlas-to-Codex orchestration foundation is implemented in OrbitFlow-Evo.

Current behavior:
- GitHub Issues act as scoped task records and orchestration state;
- the operator workstation runs `scripts/orchestration/controller.ps1`;
- Codex executes locally through the Codex CLI authenticated with the user's ChatGPT account;
- no `OPENAI_API_KEY` is required by the orchestration;
- each task uses an isolated `codex/issue-<number>` Git branch and dedicated Git worktree;
- the controller runs deterministic tests, commits/pushes the task branch, opens the PR, and returns the issue to `codex-review`;
- Atlas-requested corrections use a marked review comment plus `codex-revise` and update the same task branch/PR;
- issue comments track implementation/review iteration state;
- automated revision stops after iteration 15 and moves the task to `codex-replan-required`;
- no workflow auto-merges to `main`;
- Codex receives no Teleport or network-device credentials, and live validation remains local/operator-controlled.

Setup requires authenticated GitHub CLI and Codex CLI on the local workstation plus a one-time run of `scripts/orchestration/bootstrap.ps1`.

Validation status: implemented but not yet end-to-end validated. The first controlled test issue must confirm bootstrap, local Codex execution, worktree/branch creation, PR creation, automated tests, one Atlas-requested revision, and the review state transitions.

Detailed model: `docs/architecture/codex-orchestration.md`.

## Known Limitations

- Current SSH host-key defaults are permissive and therefore do not provide MITM protection.
- Inventory batch/input orchestration and historical snapshot retention are not yet implemented; the MVP stores latest state only.
- Live-device testing is integration validation and does not replace deterministic unit tests.

## Current Development Focus

The identification MVP is available as the observed-context layer. Future work can integrate approved input sources and production batch orchestration without moving live interface/VLAN state into inventory.

Relevant skill: `.agents/skills/device-inventory/SKILL.md`.
