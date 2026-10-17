# Issue #117 revision handoff for controller / Atlas

Implementation only; no commit, push, PR update, label change or merge was performed.
The controller owns PR #118 description updates. Suggested final description:

> Correct short Catalyst access verification with a narrow explicit-config fallback;
> keep parser unknowns and operational contradictions intact. Default execution
> backups to the run folder with portable relative references. Add reusable concise
> summary projection without weakening confirmation/replay binding. Replace JSON-centric
> Excel with template-grouped rows, actual attempted commands, durable fresh pre-row
> and scoped post-row evidence, readable continuation detail and separate apply,
> verification and save outcomes. Preserve older-run export without fabricated evidence.
> Owner's completed device changes were not replayed. Lab validation remains pending.

Validation commands/results are in the monthly devlog and canonical execution manual.
The full suite is the controller-required `python -m pytest -q` with this worktree's
`src` explicitly on PYTHONPATH. Owner commands are report-only for completed runs;
future writes require separate authorization. Existing run evidence cannot gain missing
pre-row captures or relocate old external backups automatically.

## Protected skill edits for Atlas

Filesystem writes were denied for these exact files. No bypass was attempted and no
skill update is claimed. Append the following scoped notes (or reconcile equivalent
wording in their current execution sections):

- `.agents/skills/configuration-management/SKILL.md`: "Owner cumulative revision,
  2026-10-17: execution CLI uses operator_summary/render_summary while full preparation
  remains digest-bound. Default protected captures are RUN/backups with run-relative
  references; explicit backups_dir still uses PATH/RUN_ID. Export uses template sheets,
  original inputs/decisions, durable fresh pre-row configuration, actual attempted CLI,
  readable post evidence and separate apply/verification/save. Older missing pre-row
  evidence is Not captured. Do not replay completed changes for presentation diagnosis."
- `.agents/skills/cisco-network-cli/SKILL.md`: "Short access output retains parser
  unknowns. Verification fallback is allowed only for missing access_vlan with matching
  normalized target, enabled/static-access and reliable fresh exact-interface config
  containing one explicit singleton access fact. Do not infer defaults or override
  operational VLANs. Preserve description/admin/unrelated checks and retain fallback
  source plus missing-field warnings in results/shared logs. Ambiguous evidence remains
  Unknown; confirmed mismatch fails."
- `.agents/skills/ubiquiti-network-cli/SKILL.md`: "Execution backups default to the run's
  backups folder. Reports preserve independent Current/Configured/Tagging and observed
  tagged/forbidden overlap without automatic warnings. Actual attempted commands and
  row-specific pre/post evidence are readable; save status remains device-wide and
  separate. Complete detail remains in retained journal/readable continuation sheets.
  Explicit external backup overrides remain honored; no standalone-backup redesign."

Canonical references: [manual](../user_manual/configuration-execution.md),
[API](configuration-execution-api.md),
[approved design](../architecture/configuration/approved-device-execution.md).

## Final deterministic validation

Windows host with this worktree's PYTHONPATH=src: executor 118 passed; focused/shared
687 passed; full controller `python -m pytest -q` 2,564 passed in 222.82 seconds.
CLI execute/report help, affected local link targets and git diff --check passed.
Linux commands were source-verified; no Linux-host or device/lab run is claimed.
The canonical manual includes copy-ready Linux/PowerShell setup, test and offline
report commands. Owner lab validation and the three protected skill edits above
remain pending. No commit, push, PR update, labels or merge was performed.
