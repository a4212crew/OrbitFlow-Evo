# Issue #137 / PR #138 second-review handoff — 2026-10-19

This is a review artifact, not an applied skill update or approval to merge.
No executable redesign is requested or included in this revision.

The controller/owner must resolve these outstanding review blockers on the same
Issue and PR before returning it for Atlas review:

- Obtain and retain a clean full deterministic suite result from an eligible
  protected OS-temp environment. The local failed run cannot support a PR/Issue
  claim that the full suite passed. Correct that claim until external evidence
  establishes it; Codex has not changed GitHub state.
- Apply the skill correction below in an authorized writable checkout. Ordinary
  file access to `.agents/skills/configuration-management/SKILL.md` still returns
  `Errno 30` here. Do not alter mounts or permissions to apply it.
- Obtain the owner-approved branch-history remediation procedure or an explicit
  owner risk decision for the historical environment information. Current tree
  removal is insufficient. Codex has neither rewritten history nor obtained a
  risk decision. Do not reproduce the historical values in review artifacts.
  After the approved controller action, inspect the resulting PR head and file
  list and privately scan relevant history for credential contents; report scope
  and limitations without printing sensitive values.
- Refresh open documentation-only PR #136 and reconcile its current head with
  CURRENT_STATE, the execution manual and October devlog. The read-only GitHub
  lookup failed to connect in this session. Preserve prior owner-reported
  #134/#135 evidence separately; it does not validate #137. No claim of completed
  cross-PR coordination is made.

The [execution manual](../user_manual/configuration-execution.md#approved-command-delivery-issue-137)
contains source-confirmed Linux Bash and Windows PowerShell focused/full commands,
full-log capture, and separately authorized owner-safe lab validation instructions.
Windows, owner-run and live #137 validation remain pending. Automated tests use
synthetic devices; this revision performs no device writes.

## Required Markdown skill correction (not applied)

The diff is preserved in repository Markdown so it remains reviewable independently
of ignored local validation artifacts. Atlas/controller should review and apply
it to the named skill, then replace the pending reconciliation statements with
verified status while retaining historical devlog provenance.

```diff
--- a/.agents/skills/configuration-management/SKILL.md
+++ b/.agents/skills/configuration-management/SKILL.md
@@ -9,7 +9,8 @@
 points are `python -m orbitflow.configuration.cli` and
 `scripts/configuration_plan.py`. Read `docs/architecture/configuration/offline-plans.md`
 for the v1 contract. Separate predefined Catalyst/EdgeSwitch execution is implemented
-in PR #118; owner lab validation and merge are pending. Additional adapters remain
+initially by Issue #117 / PR #118, followed by merged execution revisions.
+Owner evidence is recorded separately; validation of Issue #137 remains pending. Additional adapters remain
 future work. The restrictions below apply to v1 planning, not the separate executor.
 
 - Resolve existing `DeviceContext` snapshots; never connect or refresh inventory.
@@ -66,7 +67,7 @@
 
 ## Owner-approved configuration execution milestone — 2026-10-17
 
-**Implemented in PR #118 (Issue #117); owner lab validation and merge pending.**
+**Historical implementation milestone: PR #118 (Issue #117); superseded execution gates are reconciled below.**
 For apply, verification, save, reusable
 summary/confirmation or switchport observation, read
 [approved device execution](../../../docs/architecture/configuration/approved-device-execution.md).
@@ -90,7 +91,7 @@
 
 ## Execution presentation and progress — reviewed iteration 4
 
-Implemented on PR #118, pending owner validation/merge: `operator_summary` groups
+Historical PR #118 presentation milestone (retain subsequent owner evidence separately): `operator_summary` groups
 short findings/skips by category and source sheet/row ranges; `render_summary` uses
 compact VLAN lists with no nested evidence or primary opaque row IDs. Full bound
 preparation and replay protections remain unchanged. Execution display filters only
@@ -110,3 +111,22 @@
 optional timer never accesses channels, extends deadlines or retries writes. Display
 exceptions disable the subscriber; mandatory audit failures remain failures. See
 the supported [progress API](../../../docs/operations/configuration-execution-api.md#structured-progress-subscription).
+
+
+## Owner-approved execution simplification — 2026-10-19 (Issue #137)
+
+This supersedes older execution-stage replanning and exact fresh-state, command,
+projected-state and drift equality gates. Deliver exact immutable approved CLI
+without rerendering. Retain protected plan/workbook/digest, Approve-only supported
+selection, one explicit batch confirmation, anti-replay, fresh identity/capability/
+privilege, owned synchronized SSH and mandatory protected pre-change backup.
+Exact target presence and relevant bundle ownership, known EdgeSwitch VLAN
+prerequisites and failed dependencies remain safety checks; ordinary planning
+warnings do not re-decide approved intent. Preserve existing template-stage splits,
+consolidated post-stage observations and per-row switchport/lookup verification.
+Rejection stops that row; independent work continues only on a synchronized shell.
+Lost/ambiguous SSH stops device writes: uncertain outcomes Unknown, remaining work
+Not executed, without replay. Save once after attempted writes, including partial
+failures, only from privileged EXEC; keep save and row verification separate.
+Preserve v1/v2 planning and read-only defaults. No additional families or Manual CLI
+apply. Issue #137 owner validation remains pending; PR #136 records earlier evidence.
```

Second-review rerun: focused **462 passed (9.97s)**; full
`PYTHONPATH=src python -m pytest -q`: **3,019 passed / 25 failed (114.12s)**.
All failures are orchestration cases affected by the unchanged OS-temp Git-ancestry
safeguard. This is a failed full gate, with no external clean result available.
Local logs: `outputs/validation/issue-137-review2/focused.log` and `full.log`.
No safeguard was bypassed.
