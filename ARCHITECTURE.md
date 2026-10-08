# OrbitFlow-Evo Architecture

## 1. Purpose

This document describes the current approved technical architecture of OrbitFlow-Evo.

It is a stable reference for ChatGPT / Atlas, Codex, developers, and future project sessions. Architecture recorded here should reflect implemented or explicitly approved design. Experimental ideas are not established architecture until reviewed and accepted.

## 2. Architectural Principles

1. Shared capabilities should be vendor-independent wherever practical.
2. Vendor-specific behaviour must remain isolated behind vendor implementations.
3. Transport must remain separate from parsing and business logic.
4. Parsers report observed facts rather than inferred configuration.
5. Credentials must not be embedded in source code or inventory snapshots.
6. Deterministic logic should have automated tests.
7. New capabilities reuse the shared transport layer.
8. Changes should remain small, reviewable, and testable.
9. OrbitFlow and OrbitFlow-Evo remain operationally isolated.
10. Repository documentation is the authoritative development context.
11. Multi-device execution is device-scoped and uses one shared bounded execution layer; feature modules do not own independent concurrency.
12. Large multi-device results use a reusable execution-result spool and output-consumer boundary so device execution is independent of Excel, API, database, or other destinations.

## 3. High-Level Dependency Model

```text
External OSS/BSS / REST API / GUI / schedulers
        -> Integration layer
        -> Application / workflow layer
        -> Analysis / policy / audit-resolver layer (when required)
        -> Shared device-execution layer
        -> Reusable device capability layer
        -> Vendor-specific implementation
        -> DeviceSession / transport
        -> Network equipment
```

Capabilities must not implement independent SSH or jumphost transport.

For multi-device operations, capabilities remain single-device units. The shared device-execution layer schedules complete per-device workflows, enforces the configured active-device limit, isolates failures, and coordinates per-device results. One worker owns one target's DeviceContext, transport/session/CLI resources, and intermediate state. Shared mutable resources such as inventory persistence, report output, and process-wide logging state remain owned by their shared layers and must be concurrency-safe.

## 4. Shared Device Execution

OrbitFlow uses one shared bounded execution layer for multi-device operations. The concurrency boundary is one target device, not one capability call.

The initial approved read-only setting is configuration-driven at 10 concurrent devices. A freed worker may immediately take the next pending target; fixed batch barriers are not required. Feature modules must not create independent executors.

Configuration-changing workflows may reuse the execution layer but require an explicitly approved concurrency limit rather than implicitly inheriting the read-only setting.

### Approved Large-Run Result Spool

For large multi-device workflows, OrbitFlow will persist generic per-device execution outcomes through one shared result-spool layer rather than retaining the complete run result in feature memory.

```text
Shared device-execution layer
        -> per-device DeviceOutcome
        -> central ResultSpool
        -> unique per-run JSONL + manifest
        -> output consumer
           -> Excel
           -> REST/API
           -> database
           -> other integrations
```

The spool is output-neutral infrastructure. Workers do not write Excel, API destinations, databases, or a shared spool file directly. One owning spool writer serializes sanitized outcomes. Task-specific data belongs inside an opaque payload while the common execution envelope carries safe execution metadata.

Each run has a unique directory and run ID. Failed/interrupted output generation retains the spool for retry without repeating network collection; successfully consumed spools may be removed according to cleanup policy. Abandoned retained runs require deterministic cleanup.

The initial scale-hardening acceptance target is approximately 1,500 targets at a configured active-device limit of 5. This is an implementation/validation target, not a new hard-coded global concurrency rule.

This spool architecture is approved but not yet implemented; current implementation state remains documented separately in `CURRENT_STATE.md`.

Detailed implementation guidance belongs in `.agents/skills/device-execution/SKILL.md`.

## 5. Shared Transport

All network-device access uses the shared OrbitFlow `DeviceSession` abstraction and `connect_device(...)`.

