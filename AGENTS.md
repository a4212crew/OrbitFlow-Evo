# AGENTS.md — OrbitFlow-Evo

OrbitFlow-Evo is a multi-vendor network automation platform for ISP operations. It is the active development repository.

## 1. Permanent Operating Rules

1. Keep changes scoped to the approved task and preserve unrelated working behaviour.
2. Never commit, log, or expose passwords, OTPs, private keys, tokens, or production credentials.
3. Runtime network behaviour must be deterministic. Do not use an LLM at runtime to invent device configuration.
4. Vendor-specific behaviour must remain isolated. Platform/OS family and device family/capability profile are separate concepts.
5. Higher-level workflows must use shared transport, inventory, capability, and application interfaces instead of duplicating lower-level logic.
6. Separate observation, analysis, planning, apply, verification, and recording where practical.
7. Configuration-changing workflows must be explicitly requested and default to non-destructive behaviour.
8. One failed device or input row should not terminate a safe batch unless continuing would create risk.
9. Runtime modules must use the shared OrbitFlow logging foundation rather than creating independent logging configuration. Keep operator console output concise, write detailed diagnostics to module-owned logs, and never log secrets or raw credential material.
10. Add or update deterministic tests when behaviour changes. A task is not complete until relevant acceptance criteria pass or an untested limitation is stated.
11. Do not silently redesign architecture outside task scope.

## 2. Project Architecture Boundaries

OrbitFlow-Evo is designed as a reusable network-equipment capability platform and future OSS/BSS capability layer.

Keep these concerns separate:
- transport and jumphost connectivity;
- target input and device identity;
- reusable device capabilities;
- vendor-specific CLI commands/parsers;
- normalized models;
- analysis and policy logic;
- workflows/orchestration;
- reporting;
- runtime logging/diagnostics;
- configuration planning/apply/verification;
- integration/API layers;
- tests.

Higher-level workflows must not recreate SSH/jumphost logic, vendor-specific parsing, or logging configuration already provided by shared layers.

## 3. Safety and Merge Boundaries

- Read-only operations may run normally.
- Configuration changes require explicit user intent.
- Never place production credentials in GitHub Issues, Codex prompts, logs, or repository files.
- Codex must not merge to `main`.
- The controller must not auto-merge.
- Atlas must not merge without explicit user approval.
- The user remains final technical and merge authority.

## 4. Development Roles

- **User** — product owner, network architect, final technical/merge authority.
- **Atlas** — architecture, scope, task planning, orchestration coordination, and PR review.
- **Codex** — default implementation engineer for normal development work.

Atlas should not normally implement feature code directly. Small documentation-only edits or narrowly scoped orchestration repair may be performed directly when appropriate and remain reviewable.

## 5. Context-Efficiency Rules

Keep default task context small.

- Read this `AGENTS.md` first.
- Read only the task-relevant skill files listed below.
- Read `CURRENT_STATE.md` only when the task depends on current implementation status, architecture baseline, supported behaviour, known limitations, or active development state.
- Read files under `docs/devlog/` only when historical implementation detail is directly relevant.
- Read architecture documents only when the task changes or depends on that architecture.
- Prefer targeted search and targeted file reads before opening large documents.
- Do not broadly ingest repository documentation for simple, documentation-only, test-only, or narrowly scoped fixes.
- Avoid repeatedly printing full diffs or large command output; inspect targeted sections and one final diff where practical.

## 6. Skill Routing

Read only the skill directly relevant to the task, plus any skill it explicitly references.

| Task | Skill |
|---|---|
| Teleport, jumphost, SSH/Paramiko transport | `.agents/skills/jumphost-connectivity/SKILL.md` |
| Device identification, platform detection, identity reconciliation | `.agents/skills/device-inventory/SKILL.md` |
| Excel/list input and credential precedence | `.agents/skills/excel-inventory/SKILL.md` |
| Interface collection/parsing/change tracking | `.agents/skills/interface-collector/SKILL.md` |
| VLAN observation and VLAN state | `.agents/skills/vlan-observation/SKILL.md` |
| Interface/VLAN Excel reporting and batch report composition | `.agents/skills/device-reporting/SKILL.md` |
| Runtime/module logging, sanitization, file layout, and dependency-log routing | `.agents/skills/runtime-logging/SKILL.md` |
| Access VLAN provisioning | `.agents/skills/access-vlan-provisioning/SKILL.md` |
| Cisco IOS / IOS-XE / IOS-XR CLI behaviour | `.agents/skills/cisco-network-cli/SKILL.md` |
| Huawei VRP CLI behaviour | `.agents/skills/huawei-network-cli/SKILL.md` |
| Ubiquiti EdgeSwitch CLI behaviour | `.agents/skills/ubiquiti-network-cli/SKILL.md` |
| Atlas/Codex orchestration and review lifecycle | `.agents/skills/codex-orchestration/SKILL.md` |

## 7. Orchestration Rules

Operational controller:

```bash
python scripts/orchestration_v2/controller.py
```

Dry run:

```bash
python scripts/orchestration_v2/controller.py --dry-run
```

Permanent orchestration boundaries:
- one GitHub Issue = one scoped task;
- one task uses a dedicated `codex/issue-<number>` branch and worktree;
- controller owns preflight, Codex invocation, deterministic test gate, commit/push, PR creation/update, and task-state transitions;
- Codex implements/tests only;
- no `OPENAI_API_KEY` dependency or silent API-billing fallback;
- revisions reuse the same branch/worktree/PR;
- maximum 10 implementation/review iterations per approved plan;
- optional safe watch mode;
- no auto-merge.

For detailed lifecycle behaviour, load `.agents/skills/codex-orchestration/SKILL.md`.

## 8. Documentation Responsibilities

- `AGENTS.md` — permanent global rules, skill routing, and context-loading policy.
- `CURRENT_STATE.md` — concise implemented/validated state; read only when relevant.
- `.agents/skills/*/SKILL.md` — task-specific implementation knowledge.
- `docs/architecture/` — durable architectural models and cross-feature design decisions.
- `docs/devlog/YYYY-MM.md` — historical completed work and troubleshooting record; not default task context.
- `DEVLOG.md` — short index only.
- `ROADMAP.md` — future work.
- `README.md` — operator/developer setup and usage.

Do not duplicate long historical or task-specific detail into `AGENTS.md` or `CURRENT_STATE.md`.
