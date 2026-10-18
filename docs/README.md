# OrbitFlow-Evo Documentation Index

- [Confirmed Catalyst/EdgeSwitch execution](user_manual/configuration-execution.md): CLI, recovery and owner lab-validated C3750X/EdgeSwitch ordered template stages; C3850 and Linux validation remain pending.
- [Execution and standalone APIs](operations/configuration-execution-api.md): prepare/confirm, collectors/parsers, verification and save.

 > **Current layout:** The documentation migration is present on `main`; canonical executable guides live under `docs/user_manual/`. Legacy reference paths remain where source/tests depend on them.

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

## Interactive operations console

- [Interactive Operations Console architecture](architecture/interactive-operations-console.md) — owner-approved menus, environment profile, concurrency, migration and safety requirements implemented by Issue #123.
- [Console operator guide](user_manual/interactive-operations-console.md) — implemented CLI, profile schema and Windows/Linux validation commands.
- [Interactive console skill](../.agents/skills/interactive-operations-console/SKILL.md) — mandatory routing for eligible new user-executable workflows.

## User manuals for executable scripts

- [Canonical executable-script user manual index](user_manual/README.md) — guides maintained by both Atlas and Codex, with verified inputs, scenarios, commands and expected outputs. Legacy operations references remain at their existing paths where source/test compatibility requires them.

## Operations / executable features

- [Inventory, interface/VLAN reporting and configuration backup usage](../README.md)
- [Configuration template workbook engineer guide](user_manual/configuration-template-guide.md) — worked instructions and all 22 template inputs, expected proposals and review cases.
- [Bulk configuration planning v2](user_manual/bulk-configuration-planning.md) — **current** guide: script purpose, complete CLI options, all 22 template schemas, proposed CLI examples and expected outputs.
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
- [Approved initial device execution](architecture/configuration/approved-device-execution.md) — implemented Catalyst/EdgeSwitch execution and ordered template-stage revision; owner C3750X/EdgeSwitch lab execution validated, C3850/Linux coverage pending.
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

The documentation structure was merged in PR #110. This index tracks current canonical and retained reference paths.

- [Issue #117 protected skill correction handoff](operations/issue-117-skill-corrections.md): historical filesystem denial; scoped skill corrections completed by Atlas on PR #118.

Issue #117 [revision handoff history](operations/issue-117-revision-handoff.md): scoped skill corrections completed by Atlas after iteration 4; owner validation remains pending.

## MAC Address Lookup (Issue #130)

- [Operator guide](user_manual/mac-address-lookup.md)
- [Supported Python API](operations/mac-address-lookup-api.md)
- [Architecture contract](architecture/mac-address-lookup.md)
- [Skill reconciliation record](operations/mac-lookup-atlas-skill-handoff.md) (applied on this PR branch)
- Backend guidance: [MAC observation](../.agents/skills/mac-observation/SKILL.md) and [bridge-domain observation](../.agents/skills/bridge-domain-observation/SKILL.md)
