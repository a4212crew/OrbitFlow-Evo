# OrbitFlow-Evo Project Handoff

## 1. Project Identity

Project: OrbitFlow-Evo

Repository:
a4212crew/OrbitFlow-Evo

OrbitFlow-Evo is the experimental evolution sandbox for the stable OrbitFlow project.

Its purpose is to:
- Test new architecture and capabilities safely.
- Prototype automation and orchestration approaches.
- Perform R&D without risking the stable OrbitFlow repository.
- Validate features before deciding whether they should be promoted into OrbitFlow.

The stable OrbitFlow repository must not be modified unless explicitly instructed.

---

## 2. Development Roles

### User
Acts as:
- Product owner
- Network architect
- Technical decision maker
- Final approval authority

### ChatGPT / Atlas
Acts as:
- Solution architect
- Development manager
- Technical reviewer
- Codex task planner
- Pull request reviewer

Atlas should:
- Understand requirements before implementation.
- Keep Codex prompts concise and scoped.
- Review Codex changes before approval.
- Preserve architecture consistency.
- Avoid unnecessary rewrites.
- Prefer incremental development.

### Codex
Acts as:
- Implementation engineer

Codex should:
- Follow AGENTS.md.
- Implement scoped development tasks.
- Add or update tests where appropriate.
- Avoid modifying unrelated files.
- Never make architectural decisions independently when requirements are unclear.
- Avoid commit, push, or merge unless explicitly instructed by the orchestration workflow.

---

## 3. Development Philosophy

OrbitFlow development should prioritize:

1. Safety
2. Small scoped changes
3. Vendor isolation
4. Reusable shared capabilities
5. Deterministic parsing and logic
6. Testability
7. Review before merge
8. Repository documentation as the source of truth

Chat history must not be treated as the only source of project knowledge.

Important architecture, decisions, and project state should be documented inside the repository.

---

## 4. Target Environment

OrbitFlow is intended to support approximately 1,500 network devices.

Primary platforms include:

- Cisco IOS
- Cisco IOS-XE
- Cisco IOS-XR
- Huawei VRP
- Ubiquiti EdgeSwitch
- Additional platforms may be introduced later

Primary development environment:

- Windows workstation
- Python virtual environment
- Git
- GitHub
- OpenAI Codex CLI
- ChatGPT used as the architecture/review layer

---

## 5. Transport Architecture

OrbitFlow uses a shared DeviceSession abstraction.

The currently validated Windows Teleport access method uses:

Teleport proxy:
teleport.lynhamnetworks.au:443

Cluster:
lynhamcluster

Typical bastion:
bastion-lyn-dc1-vic

Transport pattern:

1. Start a Teleport local tunnel using `tsh ssh -N -L`.
2. Bind a local TCP port such as 2222 or 2223.
3. Forward the connection through the bastion to the network device TCP/22.
4. Paramiko connects to `127.0.0.1:<local-port>`.
5. Network device credentials are used for the final SSH session.

Direct Paramiko ProxyCommand was previously unreliable on Windows.

The Teleport tunnel approach has been live validated.

---

## 6. Existing OrbitFlow Capabilities

### Interface Observation

The interface capability has been implemented and live validated across:

- Cisco IOS
- Cisco IOS-XE
- Cisco IOS-XR
- Huawei VRP
- Ubiquiti EdgeSwitch

The vendor parser should report observed device facts rather than inferred configuration.

### VLAN Observation

The VLAN observation capability is read-only.

Its purpose is to observe:

- Configured VLANs
- Interface VLAN configuration
- VLAN database or service objects where applicable

It is not currently intended to act as a configuration consistency checker.

Supported platforms include:

- Cisco IOS
- Cisco IOS-XE
- Cisco IOS-XR
- Huawei VRP
- Ubiquiti EdgeSwitch

---

## 7. Inventory Direction

Inventory is intended to become the source of device targets for OrbitFlow capabilities.

Expected inventory data includes concepts such as:

- Device name
- Management IP
- Platform
- Site or location
- Credentials reference
- Other metadata required by capabilities

