# OrbitFlow-Evo Architecture Decisions

This document records important technical and development decisions so future ChatGPT, Codex, and developer sessions understand not only what was chosen, but why.

## DEC-001 — OrbitFlow-Evo is an isolated sandbox

**Decision:** Maintain OrbitFlow-Evo as a separate repository from stable OrbitFlow.

**Reason:** Experimental work must not risk the stable repository.

**Consequence:** Promotion to OrbitFlow requires explicit review and approval.

## DEC-002 — Repository documentation is the source of truth

**Decision:** Important architecture, development state, and decisions must be stored in the repository.

**Canonical files:** `AGENTS.md`, `CURRENT_STATE.md`, `ARCHITECTURE.md`, `DECISIONS.md`, and `docs/PROJECT_HANDOFF.md`.

**Reason:** Chat history and AI memory are useful context but are not sufficient as the only project record.

## DEC-003 — Atlas owns architecture and review

**Decision:** ChatGPT / Atlas acts as solution architect, development manager, Codex task planner, and technical/PR reviewer. Codex acts primarily as the implementation engineer.

**Reason:** Separating architecture/review from implementation reduces uncontrolled design drift.

## DEC-004 — Codex prompts should remain concise

**Decision:** Put persistent architecture and rules in repository documentation; keep individual Codex prompts short and scoped.

**Reason:** This reduces prompt size and keeps implementation tasks focused.

## DEC-005 — Use shared DeviceSession transport

**Decision:** All higher-level capabilities use the shared `DeviceSession` / `connect_device(...)` transport layer.

**Reason:** SSH and Teleport behaviour should remain centralized and reusable.

## DEC-006 — Use Teleport local forwarding on Windows

**Decision:** Windows uses the validated `tsh ssh -N -L` local-forwarding pattern with Paramiko connecting to the local forwarded port.

**Reason:** Direct Paramiko ProxyCommand behaviour was unreliable on Windows.

## DEC-007 — Keep vendor implementations isolated

**Decision:** Vendor-specific commands and parsing remain outside shared capability logic.

**Reason:** OrbitFlow is multi-vendor and must remain extensible.

## DEC-008 — Parsers report observed facts

**Decision:** Vendor parsers report configuration or operational facts actually observed in device output.

**Reason:** Normalized data should remain deterministic and auditable.

## DEC-009 — Interface and VLAN capabilities remain read-only

**Decision:** Current interface and VLAN capabilities observe device state and do not modify configuration.

**Reason:** Observation and normalization are being established before broader configuration automation.

## DEC-010 — Inventory becomes the device-context source

**Decision:** The inventory/identification layer is intended to provide reusable target/device context to other capabilities.

**Reason:** Capabilities should not duplicate device lists or platform-detection logic.

## DEC-011 — Credentials remain outside source and inventory

**Decision:** Credentials must not be committed to source code or stored in inventory snapshots.

**Reason:** Security and separation of concerns.

## DEC-012 — Test deterministic logic

**Decision:** Parser, normalization, identification, reconciliation, validation, and similar deterministic logic require automated tests.

**Reason:** Live-device testing is valuable integration validation but is not a regression-test substitute.

## DEC-013 — Prefer feature branches and PR review

**Decision:** Meaningful development uses feature branches and pull requests.

**Reason:** This provides isolation, review history, rollback capability, and auditability.

## DEC-014 — GitHub Issues can act as a Codex task queue

**Decision:** The orchestration pattern may use GitHub labels such as `codex-task`, `codex-running`, `codex-review`, `codex-approved`, `codex-pr`, and `codex-failed`.

**Reason:** GitHub provides a persistent coordination layer accessible to ChatGPT and local automation.

## DEC-015 — Merging requires an explicit safety gate

**Decision:** Codex must not independently merge changes into `main`.

**Reason:** Human control remains at the final promotion boundary.

## DEC-016 — Parallel Codex development should use worktrees

**Decision:** Future parallel execution should prefer one branch and one Git worktree per task.

**Reason:** Multiple workers must not modify the same local working directory.

## DEC-017 — Promotion from Evo is controlled

**Decision:** The preferred lifecycle is:

```text
OrbitFlow-Evo experiment
 -> implementation
 -> automated testing
 -> live validation where appropriate
 -> architecture review
 -> explicit approval
 -> controlled promotion into OrbitFlow
```

**Reason:** OrbitFlow-Evo exists specifically to isolate experimentation from the stable codebase.
