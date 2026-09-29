# Atlas GitHub Issue Creation Rules

This file is the permanent issue-creation contract for OrbitFlow-Evo.

Atlas must read this file before creating or materially rewriting any GitHub Issue intended for Codex/controller execution.

## 1. Roles and Authority

- User = product owner, network architect, final technical and merge authority.
- Atlas = architecture, scope, issue creation, orchestration coordination, and PR review.
- Codex = implementation engineer.
- Controller = issue lifecycle, worktree/branch, Codex invocation, deterministic test gate, commit/push, PR creation/update, and workflow state transitions.
- Codex, controller, and Atlas must not merge without explicit user approval.

## 2. One Issue = One Scoped Task

Each implementation task must have one focused GitHub Issue.

Do not combine unrelated features, refactors, fixes, or documentation work merely to reduce issue count.

A revision to the same approved task stays on the same Issue, branch, worktree, and PR.

## 3. Read Before Writing the Issue

Before creating the Issue:

1. Read `AGENTS.md`.
2. Read this file.
3. Read only the skill file(s) directly relevant to the task.
4. Inspect the smallest relevant portion of the repository needed to understand current behaviour.
5. Read `CURRENT_STATE.md` only when current implementation status or known limitations materially affect the task.
6. Read architecture/devlog documents only when directly required.

Do not broadly ingest the repository for a narrowly scoped task.

## 4. Issue Content Style

Keep the Issue short and implementation-oriented.

Prefer this structure:

```text
Task:
<one concise outcome>

Requirements:
- <required behaviour>
- <important architecture/safety constraint>
- <test expectation>

Acceptance:
- <observable success condition>
- relevant deterministic tests pass

Do not merge.
```

Do not copy large architecture explanations into the Issue when the relevant rules already exist in `AGENTS.md` or a skill file.

Point Codex to the authoritative documentation instead.

## 5. Issue Must Describe Behaviour, Not Micromanage Code

The Issue should state:

- what must change;
- what behaviour must be preserved;
- which architecture contract applies;
- what acceptance result is required.

The Issue should normally not dictate:

- exact function names;
- exact file edits;
- detailed implementation sequence;
- speculative internal design;

unless those details are necessary to preserve an approved architecture.

Codex should inspect the repository before implementing.

## 6. Mandatory Safety and Architecture Boundaries

Every Issue must preserve these rules where applicable:

- preserve unrelated working behaviour;
- no credentials, passwords, OTPs, tokens, private keys, or production secrets in Issues, prompts, logs, commits, or repository files;
- deterministic runtime behaviour;
- no LLM-generated device configuration at runtime;
- vendor-specific logic remains isolated;
- higher-level workflows reuse shared transport, inventory, capability, logging, and application interfaces;
- multi-device features reuse the shared device-execution layer rather than introducing feature-specific concurrency;
- no silent architecture redesign outside the approved task;
- configuration-changing behaviour requires explicit user intent;
- one failed safe batch item should not terminate the entire batch unless continuing creates risk.

Do not repeat all of these in every Issue if `AGENTS.md` already covers them. Include only task-specific constraints plus a direction to follow `AGENTS.md`.

## 7. Codex Issue Contract

For a normal implementation task, the Issue should explicitly tell Codex to:

- inspect the repository and relevant files before making changes;
- follow `AGENTS.md` and the relevant skill file(s);
- preserve unrelated behaviour;
- add or update deterministic tests for changed behaviour;
- not merge.

Avoid long Atlas-generated implementation prompts. Repository documentation is the source of detailed architecture context.

## 8. Labels and Controller Contract

For a new Codex implementation task:

- create the Issue in `a4212crew/OrbitFlow-Evo`;
- apply the `codex-task` label;
- do not manually create the Codex branch unless the workflow specifically requires recovery;
- controller uses the Issue to create/manage the dedicated `codex/issue-<number>` branch/worktree;
- controller opens or updates the PR.

Do not simultaneously apply workflow labels that conflict with the intended controller state.

## 9. Revision Contract

If Atlas reviews a PR and changes are required:

- keep the same Issue;
- keep the same branch/worktree/PR;
- post the revision contract as an owner-authored comment on the GitHub Issue itself, not only on the PR;
- include the exact `<!-- atlas-review -->` marker in that Issue comment;
- include the actual revision findings/instructions in the same comment;
- create the marked Issue comment successfully before applying `codex-revise`;
- PR comments may be used for human-readable review notes, but they do not replace the Issue-level revision contract consumed by the controller;
- transition only to the workflow label/state expected for revision;
- do not create a replacement Issue unless scope has genuinely changed into a different task.

Revision sequence:

```text
Atlas finds changes required
    -> post owner-authored Issue comment with <!-- atlas-review -->
    -> include concrete revision findings
    -> set Issue label to codex-revise
    -> operator runs controller
    -> controller reads revision context from Issue comments
    -> same worktree/branch/PR is reused
```

Maximum implementation/review iterations follow the orchestration rules in `AGENTS.md` and the Codex orchestration skill.

## 10. Review and Merge

Atlas reviews implementation against:

- the Issue;
- `AGENTS.md`;
- relevant skill files;
- deterministic tests;
- preservation of unrelated behaviour.

Atlas may request revisions but must not merge without explicit user approval.

When the user explicitly approves merge, follow the current orchestration/merge procedure and close/clean the Issue workflow state as required.

## 11. Default Atlas Issue Template

Use this as the starting point, then shorten or adapt it to the task:

```text
Task:
Implement <approved outcome>.

Requirements:
- Follow AGENTS.md and <relevant skill path>.
- <task-specific requirement 1>
- <task-specific requirement 2>
- Preserve unrelated working behaviour.
- Add/update deterministic tests for changed behaviour.

Acceptance:
- <observable result>.
- Relevant deterministic tests pass.

Inspect the repository and relevant files before making changes.

Do not merge.
```

## 12. After Creating the Issue

Atlas should report back to the user with:

- Issue number and title;
- confirmation that `codex-task` was applied;
- a concise summary of the scope;
- the next operator action, normally running the controller.

Do not overwhelm the user with the full Issue body unless requested.
