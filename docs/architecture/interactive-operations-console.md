# Interactive Operations Console and environment profile

**Status: implemented for Issue #123; deterministic validation, owner live validation pending.** Issue #123 replaces closed Issue #121 following the documentation baseline in PR #122. Existing source and tests define current behavior until Codex delivery and owner validation. No production apply is approved by this design.

## Purpose and boundaries
One interactive terminal entry point for existing operator-facing workflows, delegating to supported services. Existing direct CLIs and public APIs remain supported. Never reimplement vendor parsers, shared transport, sessions or worker pools. Keep device observation, analysis, planning, apply, verification and recording distinct. The console is not a web GUI.

## Menu contract
Main:
1. Configuration Management
2. Device Inventory
3. Interface & VLAN Reporting
4. VLAN Compliance
5. Configuration Backup
6. Environment Setting
7. MAC Address Lookup
8. Exit

Configuration Management:
1. Generate Input Template
2. Generate Configuration Plan
3. Execute Approved Plan
4. Review Executed Plan
5. Regenerate Execution Report
6. Back to Main Menu

VLAN Compliance:
1. Run VLAN Compliance
2. Run VLAN Compliance + Methodology Report
3. Regenerate Previous Report (offline)
4. Back

Other menus should offer a simple run path and any supported recovery/export actions. Present precise selected input, target scope, policy, concurrency, safety classification and outputs; ask confirmation before network operations. Back/cancel exits without device work. Do not add Review Plans: the engineer reviews the file in the filesystem. Review Executed Plan presents existing execution outcomes/report paths; it never resends commands.

## Configuration operator lifecycle
1. Generate the existing 22-worksheet input workbook in `data/input/generated_template/`, named `config_template_YYYYMMDD_NNN.xlsx` (local calendar date, day-specific sequence, collision-safe and no overwrite).
2. Select an existing workbook and call the v2 planning service (read-only). Write matching immutable `plan.json` and engineer-review `plan.xlsx` to a unique plan destination within `outputs/reports/plan_configuration/`. Show their exact paths and digest.
3. Engineer manually opens `plan.xlsx` and edits only Engineer Decision cells to Approve/Reject/Pending; no automatic approval.
4. Select matching plan artifacts for execution. Validate original plan digest and workbook integrity, decisions/dependencies and eligible rows; show explicit execution summary. Only a second explicit confirmation permits apply.
5. Delegate unchanged to the existing executor: fresh identity, relevant live state and drift/privilege gates, protected backup before writes, approved commands, per-row actual verification, safe failure handling, durable journal, per-device save policy, replay guard and Unknown/partial outcome handling.
6. View execution reports in `outputs/reports/configuration_execution/`; offline regeneration reads retained runs and does not reconnect/reapply. Preserve original planning evidence independently of execution records.

Performance tuning, skipping/reducing preflight and post-verification, new platforms, manual CLI apply, auto-rollback and unattended apply are out of scope for Issue #123.

## Environment setting and paths
Local non-secret `data/sys_config/configuration-profile.toml` is the shared console profile. First-run wizard allows entry/edit/validation of Teleport proxy, cluster, bastion host/user, connection pacing/retry and paths. Validate schema and file accessibility, required device workbook headers, and Teleport session validity at a relevant network operation. Require operator-run `tsh` login when expired; never capture OTP, password or private key in the profile. Avoid committing per-user profile values.

Default paths:
| Item | Console default |
|---|---|
| Device credentials input | `data/input/devices.xlsx` |
| Generated template inputs | `data/input/generated_template/` |
| Immutable plan + engineer review | `outputs/reports/plan_configuration/` |
| User-facing execution reports | `outputs/reports/configuration_execution/` |
| Inventory database | `data/inventory/inventory.json` |
| Environment profile | `data/sys_config/configuration-profile.toml` |

