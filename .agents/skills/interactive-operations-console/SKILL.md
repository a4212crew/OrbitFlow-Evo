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
- Use `data/sys_config/configuration-profile.toml` for reusable parameters and the optional manual authorization password hash described below; never store plaintext passwords, OTPs, tokens, private keys, or raw secret-bearing evidence. Retire root `orbitflow.toml` only with safe loader/caller migration and tested compatibility.
- On **every applicable** interactive multi-device operation prompt concurrency 1–5, blank=1; reject invalid selections. Do not persist the concurrency choice. Apply and read-only limits remain distinct; operations on one device remain serialized.
- Validate required profile values and live Teleport session at the relevant operation boundary; expiration requires operator-controlled `tsh` authentication, not automatic OTP handling.

## Required menu coverage
Main: Configuration Management; Device Inventory; Interface & VLAN Reporting; VLAN Compliance; Configuration Backup; Environment Setting; MAC Address Lookup; Exit.

MAC Address Lookup (main 7; Exit 8): Search MAC Address; List All MAC Addresses;
Back. Exactly two feature actions. No backend collectors or regeneration submenu
choice. Search validates dotted/colon MAC and exact workbook IP before network
confirmation; no concurrency prompt. List validates VLAN 1-4094, reuses all/subset
workbook selection and per-run concurrency 1-5 blank=1. Both reuse profile and
Teleport checks/cancellation. Existing profile schema is unchanged. Output under
outputs/reports/mac_table; recovery via direct API/CLI only. See the [MAC manual](../../../docs/user_manual/mac-address-lookup.md).

Configuration Management: Generate Input Template; Generate Configuration Plan; Execute Approved Plan; Review Executed Plan; Regenerate Execution Report; Back. Do not add a separate Review Plans option. VLAN Compliance: standard run, run with methodology, offline export/regeneration, Back. See architecture for paths and interaction contracts.

Engineer manually changes decision cells in generated `plan.xlsx`; console does not approve rows. The separate execution summary confirmation and all immutable digest/plan, fresh target/prerequisite safety, identity, backup, verification, save, replay and interrupted/Unknown protections remain owned by existing executor. Report-only views never reconnect or apply.

## Future user-executable workflows
For **every** new or materially changed user-executable script/workflow:
1. Assess whether it belongs in the console. Supported operator network workflows normally do; internal/development tools do not automatically.
2. If eligible, require integration and tests in **the same explicitly authorized Codex Issue/PR**, including relevant profile/target selection, runtime concurrency prompt (only if supported), cancellation/confirmation, outputs and errors.
3. If intentionally excluded, record owner-approved rationale in affected manual/architecture; do not silently omit.
4. Update `docs/user_manual/interactive-operations-console.md`, the workflow's own `docs/user_manual/` guide and indexes as needed.
5. Verify safe Linux/Windows help/menu smoke checks, deterministic regression tests and owner-provided live validation separately.
6. If Codex lacks write access to `.agents/`, it must note the exact needed Markdown changes for Atlas's separate reviewable documentation-only PR; never change permissions, invent a completed update, or block legitimate executable work unnecessarily.

No new documentation-enforcement CI jobs or scripts without owner request.


## Confirmed execution simplification — Issue #139 / PR #140

The existing **Execute Approved Plan** console action remains a thin adapter over
confirmed execution. Preserve its single batch confirmation, digest-bound selection,
per-device concurrency control, command/response evidence, backup, consolidated
post-template verification and EXEC-only partial save. Do not add a second menu
workflow or reintroduce execution-stage replanning/trusted-baseline equality as
console-level gates. The executor still checks live identity, interface/bundle
ownership, known prerequisites and SSH synchronization. PR #140 remains unmerged
and owner/live validation of Issue #139 remains pending at the time of this note.


## Manual Configuration — Issue #156 (owner-approved superseding contract)

This separate workflow supersedes older manual-command restrictions only for the
manual sender; legacy offline Manual CLI plans remain non-executable and predefined
planning/execution policies are unchanged. See
[manual architecture](../../../docs/architecture/configuration/manual-configuration.md)
and [operator guide](../../../docs/user_manual/manual-configuration.md).

- Accept literal engineer CLI, including configure/conf, abbreviations, unknown
  roots, wrappers, credential commands and explicit save/commit. No semantic
  allowlist/denylist; retain structural bounds and redact secrets before persistence.
- Group canonical IP rows in original workbook order, including noncontiguous rows.
  Own one DeviceSession and one exact live DeviceCLI shell per device group; identify,
  establish privilege/paging and take a protected backup once before writes. Never
  close/reopen the shell between rows.
- Start each row from confirmed privileged EXEC, enter supported global config,
  send literal bounded prompt-free blocks, then explicitly synchronize to confirmed
  EXEC after every block. Journal Commands completed / awaiting device save immediately.
  Save automatically exactly once after all device rows succeed and return to EXEC;
  only confirmed save yields Completed/Saved. Any invalid row, setup/write/boundary/
  recording failure stops same-device writes and prevents new automatic save.
  Preserve Unknown after save transmission, prior block evidence and confirmed save
  despite cleanup failure; expose unsafe cleanup. Explicit engineer persistence is
  independent. Never replay/reconnect/resume after writes. Predefined partial-save
  policy is unchanged.
- Ignore blank separators, preserve nonblank CLI and cell-line identity. Numbered
  selection filters manual_*.xlsx, including explicit paths. Hidden admin password
  verification and separate confirmation precede networking; omit pre-password prose.
- Optional manual_configuration_auth.password_hash in the local profile stores
  only a salted work-factor-protected hash, never a plaintext credential. Existing
  profiles remain compatible; manual execution fails closed without authorization.
- Atomically refresh ONE consolidated manual_output timestamp workbook after each
  device finishes, with all source rows, device summary and relative capture links.
  Receive-only hostname/IP captures sit beside it, without app timestamps/row labels
  or synthetic echoes. Manual run/report/backup folders use YYYYMMDD_HHMMSS and
  numeric collision suffixes. Journals retain structured evidence and legacy recovery.
- Source implements IOS/IOS-XE and EdgeSwitch framing; XR/Huawei manual entry/save
  remain unsupported. Owner run 20261026_120437 evidenced ME3600X 12/12 and ASR920
  2/2 confirmed saves; it rejected EdgeSwitch before connection. Later owner acceptance
  is not independent configuration verification. Preserve recorded validation limits.