The transport layer owns session establishment, Teleport connectivity, SSH connectivity, and command execution. Higher-level capabilities should not need to know whether the execution host is Windows or Linux.

### Windows

The validated model uses Teleport local port forwarding:

```text
OrbitFlow / Paramiko
        -> 127.0.0.1:<local-port>
        -> tsh ssh -N -L
        -> Teleport bastion
        -> target device TCP/22
```

Direct Paramiko ProxyCommand behaviour was previously unreliable on Windows, so local forwarding is the approved model.

### Linux / Ubuntu

The validated model uses `tsh proxy ssh`, Teleport identity material, Paramiko, and a `direct-tcpip` channel through the bastion.

## 6. Device Identity and Inventory

OrbitFlow separates target input from observed device identity.

The inventory layer:
- accepts a management IP plus credentials or credential reference;
- discovers platform/device family where supported;
- prefers serial number as the physical-device identity;
- treats management IP as a reachability address, not permanent identity;
- stores relatively stable observed facts only;
- never stores credentials;
- does not treat live interface/VLAN/routing/service state as permanent inventory facts.

Current supported platform identifiers include:
- Cisco IOS
- Cisco IOS-XE
- Cisco IOS-XR
- Huawei VRP
- Ubiquiti EdgeSwitch

Inventory is intended to become the source of device targets and reusable `DeviceContext` for higher-level capabilities.

## 7. Device Capability Model

Reusable device capabilities are the primary building blocks for higher-level OrbitFlow features.

Examples include:
- interface observation;
- VLAN observation;
- MAC-table observation;
- routing state;
- service state;
- configuration planning;
- configuration application;
- verification.

Rules:
- workflows call capabilities rather than embed raw vendor commands;
- capabilities consume resolved device context where appropriate;
- vendor commands/parsing remain vendor-isolated;
- normalized models are preferred over vendor-specific text;
- observe, analyze, plan, apply, verify, and record remain separable.

## 8. Interface Observation

The interface capability is read-only and has been live validated across:
- Cisco IOS
- Cisco IOS-XE
- Cisco IOS-XR
- Huawei VRP
- Ubiquiti EdgeSwitch

Vendor adapters normalize platform-specific output into common records.

## 9. VLAN Observation

The VLAN capability is read-only and reports configured facts.

It observes interface VLAN references plus VLAN, bridge-domain, and equivalent service objects where applicable.

It is not a configuration consistency checker. Compliance/policy logic belongs in a separate analysis layer consuming normalized VLAN state.

The capability is live validated across all five currently supported platform identifiers.

## 9A. Saved-Configuration Audit Resolver Boundary

Read-only configuration audit is a separate analysis concern above observation capabilities.

For VLAN audit, the approved architecture is:

```text
Saved running configuration
        -> vendor parser / VlanService
        -> preserved observations + relationships + source evidence
        -> family-specific AuditResolver
        -> validated audit facts
        -> common compliance engine
        -> report / future remediation planning
```

Responsibilities remain explicit:

- `VlanService` reports configured facts and vendor-specific relationships.
- A family-specific `AuditResolver` validates cross-section relationships and derives the authoritative facts used by audit.
- The common compliance engine evaluates policy only from validated audit facts.
- Reporting does not reinterpret vendor configuration.
- Future remediation/config generation consumes validated findings and planning output; it must not bypass the resolver or infer directly from raw parser text.

Saved configuration is authoritative for configuration-audit semantics. `InterfaceService` may contribute observed identity/state and is correlated by canonical interface name; it does not override saved configuration meaning.

Family-specific resolvers are expected for ME3600X, ASR920, Catalyst 3750X/3850, Huawei VRP, IOS-XR/NCS540, and Ubiquiti EdgeSwitch while producing a shared audit result model.

Detailed business rules belong in `.agents/skills/vlan-configuration-audit/SKILL.md`, not in this architecture document.