Protected internal execution spools/journals/backups remain under existing `outputs/runs/configuration_execution/` conventions; local confirmation authority at `data/configuration/execution/`; preserve other established reporting/log/backup destinations. Paths for user-facing reports are distinct from protected run metadata. Do not silently relocate historical artifacts.

The retired root `orbitflow.toml` contained read-only execution concurrency 5, start interval 1.0, retry delay 5.0; the implementation must migrate loader/callers before retiring it and preserve direct CLI override/default compatibility. Store pacing/retry, **not concurrency**, in the new profile.

## Concurrency
At **every interactive operation that actually supports multiple device workers**, prompt: `Concurrent devices [1-5, default 1]:`. Blank means 1; only whole integers 1–5 allowed, otherwise reprompt. The value is not stored and selection recurs on the next run. Do not prompt for offline template creation, workbook review or offline report export. Intra-device operation ordering remains sequential; configuration apply concurrency must remain an explicitly distinct safety setting.

## Operator scripts and future integration
Initial console covers supported inventory refresh, interface/VLAN reporting, VLAN compliance (including methodology and offline re-export), configuration backup, and existing v2 planning/confirmed predefined execution plus report recovery. Development orchestration, internal utilities and specialist live validation do not automatically enter the menu.

Every future new/materially changed user-executable workflow must be assessed for console eligibility. Eligible workflows must integrate the menu/profile/selection/report path in the same authorized development PR with regression tests and updated manuals; an omission needs explicit owner-approved exclusion. This requirement is routed through `AGENTS.md`, the documentation-management skill, and the console skill, with Atlas reviewing PR completeness. Do not add enforcement CI/scripts without authorization.

## Safety, compatibility and validation
Never interpret approval workbook edits as authenticated authorization or confirmation to apply. Preserve plan integrity, protected workbook checks, user confirmation, identity/state drift checks, dependencies, privilege, protected backup, command journals, independent verification/save outcomes, no unsafe replay, and deterministic Unknown classification. No second implementation of device application or automatic configuration rollback.

Deterministic tests cover menu navigation, first-run/profile validation, Teleport expiry/missing files, no secret persistence, daily naming collision, repeated concurrency prompt/bounds, cancellation, plan approval/replay gates, report-only paths, direct CLI compatibility and regression suites. Codex documents exact Windows/Linux smoke and owner-operated live tests. Lab and production changes require separate explicit owner authorization.

## Implemented compatibility note (Issue #123)

`python -m orbitflow.menu` implements this adapter. Legacy root `orbitflow.toml` remains a fallback for compatible direct callers; default loaders prefer the validated shared profile pacing without persisting interactive concurrency. Explicit alternate configuration paths retain their contracts. Offline recovery does not require profile/session setup. See the [implemented manual](../user_manual/interactive-operations-console.md) for exact prompts, paths and validation commands. Linux and owner live validation remain pending.

Implemented revision: read-only menus show the row count/range, summarize all-selection by count and explicit selections by at most ten canonical row/address identities (fixed placeholders for invalid values) before network confirmation, and select all or unique loaded device row positions through the shared target loader; planning scopes predefined requests by selected addresses. Apply scope remains engineer-workbook decisions. The console derives the digest from validated immutable JSON and supplies it unchanged to workbook verification. Invalid reports are skipped with bounded fixed notices. No executor/preflight safety changes.

MAC Address Lookup: Search MAC Address; List All MAC Addresses; Back. No collector/recovery submenu actions. Search uses one exact workbook IP, validates before network and omits concurrency; VLAN listing reuses all/subset and per-run concurrency. Existing profiles remain unchanged. See [contract](mac-address-lookup.md).


Issue #156 approved design: [separate Manual Configuration](configuration/manual-configuration.md) supersedes legacy offline Manual CLI for new input generation only. Legacy plans remain offline/non-executable; predefined partial-save behavior is unchanged. The new optional profile password-hash section and success-only per-row save are implemented on this branch with synthetic deterministic tests; owner-operated live validation remains pending. Historical evidence above is retained.
