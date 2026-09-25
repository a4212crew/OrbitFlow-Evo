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

### Operational controller

`scripts/orchestration_v2/controller.py` is the sole operational controller. The
legacy `scripts/orchestration/` implementation was removed in Issue #18 after
full end-to-end validation and explicit user approval. The v2 directory name is
unchanged. Preflight is integrated in `scripts/orchestration_v2/preflight.py`;
there is no separate bootstrap script.

The controller validates Git and author identity, GitHub authentication,
repository identity, a clean control checkout, Codex installation, and
ChatGPT-account authentication before selecting a task. An active
`OPENAI_API_KEY` or unverifiable ChatGPT authentication fails closed.

Process one queued task:

```bash
python scripts/orchestration_v2/controller.py
```

Preview the next queued task without invoking Codex or mutating Git/GitHub state:

```bash
python scripts/orchestration_v2/controller.py --dry-run
```

The controller processes one task and exits. Optional `--watch` processes tasks serially, prioritizing revisions, with a 15-second polling default (`--poll-seconds`, minimum 5). Idle polls and successful review/replan transitions continue watching. Failures stop watching without retry; global preflight failures stop before execution. Ctrl+C exits cleanly. `--watch --dry-run` repeatedly previews without mutation. Discovery excludes review, approved, failed, replan-required, running, and PR states even if queue labels remain. Atlas review is still manually triggered.
See the implementation phases below for workspace, execution, and publication details.

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
- `codex-replan-required` — iteration 10 was exhausted under the current plan.

These labels must exist in the repository before task processing. Repository setup is operator-owned; v2 does not create labels.

## Atlas Review Contract

When Atlas requires corrections, Atlas posts an issue comment containing:

```text
<!-- atlas-review -->
```

followed by concise required corrections.

Atlas then applies `codex-revise`.

The controller passes the original issue plus the latest owner-authored marked Atlas review to Codex. The same task branch and PR are reused.

Atlas should keep correction prompts concise because persistent architecture already lives in the repository.

## 10-Iteration Replan Gate

One successful Codex implementation/revision followed by one Atlas review is one iteration.

Successful iterations are recorded in issue comments with:

```text
<!-- orbitflow-codex-iteration:N -->
```

A plan may use at most 10 iterations.

If another revision is requested after iteration 10, the controller does not run Codex. It applies `codex-replan-required` and stops automated implementation.

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

If the local controller fails, it removes the queue labels (`codex-task` / `codex-revise`), applies `codex-failed`, and posts the failure reason to the issue where possible. This prevents subsequent one-task runs from selecting the same failed task automatically. Repository-cleanliness failures also include the dirty paths so the operator can correct them explicitly.

A failed run does not count as a completed implementation/review iteration unless an iteration marker was successfully posted for Atlas review.

Before retrying, inspect the task worktree and GitHub issue state. The controller intentionally refuses duplicate initial branches/worktrees rather than silently overwriting unreviewed local changes.

## Operator Setup and Validation

From an up-to-date, clean OrbitFlow-Evo checkout:

```bash
gh auth status
codex --version
codex login
```

Then process one task:

```bash
python scripts/orchestration_v2/controller.py
```

Configure Git author identity and ensure the labels above exist before processing tasks. The controller runs its prerequisite checks on every invocation.

End-to-end validation checkpoints:

1. Atlas creates a trivial non-network GitHub issue.
2. Atlas/user approves the implementation plan.
3. Atlas applies `codex-task`.
4. The local controller claims the task and runs Codex.
5. Confirm a dedicated worktree, branch, PR, passing test result, and `codex-review` state are created.
6. Atlas reviews the PR.
7. Atlas posts one marked correction comment and applies `codex-revise`.
8. Confirm the controller reuses the same branch/PR and returns the issue to `codex-review`.
9. Merge only after explicit user approval.

The approved Issue #18 contract confirms that orchestration v2 passed full end-to-end validation and authorizes legacy retirement. This task does not add a new live validation run or claim additional platform coverage. Cross-platform portability remains covered by deterministic tests.


The controller preflights a resolved Git author identity (`user.name` and `user.email`) before any Codex execution so commit failures are caught before implementation work begins.

## Operational Implementation Phases

The operational implementation remains under `scripts/orchestration_v2/`. Legacy retirement does not change its runtime behavior or controller/Codex ownership boundaries.

The controller implements these phases:

1. **Preflight** — validates Git, Git author identity, GitHub CLI authentication, repository identity, a clean control checkout, Codex installation, and ChatGPT-account authentication. An active `OPENAI_API_KEY` or an authentication state that cannot be verified as ChatGPT-based fails closed before Codex runs.
2. **Task/workspace preparation** — discovers one `codex-revise` or `codex-task` Issue, plans/validates `codex/issue-<number>`, uses a dedicated sibling worktree, and supports a read-only dry-run.
3. **Codex + test gate** — invokes local Codex with `workspace-write`, keeps temporary files in unique controller-owned OS-temp directories outside Git worktrees, requires repository changes, and runs the full deterministic pytest suite as a hard gate.

4. **Publish and review** ? after the full test gate, stage changes in the isolated worktree, commit with the preflighted identity, push the explicit task branch, create/update its PR, transition to `codex-pr`, post the successful iteration marker, and transition to `codex-review`. Initial and revision tasks follow `codex-task`/`codex-revise` -> `codex-running` -> `codex-pr` -> `codex-review`. Transitions read the issue labels and remove only attached state labels, preserving unrelated labels and tolerating absent states. Optional watch mode continues after review; no auto-merge exists.

Revision discovery reads paginated issue comments, selects the latest owner-authored `<!-- atlas-review -->`, and requires an existing open task PR. Existing worktrees must be clean, on the expected branch, and match the fetched remote after a fast-forward-only update. Codex receives the original contract plus the requested revision. A worker HEAD change is rejected. Iteration markers count successful cycles; requests after iteration 10 move to `codex-replan-required`. A new approved plan requires an explicit operator reset of the prior cycle's markers; relabeling alone does not reset the counter.

Selected-task failures transition to `codex-failed`, removing queue/running labels and preserving prerequisite, controller, Codex, or test failure categories. Global preflight failures occur before task selection and exit without claiming a task. If GitHub failure reporting itself fails, the controller exits with both errors and requires manual inspection; it cannot guarantee remote dequeue during an outage.

Temporary storage uses `tempfile.mkdtemp` under the OS temporary directory, with an `orbitflow-` prefix, task-worktree name, purpose, and unique suffix. Codex receives its external directory through `TEMP`, `TMP`, and `TMPDIR`; controller pytest receives those variables and an external `--basetemp`. Output capture also uses an owned external directory. An OS-temp override resolving inside a Git checkout is rejected before creating directories. No worktree-local temporary directory or Git cleanup prerequisite is used.

Each execution attempts bounded cleanup in `finally`, including failed launches and failed tests. Cleanup refuses symlinks/reparse points and never invokes ACL reset tools or requests administrator privileges. An unrecoverable permission/locking failure prints a warning with the retained external path to stderr; it neither masks execution/test failures nor blocks staging or worktree removal. External artifacts may remain for later cleanup by their owner. Test failures still block publication.
