# Codex orchestration controller — operator manual

**Entry point:** `scripts/orchestration_v2/controller.py`. Operates the repository GitHub Issue / Codex task lifecycle. **This is a development-orchestration tool**, not a network-configuration apply tool.

## Parameters
- `--repo REPO` (string; default is the controller's `DEFAULT_REPO` value).
- `--dry-run` (flag; false by default): preview without mutating the task lifecycle.
- `--watch` (flag; false by default): continue polling eligible Issues.
- `--poll-seconds N` (positive integer subject to parser validation; default `15` seconds).

## Linux example
```bash
python scripts/orchestration_v2/controller.py --dry-run
python scripts/orchestration_v2/controller.py --watch --poll-seconds 15
```
Windows PowerShell (only where local controller prerequisites are supported):
```powershell
python scripts/orchestration_v2/controller.py --dry-run
```
Expected results depend on eligible labelled GitHub Issues and controller preflight, worktree, Codex and pytest gates. The controller does not auto-merge PRs. Keep **one Codex development Issue active**. For full operator setup, statuses, errors, environment and test gates follow the [orchestration skill](../../.agents/skills/codex-orchestration/SKILL.md) and [architecture](../architecture/codex-orchestration.md). Do not run watch mode without appropriate owner-approved work.

## Shared progress presentation (Issue #144)

See [CLI progress and durable results](cli-progress.md) for interactive and redirected
output, phase-specific counters, saved paths, partial/interrupted/export-failure
semantics and the coverage table (including specialist/lifecycle exemptions).
Device/workflow semantics and existing arguments are unchanged. Deterministic
terminal fixtures are separate from pending owner-operated Linux/Windows validation.
