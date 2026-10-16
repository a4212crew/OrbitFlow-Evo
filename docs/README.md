# OrbitFlow-Evo Documentation Index

> **Authority and migration status:** This index reflects the Phase 3 proposed branch layout. Relocated paths do not become available on `main` until the PR merges; source/test-dependent legacy paths remain preserved.

## Start here

| Need | Source | Status |
|---|---|---|
| Codex global safety rules and skill routing | [AGENTS.md](../AGENTS.md) | Current instruction |
| Atlas issue workflow | [Issue creation rules](../.agents/ISSUE_CREATION_RULES.md) | Current instruction |
| Writing / updating documentation | [Documentation management skill](../.agents/skills/documentation-management/SKILL.md) | Current instruction |
| Current implemented/validated capabilities | [CURRENT_STATE.md](CURRENT_STATE.md) | Current-state reference; needs editorial reconciliation |
| Project usage and setup | [README.md](../README.md) | Operator entry point; some introductory wording outdated |
| Architecture overview | [architecture overview](architecture/README.md) | Architecture; iteration governance needs reconciliation |
| Numbered decisions | [architecture decisions](architecture/DECISIONS.md) | Decision history; later decisions override earlier rules |
| Future planning | [ROADMAP.md](ROADMAP.md) | Future plans; configuration v2 planning status reconciled |
| Development history index | [devlog/README.md](devlog/README.md) | Monthly index including September and October |
| September devlog | [2026-09.md](devlog/2026-09.md) | Historical |
| October devlog | [2026-10.md](devlog/2026-10.md) | Historical |

## User manuals for executable scripts

- [Canonical executable-script user manual index](user_manual/README.md) — guides maintained by both Atlas and Codex, with verified inputs, scenarios, commands and expected outputs. Existing guides remain at their current paths until an approved migration.

## Operations / executable features

- [Inventory, interface/VLAN reporting and configuration backup usage](../README.md)
- [Bulk configuration planning v2](user_manual/bulk-configuration-planning.md) — operator workflow, input generation, plan preparation and validation.
- [Configuration v2 template reference](operations/configuration-template-reference.md) — template scenarios and expected results. **Referenced by current source and tests; preserve this path.**
- [Methodology patterns 8–12](operations/methodology-patterns-8-12.md) — specialized audit reference.
- [EdgeSwitch interface-status observations](operations/edgeswitch-interface-status-observations-2026-10-08.md) — dated diagnostic/reference evidence.

This is a **navigation index**, not a claim that every executable script and public API already has a complete dedicated guide. Document gaps are to be reconciled in the approved operations-documentation phase. Never fabricate commands or outputs to fill those gaps.

## Architecture and decisions

- [Device capability / OSS model](architecture/device-capability-oss-model.md)
- [Execution result spool](architecture/result-spool.md)
- [Codex orchestration architecture](architecture/codex-orchestration.md) — check current source for governing iteration limit.
- [Configuration architecture index](architecture/configuration/README.md)
- [Offline Change Plans v1](architecture/configuration/offline-plans.md)
- [Guided bulk planning / 22-template design](architecture/configuration/guided-bulk-planning.md) — **historical implementation status is stale**; use current operator guide and code for present capability.
- [Approved Catalyst template requirements](architecture/configuration/approved-catalyst-templates.md)
- [Approved ME3600X/ASR920/EdgeSwitch template requirements](architecture/configuration/approved-me3600x-asr920-edgeswitch-templates.md)
- [Interface methodology design and review](architecture/configuration/interface-methodology-review.md)
- [Configuration removal: proposal only](architecture/configuration/configuration-removal.md)
- [Configuration management proposal](architecture/configuration/configuration-management.md)
- [Change Plan specification proposal](architecture/configuration/change-plan-specification.md)
- [Configuration templates proposal](architecture/configuration/configuration-templates.md)
- [Execution workflow proposal](architecture/configuration/execution-workflow.md)
- [Platform adapters proposal](architecture/configuration/platform-adapters.md)
- [Drift detection proposal](architecture/configuration/drift-detection.md)

## Controller and historical references

- [Controller task preamble](../scripts/orchestration_v2/task-preamble.md) — **direct runtime dependency**, must remain at its current path.
- [Project handoff](PROJECT_HANDOFF.md) — historical and partly obsolete; currently referenced from root architecture/decisions, **not canonical for current workflow**.
- [Orchestration watch validation](orchestration-watch-validation.md) — one-time historical validation, deletion candidate only.
- [Orchestration v2 end-to-end validation](orchestration-v2-e2e-validation.md) — one-time historical validation, deletion candidate only.

## How to interpret documents

**Implemented:** confirm against actual `main` source, tests, current operator guide and observed validation; old documents may be stale.

**Approved design:** describes owner-approved target requirements; not proof functionality is implemented.

**Proposed:** future work, not implementation authorization.

**Historical:** dated history/evidence, not active instructions.

**Superseded:** keep provenance but defer to verified newer implementation/approved decision.

## Editing contract

For user-executable scripts, Atlas and Codex maintain canonical guides under `docs/user_manual/`. For any meaningful source change or fix, Codex must follow [documentation-management/SKILL.md](../.agents/skills/documentation-management/SKILL.md), append a monthly devlog entry and update affected README, function/API/CLI guidance and indexes as needed. Atlas may correct and reorganize Markdown directly through reviewable documentation-only changes, without creating a Codex development Issue. **Neither Atlas nor Codex may merge a PR without the owner's explicit approval.**

This Phase 2 index does **not** move, rename or delete any existing Markdown document.
