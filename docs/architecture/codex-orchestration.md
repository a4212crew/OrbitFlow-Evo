# Codex Orchestration for OrbitFlow-Evo

## Purpose

OrbitFlow-Evo uses ChatGPT / Atlas as the architecture, task-planning, orchestration-coordination, and review layer. Codex is the default implementation engineer for normal feature development. Atlas should not normally write feature code directly; direct Atlas implementation is reserved for narrowly scoped bootstrap/orchestration repair when the Codex execution path itself is broken or unavailable.

GitHub Issues provide the persistent control plane. Codex execution happens locally on the operator workstation through the Codex CLI authenticated with the user's ChatGPT account.

The orchestration entry points are Python so the same workflow can run on Windows and Linux without maintaining separate shell implementations.

This design is derived from the proven Codex-Orchestrator-Lab model and does not require an OpenAI API key.

## Control Flow

```text
User requirement
  -> Atlas architecture review
  -> GitHub issue
  -> codex-task
  -> local Python controller
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

Codex must never merge its own work. The controller must not auto-merge, and Atlas must not merge without explicit user approval.

## Components

### bootstrap.py

`scripts/orchestration/bootstrap.py` is the prerequisite gate. The approved target checks are:

- Git is installed;
- Git `user.name` and `user.email` resolve;
- GitHub CLI is installed and authenticated;
- Codex CLI is installed;
- Codex is authenticated through the user's ChatGPT account;
- the expected GitHub repository is reachable;
- orchestration labels exist.

Current code already checks Git identity, GitHub CLI availability/authentication, Codex CLI availability, repository reachability, and labels. Explicit machine-verifiable detection of the Codex authentication/billing mode is a follow-up hardening item unless the CLI exposes a stable command for it.

It does not configure or require `OPENAI_API_KEY`.

Codex must be authenticated separately with the user's ChatGPT account. If needed:

```bash
codex login
```

Run on either Windows or Linux:

```bash
python scripts/orchestration/bootstrap.py
```

### controller.py

`scripts/orchestration/controller.py` is the local worker/controller.

It:

1. checks for `codex-revise` tasks first, then `codex-task`;
2. verifies that the local checkout is the expected GitHub repository;
3. rejects a dirty main checkout;
4. creates or reuses a dedicated task worktree;
5. invokes local `codex exec` with an explicit `workspace-write` sandbox scoped to the task worktree;
6. provides Codex a disposable temporary directory inside the task worktree so tools such as pytest can create temporary files on Windows/Linux, then removes it before repository change detection;
7. runs the deterministic pytest suite with `PYTHONPATH=src`;
8. stops if tests fail, without committing, pushing, or creating/updating a PR;
9. commits and pushes only after tests pass;
10. creates the initial PR or updates the existing PR branch;
11. posts the iteration result to the GitHub issue;
12. returns the issue to `codex-review`.

Run once (default operating mode):

```bash
python scripts/orchestration/controller.py
```

One-task execution is the normal operator workflow: one queued task is processed, a result is produced, and the controller exits.

Run continuously only when unattended queue processing is explicitly desired and validated:

```bash
python scripts/orchestration/controller.py --watch
```

Dry-run the next queued task without invoking Codex or mutating branches, worktrees, labels, comments, commits, pushes, or PRs:

```bash
python scripts/orchestration/controller.py --dry-run
```

Optional polling interval:

```bash
python scripts/orchestration/controller.py --watch --poll-seconds 20
```

The minimum polling interval is 5 seconds.

## Cross-Platform Requirement

The orchestration implementation is Python-first and must remain portable across Windows and Linux.

Rules:

- use `pathlib.Path` or equivalent platform-aware path handling;
- do not hard-code Windows `\\` or POSIX `/` separators in shared logic or tests;
- use `subprocess` rather than shell-specific command syntax;
- keep Git, GitHub CLI, Codex CLI, and pytest invocation semantics equivalent on both operating systems;
- OS-specific network transport behavior remains inside OrbitFlow's transport layer and is not duplicated by orchestration code.

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

## Test Gate

The controller treats the deterministic pytest suite as a hard gate.

If pytest fails:

- `codex-failed` is applied;
- the failure is reported to the issue;
- Codex changes remain uncommitted in the task worktree for inspection;
- no branch push occurs;
- no pull request is created or updated;
- the failed run does not create a successful iteration marker.

This prevents a known-failing implementation from advancing automatically to Atlas review.

## Authentication and Billing Boundary

The intended implementation worker is the locally installed Codex CLI authenticated with the user's ChatGPT account.

The operating policy is:

- no `OPENAI_API_KEY` dependency;
- no OpenAI API fallback for implementation;
- no automatic purchase or use of additional paid credits;
- if included ChatGPT-plan Codex usage is unavailable or exhausted, stop and surface the condition rather than switching billing paths;
- do not claim unlimited usage for any subscription tier.

Git author identity, GitHub authentication, and Codex authentication are separate prerequisites:

```text
Git user.name / user.email
    -> commit metadata

gh authentication
    -> GitHub push / issue / PR authority

Codex ChatGPT authentication
    -> local implementation-worker access
```

GitHub access uses the locally authenticated `gh` CLI.

## Security Boundaries

- Codex runs with `workspace-write`, not unrestricted filesystem access. The writable task area is the dedicated issue worktree; Git metadata and unrelated paths remain outside the intended modification boundary.
- Codex receives repository/task context only.
- Device passwords, OTPs, Teleport private keys/certificates, and production secrets must not be placed in GitHub issues or Codex prompts.
- The controller may run repository tests but does not perform live network validation.
- Live-device validation remains an operator-controlled activity using the approved OrbitFlow transport.
- Stable OrbitFlow is outside this automation boundary.
- No controller path auto-merges to `main`.
- The user remains the final merge authority.

## Failure Handling

If the local controller fails, it removes the queue labels (`codex-task` / `codex-revise`), applies `codex-failed`, and posts the failure reason to the issue where possible. This prevents `--watch` from retrying the same failed task indefinitely. Repository-cleanliness failures also include the dirty paths so the operator can correct them explicitly.

A failed run does not count as a completed implementation/review iteration unless an iteration marker was successfully posted for Atlas review.

Before retrying, inspect the task worktree and GitHub issue state. The controller intentionally refuses duplicate initial branches/worktrees rather than silently overwriting unreviewed local changes.

## Bootstrap and First Validation

From an up-to-date, clean OrbitFlow-Evo checkout:

```bash
gh auth status
codex --version
codex login
python scripts/orchestration/bootstrap.py
```

Then process one task:

```bash
python scripts/orchestration/controller.py
```

Use `--watch` only for explicitly approved unattended queue processing.

First end-to-end validation:

1. Atlas creates a trivial non-network GitHub issue.
2. Atlas/user approves the implementation plan.
3. Atlas applies `codex-task`.
4. The local controller claims the task and runs Codex.
5. Confirm a dedicated worktree, branch, PR, passing test result, and `codex-review` state are created.
6. Atlas reviews the PR.
7. Atlas posts one marked correction comment and applies `codex-revise`.
8. Confirm the controller reuses the same branch/PR and returns the issue to `codex-review`.
9. Merge only after explicit user approval.

The orchestration foundation is not considered end-to-end validated until this controlled test succeeds on at least one workstation. Cross-platform portability is covered deterministically, while full live orchestration should be exercised on both Windows and Linux when both environments are available.


The controller preflights a resolved Git author identity (`user.name` and `user.email`) before any Codex execution so commit failures are caught before implementation work begins.
