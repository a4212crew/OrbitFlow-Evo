# Codex Orchestration Skill

Use this skill for OrbitFlow-Evo development tasks involving ChatGPT / Atlas, GitHub Issues, the local Python controller, Codex CLI, Codex task/revision lifecycle, PR review, or orchestration troubleshooting.

Read `AGENTS.md` and `CURRENT_STATE.md` before this skill. For durable architecture and state-machine detail, also read `docs/architecture/codex-orchestration.md`.

## Roles

### User

The user is:
- product owner;
- network architect / technical decision maker;
- final merge authority.

### ChatGPT / Atlas

Atlas is the default:
- solution architect;
- scope and implementation-plan owner;
- GitHub Issue/task author;
- orchestration coordinator;
- PR/diff reviewer.

Atlas should not normally implement feature code directly.

Atlas may directly patch the orchestration/bootstrap mechanism when Codex cannot operate because that mechanism itself is broken or unavailable. Keep such repair work small, reviewable, and explicitly identified as orchestration repair.

### Codex

Codex is the default implementation engineer.

Codex may:
- edit scoped repository files;
- add/update deterministic tests;
- run repository checks;
- update required task documentation.

Codex must not:
- independently redesign architecture outside the approved task;
- receive production network credentials;
- merge to `main`;
- bypass the controller/user review boundary.

## Default Workflow

```text
User requirement
    -> Atlas architecture/scope review
    -> Atlas creates scoped GitHub Issue
    -> issue receives codex-task
    -> operator runs controller for one task
    -> controller preflights workstation/repository
    -> controller creates dedicated branch/worktree
    -> controller invokes local Codex CLI
    -> Codex implements task
    -> controller runs deterministic tests
    -> controller commits and pushes
    -> controller creates/updates PR
    -> issue moves to codex-review
    -> Atlas reviews
        -> pass: await explicit user merge approval
        -> changes: Atlas review comment + codex-revise
    -> same branch/PR reused for revisions
```

One-task execution is the default:

```bash
python scripts/orchestration/controller.py
```

Use `--watch` only when unattended queue processing is explicitly desired and validated.

## Task Contract

The GitHub Issue is the scoped implementation contract.

Keep it concise and include:
- purpose;
- scope;
- constraints;
- acceptance criteria;
- architecture references only when needed.

Do not duplicate large persistent rules from `AGENTS.md`, `CURRENT_STATE.md`, or architecture docs into every issue.

## Repository Isolation

Each normal task uses:
- branch: `codex/issue-<number>`;
- dedicated sibling Git worktree.

Parallel tasks must not share one mutable working directory.

Stable OrbitFlow is outside the Evo orchestration boundary unless the user explicitly approves promotion.

## Preflight Requirements

Before invoking Codex, verify:
- Git executable available;
- Git `user.name` configured;
- Git `user.email` configured;
- GitHub CLI authenticated;
- Codex CLI installed;
- Codex authenticated through the user's ChatGPT account;
- expected OrbitFlow-Evo repository identity;
- clean main/control checkout;
- no conflicting branch/worktree for the task.

A failed preflight should stop before Codex implementation begins.

## Authentication and Cost Boundary

The intended worker is the local Codex CLI authenticated using the user's ChatGPT account.

Rules:
- no `OPENAI_API_KEY` dependency;
- no silent fallback to OpenAI API billing;
- no automatic purchase/use of additional paid credits;
- if included ChatGPT-plan Codex usage is unavailable/exhausted, stop and report it;
- Git identity, GitHub authentication, and Codex authentication are separate concerns.

The repository should not claim that a specific subscription tier has unlimited usage. It should only enforce the chosen no-API/no-automatic-paid-fallback path.

## Controller Responsibilities

The controller owns deterministic orchestration mechanics:
- task discovery;
- preflight;
- branch/worktree creation;
- Codex invocation;
- test gate;
- Git commit/push;
- PR creation/update;
- issue labels/comments/state.

Codex itself should not need to perform GitHub control-plane operations.

The controller must not auto-merge.

## Test Gate

After Codex returns repository changes, the controller runs the deterministic repository test suite.

If tests fail:
- stop before commit/push/PR progression;
- mark/report a failure state;
- preserve enough context for troubleshooting.

Live-device testing remains separate and operator-controlled.

## Review and Revision

Atlas reviews every Codex-generated PR before merge.

If corrections are required:
1. Atlas posts a clearly marked review comment.
2. Apply `codex-revise`.
3. Controller reuses the same task branch and PR.
4. Codex addresses the scoped review findings.
5. Tests run again.
6. Return to `codex-review`.

One implementation/review iteration is:

```text
Codex implementation or revision
    -> Atlas review
```

Maximum: 15 iterations under one approved plan.

After iteration 15, move to `codex-replan-required` and require Atlas + user to approve a new plan.

## Merge Boundary

No automatic merge.

- Codex cannot merge.
- Controller cannot auto-merge.
- Atlas must not merge without explicit user approval.
- User remains final technical authority.

## Failure Categories

Where practical, report failures distinctly:

1. **preflight failure**
   - missing Git identity;
   - dirty control checkout;
   - missing authentication/tool;
   - conflicting worktree/branch.

2. **controller/orchestration failure**
   - worktree/Git/GitHub state-machine error;
   - local process/environment failure.

3. **Codex execution failure**
   - Codex command fails or produces no usable changes.

4. **test failure**
   - deterministic tests reject the implementation.

A failed task must not remain continuously queued for automatic retry unless retry behaviour is explicitly intended.

## Documentation

After meaningful orchestration changes:
- update `docs/architecture/codex-orchestration.md` for durable architecture;
- update `CURRENT_STATE.md` only for current implemented/validated state;
- update `DECISIONS.md` for durable decisions;
- append detailed work to the current monthly devlog;
- keep `AGENTS.md` focused on permanent rules.
