# AGENTS.md — OrbitFlow-Evo

OrbitFlow-Evo is a multi-vendor network automation platform for ISP operations.

## 1. Permanent Operating Rules

1. Keep changes scoped to the approved task and preserve unrelated working behaviour.
2. Never commit, log, or expose passwords, OTPs, private keys, tokens, production credentials, or raw secret-bearing device output.
3. Runtime network behaviour must be deterministic; do not use an LLM at runtime to invent device configuration.
4. Keep vendor-specific behaviour isolated. Platform/OS family and device family/capability profile are separate concepts.
5. Higher-level workflows must reuse shared transport, inventory, capability, application, and logging interfaces instead of duplicating lower-level logic.
6. Separate observation, analysis, planning, apply, verification, and recording where practical.
7. Configuration changes require explicit user intent and default to non-destructive behaviour.
8. One failed device/input row must not terminate a safe batch unless continuing creates risk.
9. Keep operator console output concise; detailed sanitized diagnostics belong in module-owned logs.
10. Add/update deterministic tests when behaviour changes. State any untested limitation.
11. Do not silently redesign architecture outside task scope.
12. Normalized capability models are authoritative for cross-vendor semantics; higher layers must not reinterpret raw vendor configuration.
13. Do not create synthetic interface identities solely from VLAN, L2VPN, VSI, bridge-domain, or other service references.
14. Append meaningful completed features, behavioural changes, bug fixes, and orchestration changes to the current monthly `docs/devlog/YYYY-MM.md`. Update `CURRENT_STATE.md` only when the implemented/validated capability baseline changes.
15. Multi-device execution must use the shared OrbitFlow device-execution layer; feature modules must not create independent thread pools, worker pools, or equivalent concurrency mechanisms.
16. The concurrency boundary is one target device. One execution worker owns that device's DeviceContext, DeviceSession/transport resources, CLI resources, per-device workflow, and intermediate results.
17. Reusable capabilities remain single-device components and must not depend on whether other devices are executing concurrently.
18. Shared mutable resources such as inventory persistence, report/output generation, and process-wide logging state must be synchronized or aggregated by their owning shared layer rather than mutated unsafely by device workers.
19. Large multi-device workflows must not require retaining an unbounded full-run result set in memory; reusable execution-result persistence and output consumption belong to shared infrastructure rather than feature-specific workers.
20. Use the approved filesystem convention for new or migrated paths: `data/` holds persistent OrbitFlow application state, while `outputs/` holds OrbitFlow-generated operational output. The target layout is `data/inventory/inventory.json`, `outputs/reports/<report>/`, `outputs/backups/<backup-type>/`, `outputs/validation/<validation-type>/`, `outputs/logs/<module>/YYYY-MM-DD/`, and `outputs/runs/<task>/<run-id>/`. Treat this as the target architecture until runtime migration is implemented; do not claim legacy paths have moved before the code changes.

## 2. Architecture Boundaries

Keep transport, target input/device identity, shared device execution, execution-result spooling/consumption, reusable capabilities, vendor CLI/parsers, normalized models, analysis/policy, workflows, reporting, logging, configuration apply/verification, integrations, and tests separated.

Higher-level workflows must not recreate SSH/jumphost logic, vendor parsing, normalized semantics, or logging configuration already owned by shared layers.

## 3. Safety and Roles

- Read-only operations may run normally; configuration changes require explicit user intent.
- Never place production credentials in GitHub Issues, Codex prompts, logs, or repository files.
- **User** — product owner, network architect, final technical and merge authority.
- **Atlas** — architecture, scope, task planning, orchestration coordination, and PR review.
- **Codex** — default implementation engineer for normal development work.
- Codex implements/tests only; the controller owns Git/GitHub lifecycle operations.
- Codex and the controller must not auto-merge. Atlas must not merge without explicit user approval.
- Atlas should not normally implement feature code directly; small documentation-only edits or narrowly scoped orchestration repair may be performed directly when appropriate and remain reviewable.

