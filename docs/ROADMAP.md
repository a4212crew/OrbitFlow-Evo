# ROADMAP.md — OrbitFlow Future Work

This file contains future ideas and is not a permanent instruction set.

Issue #154 implements lab-first ME3600X/ASR920 confirmed execution for Templates
9–13, including complete EVC recreation, fresh safety checks and independent
verification. Existing CLI/API/console and recoverable reporting are reused.
Owner lab and Linux validation remain pending; other families, Manual CLI apply
and automatic rollback/resume remain future work. See the [execution manual](user_manual/configuration-execution.md#me3600x-and-asr920-issue-154).

Items here are not automatically approved implementation tasks. Move an item into an explicit task before Codex implements it.

## Potential Enhancements

- Store daily snapshots in MySQL or PostgreSQL.
- Build a web dashboard for interface changes.
- Add device grouping by region/site.
- Add email reporting for daily changes.
- Add Git-based snapshots of collected raw outputs.
- Add NMS inventory integration.
- Add topology mapping based on LLDP/CDP.
- Add controlled rollback execution only after provisioning has sufficient field testing.
- Add optional RAG/LLM summaries only after deterministic structured parsing is complete.
- Add database-backed history while preserving Excel workflows where still required.
- Add additional inventory sources only through an explicit approved architecture change.
- Expand transport/session abstraction so collectors and provisioners share one stable device-session API.
- Add credential-provider abstraction suitable for both Windows and Linux.
- Add additional vendor/platform skills as OrbitFlow scope grows.

## Universal Configuration Management (Proposed)

Issue #117 implements the initial approved C3750X/C3850/EdgeSwitch predefined
execution milestone with summary confirmation, fresh preflight, independent
verification/save and durable report recovery. See the
[execution manual](user_manual/configuration-execution.md). Deterministic validation
is implemented; owner lab/live validation remains pending. The generic delivery
order below is historical: IOS-XR/other-family execution, Manual CLI execution,
HTTP integration, automatic rollback and drift reconciliation remain future work.

Architecture: [docs/architecture/configuration/](architecture/configuration/README.md). These are prospective phases, not approved implementation issues or completed features.

1. Define and validate a versioned shared Change Plan contract for manual CLI, Excel/CSV, templates and compliance-derived proposals.
2. Build a non-destructive validation and approval boundary, reusing shared device execution, transport, backups and logging.
3. Introduce controlled IOS/IOS-XE execution with mandatory preflight, verified state, explicit save and safe failure/unknown-state reporting; validate in a lab first.
4. Add tested, capability-gated transactional IOS-XR support, then EdgeSwitch and other families as separately scoped work.
5. Add reviewed configuration templates, bulk input and audit-ready UI/scheduling integrations.
6. Add desired-state storage, drift detection and approval-gated reconciliation after implementation maturity.

Automated rollback must remain conditional on vendor capability and field-tested recovery. Configuration concurrency requires its own conservative, explicitly approved policy.

## Approved documentation baseline: template-based configuration planning (2026-10-11)

The earlier generic ordering above is exploratory, not a current implementation plan. Approved future target: [22-template Gap C configuration planning](architecture/configuration/guided-bulk-planning.md). It uses one input worksheet per family/function; live read-only observation and existing-CLI evidence for predefined templates; offline-only Manual CLI; common engineer review and digest-bound immutable plans; reusable service APIs. **Configuration planning v2 is now implemented on `main` as an offline/read-only planning workflow**; consult [the operator guide](operations/bulk-configuration-planning.md) and [template reference](operations/configuration-template-reference.md) for supported commands, scenarios and limitations. Issue #88 and PR #89 were superseded, and the later v2 implementation has merged. **Issue #117 now implements confirmed predefined Catalyst/EdgeSwitch apply, verification and save; rollback and other execution families remain future work. Owner live/lab validation is pending.**

Issue #117 review corrections support real EdgeSwitch Interface VLAN headers with
strict table completeness, require matching standalone switchport target headers,
verify the approved C3750X dot1q change while preserving unrelated settings, and
recognize supplied command-not-found/range rejections. C3850 omits the selector.
Save remains prompt-based with errors separate. Optional capability correlation
retains run/row/digest, target/command, elapsed timing and safe failure diagnostics;
see the [API reference](operations/configuration-execution-api.md). Owner lab validation remains pending.


Issue #117 cumulative owner revision (2026-10-17): execution now uses a concise reusable
operator summary without weakening digest-bound confirmation; protected backups default
to the execution run's `backups/` with relative references (explicit external override
remains supported). Reports group original template rows with fresh pre-row evidence,
actual attempted commands, readable post evidence and independent apply/verification/save
outcomes. Older missing pre-row evidence is Not captured. Short Catalyst access responses
permit only reliable explicit exact-port configuration fallback, with source/warnings;
pure parser unknowns and contradictory operational facts are preserved. See the
[execution manual](user_manual/configuration-execution.md). No completed configuration was replayed; owner lab validation
and merge remain pending.

Issue #117 iteration 3: execution summaries group findings by source sheet/row ranges
without nested evidence; template reports expose individual input columns, compact
checks and linked complete detail, and preserve manifest run identity after relocation.
Presentation alone suppresses tagged/membership overlap warnings. Optional structured
progress drives immediate flushed CLI stages and five-second waiting updates without
accessing channels or replaying writes; Python API calls remain quiet by default.
Fallback field/source and journal warning messages survive shared safe log formatting.
Owner live/lab validation and protected skill reconciliation remain pending.

## MAC lookup delivery (Issue #130)

Read-only MAC snapshots, operational XR attachment lookup, exact mapping, two-action operator workflow and offline workbook recovery are implemented with deterministic sample tests. Owner-operated family/Linux validation remains pending; MAC/bridge-domain skill routing is included on this PR branch. See [manual](user_manual/mac-address-lookup.md) for exact limitations; no device writes or peer following are included.

## Manual Configuration — Issue #156

Separate Excel multiline-row execution is implemented on this branch with deterministic synthetic validation; owner-operated Windows/Linux lab validation is pending. New planning inputs omit legacy Manual CLI; historical immutable plans/reports retain compatibility. XR commit/candidate ownership and Huawei entry/save completion remain explicit unsupported gaps; Junos is unsupported. See the [manual](user_manual/manual-configuration.md).

Issue #156 usability revision on this branch: blank cell separators are accepted,
manual workbooks use the shared numbered chooser, and each device immediately
publishes a short report with a real relative capture hyperlink. Receive-only
captures live beside device reports; run journals retain structured audit evidence
and legacy offline recovery. See the [manual](user_manual/manual-configuration.md). Owner lab validation is pending.
