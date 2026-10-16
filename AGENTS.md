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
12. Normalized capability models are authoritative for reusable cross-vendor observation. A routed audit/analysis skill may derive validated audit facts from preserved saved-configuration relationships and evidence, but reporting/workflow layers must not perform ad-hoc vendor reinterpretation.
13. Do not create synthetic interface identities solely from VLAN, L2VPN, VSI, bridge-domain, or other service references.
14. For every meaningful feature, fix or behaviour change, follow `.agents/skills/documentation-management/SKILL.md`: append the monthly devlog and update affected operator, public API, README and function documentation. Update `CURRENT_STATE.md` only when the implementation/validation baseline changes.
15. All multi-device flows use shared device execution; feature modules must not create independent worker pools. Each worker owns one target device and that device's context, session, CLI and intermediate results; reusable capabilities stay single-device and independent of concurrency.
16. Shared persistence, reporting and logging are synchronized or aggregated in their owning layer. Large runs use shared bounded execution-result spooling/consumption instead of retaining unbounded full-run results.
17. Follow the approved target filesystem convention: persistent state under `data/` (e.g. `data/inventory/inventory.json`); generated files under `outputs/` (`reports/<report>/`, `backups/<type>/`, `validation/<type>/`, `logs/<module>/YYYY-MM-DD/`, `runs/<task>/<run-id>/`). Do not claim paths were migrated unless source confirms it.

## 2. Architecture Boundaries

Keep transport, inventory/identity, execution/spooling, normalized capabilities, vendor parsing, analysis, reporting, logging and configuration execution separated. Workflows must reuse existing shared interfaces rather than duplicate them.

## 3. Safety and Roles

- Read-only operations may run normally; configuration changes require explicit user intent.
- Never place production credentials in GitHub Issues, Codex prompts, logs, or repository files.
- **User** — product owner, network architect, final technical and merge authority.
- **Atlas** — architecture, documentation owner, scope, GitHub Issue orchestration and PR review; may make reviewable Markdown-only changes.
- **Codex** — sole implementer of source code, executable scripts and tests; updates affected documentation in the same development work.
- Codex implements source code and tests and updates affected documentation; the controller owns Git/GitHub lifecycle operations.
- Codex and the controller must not auto-merge. Atlas must not merge without explicit user approval.
- Atlas does not change code, scripts or tests. Only Codex implements executable changes.
- Only **one active Codex development Issue** at a time. Never create/materially update a development Issue without explicit owner instruction; never merge without explicit owner approval.

## 4. Context Loading

Keep default context small.

- Always read this `AGENTS.md` first.
- Use the Skill Routing table below to choose the skill(s) directly relevant to the task.
- A skill mentioning, linking, or depending on another skill does **not** mean the referenced skill must be loaded.
- Treat adjacent-skill references as capability ownership guidance, not automatic context dependencies.
- After targeted source inspection, load an additional skill only when the task actually modifies that capability or the implementation must cross that capability boundary.
- Using another capability through its existing public interface is not, by itself, a reason to load that capability's skill.
- Read `CURRENT_STATE.md` only when current implementation/validation status, limitations or active state matters.
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
| Saved-configuration VLAN audit/compliance, family-specific relationship validation, audit findings | `.agents/skills/vlan-configuration-audit/SKILL.md` |
| Interface/VLAN Excel reporting and batch report composition | `.agents/skills/device-reporting/SKILL.md` |
| Runtime/module logging and dependency-log routing | `.agents/skills/runtime-logging/SKILL.md` |
| Access VLAN provisioning | `.agents/skills/access-vlan-provisioning/SKILL.md` |
| Offline Change Plans, configuration validation, engineer-selected templates and approval gates | `.agents/skills/configuration-management/SKILL.md` |
| Cisco IOS / IOS-XE / IOS-XR CLI behaviour | `.agents/skills/cisco-network-cli/SKILL.md` |
| Huawei VRP CLI behaviour | `.agents/skills/huawei-network-cli/SKILL.md` |
| Ubiquiti EdgeSwitch CLI behaviour | `.agents/skills/ubiquiti-network-cli/SKILL.md` |
| Controller, Codex invocation, task/revision lifecycle, PR/review orchestration | `.agents/skills/codex-orchestration/SKILL.md` |
| Documentation updates for every meaningful development/fix; document relocation and references | `.agents/skills/documentation-management/SKILL.md` |

The documentation-management skill applies across meaningful development tasks; read only affected documentation. The orchestration skill is for controller work only, not all Codex tasks.


## 6. Orchestration Boundary

Operational controller: `python scripts/orchestration_v2/controller.py` (add `--dry-run` to preview).

One Issue is one scoped task in an isolated worktree. Controller owns preflight, Codex invocation, tests, Git and PR lifecycle; never auto-merges. Load the orchestration skill only when modifying/troubleshooting that lifecycle.

## 7. Documentation

- Documentation ownership, monthly devlogs, operator-facing scripts/API descriptions and link maintenance: `.agents/skills/documentation-management/SKILL.md`.
- Current documentation navigation: `docs/README.md`. **Existing paths remain unchanged until an approved migration.**
- Atlas reconciles verified implementation and approved decisions in relevant Markdown **before creating or materially updating an authorized development Issue**, using safe, reviewable changes; avoid overlap with active Codex PRs.
- Codex updates affected documentation and the devlog as part of implementation; Atlas checks completeness in PR review.
- No new documentation-enforcement scripts or CI checks without owner request. Never load all historical documents by default.
