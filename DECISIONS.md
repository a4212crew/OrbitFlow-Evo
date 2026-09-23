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


## DEC-018 — Limit Codex implementation/review cycles to 15 iterations

**Decision:** A Codex task may undergo at most 15 implementation/revision and Atlas review iterations under the same approved implementation plan.

One iteration is one Codex implementation or revision followed by one Atlas review.

If the fifteenth review still requires changes, automated implementation stops and the task enters `codex-replan-required`. Atlas and the user must revisit and approve the architecture or implementation plan before another implementation cycle begins. A newly approved plan starts a fresh iteration counter.

**Reason:** Repeated patching beyond this point is more likely to indicate a flawed or incomplete implementation plan than a simple implementation defect. Stopping and replanning limits design drift and unproductive automated retries.

**Consequence:** Codex orchestration must track the current iteration deterministically and must not automatically schedule iteration 16 under the same plan.


## DEC-019 — Use local ChatGPT-authenticated Codex CLI orchestration in OrbitFlow-Evo

**Decision:** Use GitHub Issues as the orchestration/control plane while running Codex locally on the operator workstation through the Codex CLI authenticated with the user's ChatGPT account. Each task uses an isolated `codex/issue-<number>` branch and dedicated Git worktree.

**Reason:** This preserves the proven Codex-Orchestrator-Lab model, uses GitHub for persistent coordination and review state, supports parallel isolated tasks, and avoids requiring OpenAI API-key billing for the implementation worker.

**Security boundary:** Codex may modify and test repository code but must not receive Teleport identities, device credentials, OTPs, or production network access. Live-device validation remains operator-controlled and local.

**Consequence:** The local controller owns Git operations and GitHub state transitions. Codex itself must not commit, push, create PRs, or merge. No orchestration path may auto-merge to `main`. The 15-iteration replan gate from DEC-018 applies to revision cycles.

## DEC-020 — Use Python for local Codex orchestration

**Decision:** OrbitFlow-Evo local Codex orchestration uses Python entry points (`scripts/orchestration/bootstrap.py` and `scripts/orchestration/controller.py`) rather than PowerShell-specific controller scripts.

**Reason:** The orchestration control plane must run from the same codebase on both Windows and Linux. Python provides platform-aware filesystem/process handling, deterministic pytest coverage, and avoids maintaining separate shell implementations.

**Operational rules:** Shared orchestration code and tests must not hard-code operating-system path separators. Dry-run must be non-mutating. The deterministic pytest suite is a hard gate: failed tests must stop the controller before commit, push, or pull-request creation/update.

**Consequence:** PowerShell orchestration entry points are retired. GitHub Issues, local ChatGPT-authenticated Codex CLI execution, dedicated task worktrees/branches, the 15-iteration replan gate, and explicit human merge approval remain unchanged.
