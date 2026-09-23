# Codex Orchestration for OrbitFlow-Evo

## Purpose

OrbitFlow-Evo uses ChatGPT / Atlas as the architecture, planning, and review layer and Codex as the implementation engineer.

GitHub Issues provide the persistent control plane. Codex execution happens locally on the operator workstation through the Codex CLI authenticated with the user's ChatGPT account.

This design is derived from the proven Codex-Orchestrator-Lab model and does not require an OpenAI API key.

## Control Flow

```text
User requirement
  -> Atlas architecture review
  -> GitHub issue
  -> codex-task
  -> local controller.ps1
  -> local ChatGPT-authenticated codex exec
  -> dedicated Git worktree + codex/issue-<number> branch
  -> deterministic tests
  -> controller commits/pushes
  -> controller creates/updates PR
  -> codex-review
  -> Atlas review
       -> pass: codex-approved
       -> changes: Atlas issue comment + codex-revise
  -> explicit human merge
```

Codex must never merge its own work.

## Components

### bootstrap.ps1

`scripts/orchestration/bootstrap.ps1` validates:

- GitHub CLI is authenticated;
- Codex CLI is installed;
- the expected GitHub repository is reachable;
- orchestration labels exist.

It does not configure or require `OPENAI_API_KEY`.

Codex must be authenticated separately with the user's ChatGPT account. If needed:

```powershell
codex login
```

### controller.ps1

`scripts/orchestration/controller.ps1` is the local worker/controller.

It:

1. checks for `codex-revise` tasks first, then `codex-task`;
2. validates repository identity;
3. rejects a dirty main checkout;
4. creates or reuses a dedicated task worktree;
5. invokes local `codex exec`;
6. runs the deterministic pytest suite;
7. commits and pushes the task branch;
8. creates the initial PR or updates the existing PR branch;
9. posts the iteration result to the GitHub issue;
10. returns the issue to `codex-review`.

Run once:

```powershell
.\scripts\orchestration\controller.ps1
```

Run continuously:

```powershell
.\scripts\orchestration\controller.ps1 -Watch
```

Dry-run the next queued task without invoking Codex:

```powershell
.\scripts\orchestration\controller.ps1 -DryRun
```

## Worktree and Branch Isolation

Each issue uses:

```text
branch:   codex/issue-<number>
worktree: ../OrbitFlow-Evo-worktrees/issue-<number>
```

The main checkout remains the control checkout and must be clean.

Separate issues therefore execute in separate Git worktrees. This allows parallel tasks without multiple Codex workers modifying the same directory.

The current controller processes one task at a time per controller process. Multiple controller processes should not be pointed at the same issue queue unless additional worker-claim locking is introduced.

## GitHub Labels

- `codex-task` — approved initial implementation is waiting.
- `codex-running` — local Codex/controller execution is in progress.
- `codex-review` — implementation is waiting for Atlas review.
- `codex-revise` — Atlas requested another Codex revision.
- `codex-approved` — Atlas review passed.
- `codex-pr` — the task has an implementation PR.
- `codex-failed` — local orchestration failed and needs inspection.
- `codex-replan-required` — iteration 15 was exhausted under the current plan.

The bootstrap script creates or updates these labels.

## Atlas Review Contract

When Atlas requires corrections, Atlas posts an issue comment containing:

```text
<!-- atlas-review -->
```

followed by concise required corrections.

Atlas then applies `codex-revise`.

The controller passes the original issue plus the latest owner-authored marked Atlas review to Codex. The same task branch and PR are reused.

Atlas should keep correction prompts concise because persistent architecture already lives in the repository.

## 15-Iteration Replan Gate

One successful Codex implementation/revision followed by one Atlas review is one iteration.

Successful iterations are recorded in issue comments with:

```text
<!-- orbitflow-codex-iteration:N -->
```

A plan may use at most 15 iterations.

If another revision is requested after iteration 15, the controller does not run Codex. It applies `codex-replan-required` and stops automated implementation.

Atlas and the user must then revisit and approve the implementation plan. A new approved plan begins a fresh implementation cycle.

## Authentication and Billing Boundary

The implementation worker uses the locally installed Codex CLI authenticated with the user's ChatGPT account.

This orchestration does not use:

- `OPENAI_API_KEY`;
- the OpenAI API as the implementation transport;
- GitHub-hosted `openai/codex-action`.

Therefore the orchestration is intended to consume the Codex usage available through the authenticated ChatGPT plan, subject to the plan's current Codex limits, rather than API-key billing.

GitHub access uses the locally authenticated `gh` CLI.

## Security Boundaries

- Codex receives repository/task context only.
- Device passwords, OTPs, Teleport private keys/certificates, and production secrets must not be placed in GitHub issues or Codex prompts.
- The controller may run repository tests but does not perform live network validation.
- Live-device validation remains an operator-controlled activity using the approved OrbitFlow transport.
- Stable OrbitFlow is outside this automation boundary.
- No controller path auto-merges to `main`.
- The user remains the final merge authority.

## Failure Handling

If the local controller fails, it applies `codex-failed` and posts the failure reason to the issue where possible.

A failed run does not count as a completed implementation/review iteration unless an iteration marker was successfully posted for Atlas review.

Before retrying, inspect the task worktree and GitHub issue state. The controller intentionally refuses duplicate initial branches/worktrees rather than silently overwriting unreviewed local changes.

## Bootstrap and First Validation

From an up-to-date, clean OrbitFlow-Evo checkout:

```powershell
gh auth status
codex --version
codex login
.\scripts\orchestration\bootstrap.ps1
```

Then start the controller:

```powershell
.\scripts\orchestration\controller.ps1 -Watch
```

First end-to-end validation:

1. Atlas creates a trivial non-network GitHub issue.
2. Atlas/user approves the implementation plan.
3. Atlas applies `codex-task`.
4. The local controller claims the task and runs Codex.
5. Confirm a dedicated worktree, branch, PR, test result, and `codex-review` state are created.
6. Atlas reviews the PR.
7. Atlas posts one marked correction comment and applies `codex-revise`.
8. Confirm the controller reuses the same branch/PR and returns the issue to `codex-review`.
9. Merge only after explicit user approval.

The orchestration foundation is not considered end-to-end validated until this controlled test succeeds.