## 4. Context Loading

Keep default context small.

- Always read this `AGENTS.md` first.
- Use the Skill Routing table below to choose the skill(s) directly relevant to the task.
- A skill mentioning, linking, or depending on another skill does **not** mean the referenced skill must be loaded.
- Treat adjacent-skill references as capability ownership guidance, not automatic context dependencies.
- After targeted source inspection, load an additional skill only when the task actually modifies that capability or the implementation must cross that capability boundary.
- Using another capability through its existing public interface is not, by itself, a reason to load that capability's skill.
- Read `CURRENT_STATE.md` only when the task depends on current implementation/validation status, known limitations, or active state.
- Read architecture documents only when the task changes or depends on that architecture.
- Historical devlogs are write/history targets, not default implementation context; read them only when historical detail is directly relevant.
- Prefer targeted searches/reads. Avoid broad repository ingestion and repeated full diffs/large command output.

## 5. Skill Routing

Use this table to choose the skill(s) directly relevant to the task. Start there; expand to an adjacent skill only when task/source evidence shows that capability must also change.

| Task | Skill |
|---|---|
| Teleport, jumphost, SSH/Paramiko transport | `.agents/skills/jumphost-connectivity/SKILL.md` |
| Device identification, platform detection, identity reconciliation | `.agents/skills/device-inventory/SKILL.md` |
| Multi-device execution, concurrency limits, worker/resource isolation, execution results | `.agents/skills/device-execution/SKILL.md` |
| Excel/list input and credential precedence | `.agents/skills/excel-inventory/SKILL.md` |
| Interface collection/parsing/change tracking | `.agents/skills/interface-collector/SKILL.md` |
| VLAN observation and VLAN state | `.agents/skills/vlan-observation/SKILL.md` |
| Interface/VLAN Excel reporting and batch report composition | `.agents/skills/device-reporting/SKILL.md` |
| Runtime/module logging and dependency-log routing | `.agents/skills/runtime-logging/SKILL.md` |
| Access VLAN provisioning | `.agents/skills/access-vlan-provisioning/SKILL.md` |
| Cisco IOS / IOS-XE / IOS-XR CLI behaviour | `.agents/skills/cisco-network-cli/SKILL.md` |
| Huawei VRP CLI behaviour | `.agents/skills/huawei-network-cli/SKILL.md` |
| Ubiquiti EdgeSwitch CLI behaviour | `.agents/skills/ubiquiti-network-cli/SKILL.md` |
| Controller, Codex invocation, task/revision lifecycle, PR/review orchestration | `.agents/skills/codex-orchestration/SKILL.md` |

The orchestration skill is for orchestration/controller work only. Normal feature tasks do not load it merely because Codex is the implementation worker.

## 6. Orchestration Boundary

Operational controller: `python scripts/orchestration_v2/controller.py` (add `--dry-run` to preview).

One GitHub Issue is one scoped task. Tasks use isolated branches/worktrees. The controller owns preflight, Codex invocation, test gate, commit/push, PR/state transitions, and never auto-merges. Codex changes repository files and tests only.

Load `.agents/skills/codex-orchestration/SKILL.md` only when changing or troubleshooting this orchestration lifecycle.

## 7. Documentation Responsibilities

- `AGENTS.md` — permanent global rules and routing/context policy.
- `CURRENT_STATE.md` — concise implemented/validated state.
- `.agents/skills/*/SKILL.md` — task-specific implementation knowledge.
- `docs/architecture/` — durable architecture/cross-feature decisions.
- `docs/devlog/YYYY-MM.md` — completed work/troubleshooting history; append without reading history unless needed.
- `DEVLOG.md` — short index.
- `ROADMAP.md` — future work.
- `README.md` — operator/developer setup and usage.

Do not duplicate long historical or task-specific detail into `AGENTS.md` or `CURRENT_STATE.md`.
