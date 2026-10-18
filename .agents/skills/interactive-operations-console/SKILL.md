---
name: interactive-operations-console
description: Use when creating or changing the interactive operator menu, shared environment profile, or onboarding a new user-executable workflow to the console.
---

# Interactive Operations Console

## Status and source of truth
Owner-approved design: [architecture](../../../docs/architecture/interactive-operations-console.md). Implementation from Issue #123 / PR #124 was merged to `main` on 2026-10-18. Codex-reported Windows deterministic tests passed; owner-operated Windows lab validation confirmed planning and C3750X/EdgeSwitch execution with 36 verified rows and two saved devices. Linux operator validation and broader platform/failure-path live validation remain pending. The C3750X access-VLAN fallback investigation and compact Excel formatting are deferred. Verify actual source, tests and supported scripts before claiming implemented or validated behavior. Follow `AGENTS.md` and the documentation-management skill.

## Boundaries
- Interactive console is a thin adapter over existing application/services and stable user-executable CLIs, **not** another transport, parser, scheduler, vendor implementation, or configuration executor.
- Keep direct Linux/Windows CLI and public API contracts working. Existing orchestration controller and specialist validation tools are not automatically menu choices.
- Do not silently change default paths of unrelated scripts. Keep recoverable spools, confirmation authority, logs, backup confidentiality and audit references intact.
- Use `data/sys_config/configuration-profile.toml` for non-secret reusable parameters; never store passwords, OTPs, tokens, private keys, or raw secret-bearing evidence. Retire root `orbitflow.toml` only with safe loader/caller migration and tested compatibility.
- On **every applicable** interactive multi-device operation prompt concurrency 1–5, blank=1; reject invalid selections. Do not persist the concurrency choice. Apply and read-only limits remain distinct; operations on one device remain serialized.
- Validate required profile values and live Teleport session at the relevant operation boundary; expiration requires operator-controlled `tsh` authentication, not automatic OTP handling.

## Required menu coverage
Main: Configuration Management; Device Inventory; Interface & VLAN Reporting; VLAN Compliance; Configuration Backup; Environment Setting; Exit.

Configuration Management: Generate Input Template; Generate Configuration Plan; Execute Approved Plan; Review Executed Plan; Regenerate Execution Report; Back. Do not add a separate Review Plans option. VLAN Compliance: standard run, run with methodology, offline export/regeneration, Back. See architecture for paths and interaction contracts.

Engineer manually changes decision cells in generated `plan.xlsx`; console does not approve rows. The separate execution summary confirmation and all immutable digest/plan, preflight/drift, identity, backup, verification, save, replay and interrupted/Unknown protections remain owned by existing executor. Report-only views never reconnect or apply.

## Future user-executable workflows
For **every** new or materially changed user-executable script/workflow:
1. Assess whether it belongs in the console. Supported operator network workflows normally do; internal/development tools do not automatically.
2. If eligible, require integration and tests in **the same explicitly authorized Codex Issue/PR**, including relevant profile/target selection, runtime concurrency prompt (only if supported), cancellation/confirmation, outputs and errors.
3. If intentionally excluded, record owner-approved rationale in affected manual/architecture; do not silently omit.
4. Update `docs/user_manual/interactive-operations-console.md`, the workflow's own `docs/user_manual/` guide and indexes as needed.
5. Verify safe Linux/Windows help/menu smoke checks, deterministic regression tests and owner-provided live validation separately.
6. If Codex lacks write access to `.agents/`, it must note the exact needed Markdown changes for Atlas's separate reviewable documentation-only PR; never change permissions, invent a completed update, or block legitimate executable work unnecessarily.

No new documentation-enforcement CI jobs or scripts without owner request.