## 10. Vendor Isolation

Vendor-specific commands and parsers remain isolated from shared capability logic.

Platform/OS family and device family/capability profile are separate concepts. A platform identifier alone must not be assumed to determine every supported feature or parser path.

## 11. Testing and Validation

Deterministic logic should be unit-tested without requiring live devices.

Tests should cover parser behaviour, command selection, platform detection, identity reconciliation, model normalization, error handling, credential exclusion, and other deterministic logic.

Live-equipment validation supplements automated tests but does not replace them.

Documentation should distinguish clearly between:
- unit tested;
- integration tested;
- live validated.

## 12. Repository Knowledge Model

Canonical continuity files are:
- `AGENTS.md`
- `CURRENT_STATE.md`
- `ARCHITECTURE.md`
- `DECISIONS.md`
- `docs/PROJECT_HANDOFF.md`

Task/vendor implementation knowledge remains under `.agents/skills/`.

Historical implementation detail remains under `docs/devlog/`.

## 13. Development Model

The preferred workflow is:

```text
Requirement
    -> Atlas architecture review
    -> scoped Codex task
    -> implementation
    -> diff review
    -> feature branch
    -> pull request
    -> final review
    -> merge
```

ChatGPT / Atlas is the architecture, orchestration, and review layer. Codex is the implementation engineer. The user remains the final technical authority.

### Implementation / Review Iteration Limit

Each approved implementation plan may undergo a maximum of 15 Codex implementation/revision and Atlas review iterations.

One iteration consists of:

```text
Codex implementation or revision
    -> Atlas review
```

If the fifteenth review still requires changes, automated implementation must stop and the task moves to `codex-replan-required`. Atlas and the user then reassess the architecture or implementation plan. A newly approved plan begins a new implementation cycle with its own 15-iteration limit.

## 14. OrbitFlow-Evo Boundary

OrbitFlow-Evo is the experimentation environment.

Changes made here must not automatically modify the stable OrbitFlow repository.

Promotion to OrbitFlow requires explicit review and approval and may use reimplementation, cherry-pick, or a dedicated migration PR depending on the change.

## 15. Codex Orchestration

OrbitFlow-Evo uses a local Codex CLI worker controlled through GitHub Issues.

The control flow is:

```text
Atlas-approved GitHub issue
 -> codex-task
 -> cross-platform Python controller on the operator workstation
 -> ChatGPT-authenticated Codex CLI
 -> dedicated codex/issue-<number> worktree/branch
 -> tests
 -> push + pull request
 -> codex-review
 -> Atlas approval or codex-revise
 -> explicit human merge gate
```

GitHub remains the coordination and audit layer, while Codex execution occurs locally on the operator workstation. Codex is authenticated with the user's ChatGPT account rather than an API key, so this orchestration does not require `OPENAI_API_KEY`.

The Python controller validates local repository identity and a clean main checkout, prevents duplicate initial execution, isolates tasks in dedicated Git worktrees, updates issue labels/comments, enforces a passing pytest gate before commit/push/PR progression, creates or updates the task PR, and reuses the same task branch for revisions. Its dry-run mode is non-mutating. The same controller implementation is used on Windows and Linux.

The 15-iteration replan gate remains mandatory. Revision 16 is never executed under the same approved plan.

No automatic merge is permitted. Teleport and network-device credentials remain outside Codex prompts and GitHub. Live network validation remains operator-controlled.

Detailed model and setup: `docs/architecture/codex-orchestration.md`.

The local orchestration foundation is implemented but must be considered not end-to-end validated until bootstrap and a controlled test issue complete successfully.

## 16. Parallel Development Direction

Future parallel Codex work should prefer one Git branch and one Git worktree per task.

Conceptually:

```text
GitHub Issue
    -> dedicated branch
    -> dedicated worktree
    -> Codex worker
    -> review
    -> PR
```

Parallel workers must not share one mutable working directory.