Credentials must not be stored directly in source code.

---

## 8. Development Workflow

Preferred workflow:

Requirement
→ Atlas reviews requirement
→ Atlas creates scoped Codex task
→ Codex implements change
→ Atlas reviews diff
→ Feature branch
→ Pull request
→ Final review
→ Merge

Development should normally use feature branches and pull requests.

Direct uncontrolled changes to main should be avoided.

---

## 9. Codex Orchestration R&D

A separate repository was used to validate ChatGPT-to-Codex orchestration:

Codex-Orchestrator-Lab

The following workflow was successfully proven:

codex-task
→ local controller runs Codex
→ Codex modifies repository
→ result and git diff posted to GitHub
→ codex-review
→ Atlas review
→ codex-approved
→ feature branch
→ commit
→ push
→ pull request
→ codex-pr
→ manual merge approval
→ main updated

Scripts validated in the lab included:

- controller.ps1
- finalize.ps1
- merge-approved.ps1

This orchestration model may later be adapted for OrbitFlow-Evo after appropriate safety hardening.

---

## 10. Orchestration Safety Requirements

Before introducing automated Codex orchestration into OrbitFlow-Evo, consider:

- Reject unexpected dirty working trees.
- Use one branch per task.
- Prefer one Git worktree per parallel task.
- Prevent duplicate issue execution.
- Introduce task states such as:
  - codex-task
  - codex-running
  - codex-review
  - codex-approved
  - codex-pr
  - codex-failed
  - codex-replan-required
- Capture task-specific diffs only.
- Validate repository identity before execution.
- Never automatically merge directly into main without an explicit approval gate.
- Support clean failure recovery.
- Keep Codex prompts concise.
- Track implementation/review iterations explicitly. One iteration is one Codex implementation or revision followed by Atlas review.
- Allow a maximum of 15 iterations under one approved implementation plan.
- If iteration 15 still fails review, stop automated implementation, move the task to `codex-replan-required`, and require Atlas plus the user to revisit the implementation plan before starting a new cycle.

---

## 11. Parallel Development Direction

Future orchestration may support multiple Codex tasks simultaneously.

The preferred architecture is likely:

GitHub Issue
→ dedicated Git branch
→ dedicated Git worktree
→ Codex worker
→ PR

Separate worktrees should prevent parallel tasks from modifying the same local working directory.

Conflict detection and PR review should remain mandatory.

---

## 12. Repository Knowledge Model

The repository should remain the authoritative project knowledge source.

Important files:

- AGENTS.md
- CURRENT_STATE.md
- ARCHITECTURE.md
- DECISIONS.md
- docs/PROJECT_HANDOFF.md

Future ChatGPT or Codex sessions should read these files before significant development work.

---

## 13. Working Style

The user prefers:

- Step-by-step development.
- Meaningful development chunks rather than excessively small steps.
- Short and precise Codex prompts.
- Architecture review before implementation.
- Reviewing one stage before progressing to the next.
- Practical live validation where appropriate.
- Clear explanation of how each module will actually be used operationally.

Do not start major new implementation work until the current development step has been reviewed.

---

## 14. Promotion Model

OrbitFlow-Evo is experimental.

Features should not automatically flow into OrbitFlow.

Preferred promotion lifecycle:

OrbitFlow-Evo experiment
→ implementation
→ testing
→ live validation
→ architecture review
→ explicit approval
→ controlled promotion into OrbitFlow

Promotion may use:
- Reimplementation
- Cherry-pick
- Dedicated migration PR

depending on the nature of the change.

---

## 15. Starting a New ChatGPT Project

When starting a new ChatGPT conversation for OrbitFlow-Evo, instruct ChatGPT to read:

1. AGENTS.md
2. CURRENT_STATE.md
3. ARCHITECTURE.md
4. DECISIONS.md
5. docs/PROJECT_HANDOFF.md

ChatGPT should then continue acting as Atlas: solution architect, development manager, and reviewer, while Codex acts as the implementation engineer.