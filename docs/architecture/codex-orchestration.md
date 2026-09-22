# Codex Orchestration for OrbitFlow-Evo

## Purpose

OrbitFlow-Evo uses ChatGPT / Atlas as the architecture, planning, and review layer and Codex as the implementation engineer.

The orchestration layer coordinates work through GitHub Issues, GitHub Actions, feature branches, and pull requests. It does not grant Codex access to production network devices, Teleport identities, or device credentials.

## Control Flow

```text
User requirement
  -> Atlas architecture review
  -> GitHub issue
  -> codex-task label
  -> GitHub Actions / Codex
  -> codex/issue-<number> branch
  -> pull request
  -> Atlas review
       -> pass: codex-approved
       -> changes: Atlas issue comment + codex-revise
  -> explicit human merge
```

Codex must never merge its own work.

## Initial Task

Atlas creates a scoped issue and, after the implementation plan is approved, applies `codex-task`.

The `Codex Task` workflow:

1. accepts only an owner-triggered `codex-task` label event;
2. checks out `main`;
3. installs repository test dependencies before Codex starts;
4. creates an isolated `codex/issue-<number>` branch;
5. runs `openai/codex-action@v1` with the built-in `:workspace` permission profile;
6. supplies repository rules plus the issue task to Codex;
7. runs the deterministic test suite;
8. commits and pushes the task branch;
9. opens a pull request;
10. marks the issue `codex-review`.

Test failure does not automatically merge or discard the implementation. The PR records the test outcome so Atlas can review the code and failure together.

## Atlas Review and Revisions

When Atlas requires corrections, Atlas posts an issue comment containing the marker:

```text
<!-- atlas-review -->
```

followed by concise required corrections, then applies `codex-revise`.

The revision workflow checks out the existing task branch, passes the original issue plus the latest marked Atlas review to Codex, runs tests, commits the revision, and returns the issue to `codex-review`.

Atlas should keep correction prompts concise and should not restate repository architecture that already exists in `AGENTS.md` and the canonical architecture documents.

## 15-Iteration Replan Gate

One Codex implementation/revision followed by one Atlas review is one iteration.

The current plan may use at most 15 iterations. Iteration state is recorded in issue comments using a machine-readable marker:

```text
<!-- orbitflow-codex-iteration:N -->
```

If another revision is requested after iteration 15, the workflow must not run Codex. It removes the revision state, applies `codex-replan-required`, and stops automated implementation.

Atlas and the user must then reassess the implementation plan. A newly approved plan starts a fresh implementation cycle.

## Labels

- `codex-task` — approved task awaiting initial implementation.
- `codex-running` — Codex is currently executing.
- `codex-review` — implementation is waiting for Atlas review.
- `codex-revise` — Atlas requested another revision.
- `codex-approved` — Atlas review passed.
- `codex-pr` — an implementation PR exists.
- `codex-failed` — orchestration failed and requires inspection.
- `codex-replan-required` — iteration 15 was exhausted under the current plan.

Run the `Codex Orchestration Bootstrap` workflow once after installation to create these labels.

## Required Secret

The GitHub repository must contain an Actions secret named:

```text
OPENAI_API_KEY
```

The secret is supplied only to the official Codex GitHub Action.

Do not add network-device credentials, Teleport keys/certificates, OTPs, or production passwords to GitHub Actions secrets for this orchestration.

## Security Boundaries

- Only the repository owner may trigger the provided Codex task/revision jobs.
- Codex runs with the `:workspace` permission profile.
- Dependencies are installed before Codex runs; Codex does not require production network access.
- Codex never receives live device credentials or Teleport identities.
- No workflow auto-merges to `main`.
- Stable OrbitFlow is outside this automation boundary.
- Live validation remains an operator-controlled local activity.

## Parallel Tasks

Each issue uses a deterministic branch:

```text
codex/issue-<number>
```

GitHub Actions concurrency prevents overlapping runs for the same issue while allowing separate issues to execute independently.

This provides task isolation without sharing one mutable local workstation checkout.

## Bootstrap and First Validation

1. Add the `OPENAI_API_KEY` Actions secret.
2. Run `Codex Orchestration Bootstrap` manually from GitHub Actions.
3. Confirm the eight orchestration labels were created.
4. Create a trivial, non-network test issue.
5. Have Atlas review the issue and apply `codex-task`.
6. Confirm Codex creates a branch and PR and the repository tests run.
7. Have Atlas request one controlled revision using a marked review comment plus `codex-revise`.
8. Confirm the same PR branch updates and the issue returns to `codex-review`.
9. Merge only after explicit user approval.

The orchestration foundation is not considered live validated until this end-to-end test succeeds.
