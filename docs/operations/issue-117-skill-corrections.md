# Issue #117 protected skill corrections

The implementation session received PermissionError writing
`.agents/skills/configuration-management/SKILL.md`; no protected skill was changed.
Controller/owner must apply these scoped Markdown corrections before completeness
can be claimed. Preserve historical approvals and phase-specific v1 restrictions.

- configuration-management: replace the execution milestone's **Design only; no
  executor is implemented.** with **Implemented by Issue #117; deterministic
  validation only, owner lab validation pending.** Change the opening future-live-
  execution statement to distinguish separate Catalyst/EdgeSwitch execution from
  future adapters. Label replacement-workflow material historical planning approvals
  rather than declaring the entire workflow unimplemented.
- cisco-network-cli and ubiquiti-network-cli: replace execution milestone
  **Approved design, not implemented.** with **Implemented by Issue #117; owner
  lab validation pending.** Preserve approved exact commands and save policy.
- Relevant requirements should mention normalized Cisco Name / EdgeSwitch Port
  identity, Interface or Port VLAN-table headers, exact C3750X dot1q changes,
  supplied rejection diagnostics, optional shared correlation and elapsed timing.
  C3850 omits encapsulation; save errors remain separate from Saved.

Verified behavior: [execution API](configuration-execution-api.md).
These protected edits remain pending; this document does not replace the skills.

## Controller PR description revision draft

Implements explicit summary-confirmed execution of the approved C3750X, C3850 and
EdgeSwitch predefined templates. Immutable plans and reviewed decisions bind a
single-use confirmation; per-IP shared execution performs fresh preflight, protected
backup, exact approved CLI and reusable row verification. Safe peers continue after
row failure; usable sessions save partial changes once at task end. Durable command
journals/results support offline workbook regeneration without reapply.

Review corrections recognize owner-style EdgeSwitch Interface VLAN tables, validate
standalone switchport target identity, verify approved C3750X dot1q changes without
weakening unrelated preservation, and classify supplied rejection diagnostics.
Original EXEC return still determines Saved, independently of explicit errors.
Optional shared capability metadata correlates run/digest/row/IP/interface/command,
phase/outcome/durations with sanitized exception diagnostics; standalone callers
remain independent of XLSX and execution.

Automated validation: 99 execution tests (23 added regression cases); 558 focused/
shared tests. Full controller-required suite: 2545 passed in 188.65s (Windows). Execute/report
help and git diff --check pass. Canonical manual includes Linux/Windows test and
operator lab commands. No device apply/save or live validation performed; owner
lab checks remain pending, including firmware/global-mode evidence, exact changes,
partial saves and report recovery. Protected skill status corrections above remain
blocked and require controller/owner action. No PR/Git lifecycle action was performed.
