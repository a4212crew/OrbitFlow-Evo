---
name: documentation-management
description: Mandatory documentation maintenance for any meaningful OrbitFlow-Evo development, bug fix, public interface change or documentation restructuring. Read with the directly relevant capability skill; do not load every guide.
---

# Documentation Management

## Scope and ownership

This skill governs **how Codex maintains documentation during approved implementation**. Atlas owns architecture, documentation organization, pre-Issue documentation reconciliation and PR review. Codex alone edits source, scripts and tests; Codex also updates affected Markdown documents within its authorized Issue/PR. Documentation-only Atlas edits must be reviewable, avoid conflicting with active Codex work, and must not alter approved decisions silently.

Follow `AGENTS.md` and the routed capability skill. Consult [documentation index](../../../docs/README.md) to find the authoritative document. Never treat an historical devlog or proposed design as current implementation authority.

## Every meaningful implementation / fix

1. Identify changed observable behaviour, inputs, output, supported devices, commands and public contracts from **actual source and tests**.
2. Append a **short dated entry** to `docs/devlog/YYYY-MM.md`: Issue/PR, change summary, affected modules, operator-visible effects, automated test evidence, live/operator validation status (pending unless owner confirmed), limitations and documentation changed. Do not load all preceding monthly devlogs; use targeted reads. Do not rewrite existing history.
3. Maintain `docs/devlog/README.md` as a **monthly index only**. Add missing month links and a new month when created; do not copy log entries into the index.
4. Update the affected README, module/function description, operator guide, API reference, architecture and `docs/CURRENT_STATE.md` **only where behaviour or the implemented/validated baseline changes**. Update `docs/ROADMAP.md` when a planned capability changes status. Never describe unapproved intent or unvalidated functionality as implemented.
5. Add new documentation to the right index. Check every affected relative link, path and in-page anchor after edits. Preserve existing paths unless the task explicitly authorizes moves.
6. In PR summary, list documentation changed, validations performed, and any required documentation still pending. Missing required docs are review findings; make revisions on the same Issue/PR.

## Public scripts, functions and APIs

**User-executable scripts and CLI workflows:** Maintain their canonical user guides in `docs/user_manual/`, indexed by `docs/user_manual/README.md`. Both **Atlas and Codex may create or update Markdown guides** there: Atlas through reviewable documentation-only changes (including pre-Issue reconciliation), and Codex within its authorized development Issue/PR whenever executable behaviour changes. Neither may edit application code outside their assigned authority. Maintain links to these guides from `docs/README.md` and relevant README/capability documents. Do not move existing guides or break their references without an approved migration and reference review.

**Supported public Python/HTTP APIs:** Keep API/interface contracts discoverable from the existing operations/API documentation index until a separately approved structure change. A CLI and its underlying public API may have distinct references linked together.

Each new or materially changed executable script or supported public API must document, as applicable:

- Purpose, module/entry point, read-only/planning/apply classification and side effects.
- Supported families, environment, dependencies, credentials/Teleport requirements without exposing secrets.
- All user-facing parameters: name, type, required/optional, defaults, valid ranges/choices, input validation and precedence.
- Workflow scenarios (for example single and bulk, success, partial failure and invalid input).
- Sanitized sample files/requests/arguments, copy-ready Linux and Windows commands when supported, HTTP method/path or Python call signature.
- **Expected result for each scenario**: return value or response, status/errors, output path, workbook sheets/columns/fields, logs and limitations.
- Relevant failure/partial-success semantics, warnings, verification steps and operator/live-validation status.

Document only supported, stable/public interfaces. An internal helper is not automatically a public API. Never invent flags, defaults, output filenames, scenarios, or supported platforms. Verify against actual signatures, parsers and tests.

## Architecture and historical records

- `AGENTS.md`: only permanent cross-cutting rules and exact skill routing; no long business rules.
- `docs/CURRENT_STATE.md`: current verified implementation and limitations; not a historical narrative.
- `ARCHITECTURE.md`, `DECISIONS.md`, `docs/architecture/`: approved design and decisions; mark superseded statements rather than erasing provenance.
- `docs/ROADMAP.md`: future/planned work; not evidence a capability exists.
- `docs/devlog/YYYY-MM.md`: append-only history, not current instructions.
- `docs/user_manual/`: canonical user manuals for user-executable scripts/CLI workflows, maintained by Atlas and Codex; `docs/user_manual/README.md` is their index.
- `docs/operations/`: existing operator and supported API references; preserve their paths and link to canonical user manuals during migration.
- `docs/README.md`: navigation and document authority. **Until later migration phases, use current paths above; do not assume proposed relocated paths already exist.**

## Before finishing

Confirm: devlog entry; affected README/guide/API/function descriptions; truthful current-state and planning status; indexes/relative links; clear test and operator validation status; no secret exposure. **No documentation enforcement scripts, CI checks or auto-generated docs are authorized by this skill.** Atlas reviews completeness manually.
