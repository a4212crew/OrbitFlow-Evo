# Interactive Operations Console — proposed operator guide

**Status: approved target workflow, NOT an available command on current main.** The entry point and precise console messages will be documented against implemented CLI and tests in Issue #121. Until then use existing guides in [the user manual index](README.md). This page specifies expected scenarios; commands below are **examples only, not executable today**.

## Planned prerequisites
Python 3.11+ and repository requirements, `src` importable or installed package, supported device credential workbook, existing interactive Teleport `tsh` authentication for live operations and permission to create report/run files. Never store passwords, OTP, tokens or private keys in the new profile. For Linux direct transport identity behavior and Windows forwarding setup consult [repository setup](../../README.md) and individual manuals.

## Proposed launch (after implementation)
Linux:
```bash
export PYTHONPATH="$PWD/src"
python -m orbitflow.menu
```
Windows PowerShell:
```powershell
$env:PYTHONPATH = "$PWD/src"
python -m orbitflow.menu
```

Actual module path must be verified against the resulting implementation before marking this manual operational.

## Main menu
1. Configuration Management
2. Device Inventory
3. Interface & VLAN Reporting
4. VLAN Compliance
5. Configuration Backup
6. Environment Setting
7. Exit

Environment Setting runs a first-use wizard or edits the non-secret profile `data/sys_config/configuration-profile.toml`, storing Teleport routing details and default directories. Before relevant live operations it checks Teleport validity, device Excel and paths; expired `tsh` sessions require operator reauthentication. It never attempts to supply an OTP.

Whenever a menu workflow supports multi-device execution, prompt `Concurrent devices [1-5, default 1]:`; blank=1, 2–5 allowed, invalid input reprompts. Prompt again on each run, not once per launch; do not save concurrency. No prompt for offline report generation.

## Configuration Management scenario
1. **Generate Input Template** creates `data/input/generated_template/config_template_YYYYMMDD_NNN.xlsx` with 22 existing template worksheets. Unique sequence, no overwrite.
2. **Generate Configuration Plan** selects the input workbook, uses existing read-only v2 planning and writes adjacent `plan.json` and `plan.xlsx` under a unique folder in `outputs/reports/plan_configuration/`. Console shows exact paths and source digest. Device collection uses the saved non-secret profile and separately protected `data/input/devices.xlsx`.
3. **Manual engineer review:** open `plan.xlsx` in its folder and edit only Engineer Decision cells (Pending/Approve/Reject). Leave all evidence/identities unchanged. The console has no Review Plans option.
4. **Execute Approved Plan** selects the plan pair, validates protected workbook and immutable source digest, eligible rows and dependencies; shows exact summary and asks `Confirm execution? [y/N]:`. Declining connects to no device. Approved spreadsheet rows alone do not authorize apply. Actual execution retains fresh device safety preflight, protected backup, exact approved commands, verification, save and replay prevention.
5. **Review Executed Plan** locates user-facing execution workbooks in `outputs/reports/configuration_execution/`, identifies complete/partial/Unknown results and preserved run identifiers; viewing never executes.
6. **Regenerate Execution Report** selects a retained run under `outputs/runs/configuration_execution/` and writes a new workbook offline without device connections or retries.

Expected outputs: original source Excel unchanged; immutable plan/review pair; independent execution workbook with row status, actual attempted commands, verification evidence, backup/save metadata, and retained protected journal/backups. See [execution guide](configuration-execution.md) for implemented current semantics and partial/Unknown recovery.

## VLAN Compliance scenario
Choose **VLAN Compliance → Run VLAN Compliance + Methodology Report**; select all targets from `data/input/devices.xlsx` or supported specific targets/alternate workbook, enter concurrency 1–5 (blank 1), review summary/policy `policies/vlan_compliance.json`, confirm read-only run. Underlying compliance uses the established rule engine and produces compliance and methodology workbooks in its current report directory `outputs/reports/vlan_compliance/`; source/row/device statuses are not invented. **Regenerate Previous Report** uses retained spools offline without connecting.

For normal compliance run choose the standard option; see [VLAN compliance manual](device-vlan-compliance.md) for exact current policy, outputs, error categories and recovery behavior. A device unable to be assessed does not mean compliant.

## Other operations
**Device Inventory:** choose credential targets and supported refresh/export, select concurrency, confirm read-only session; inspect inventory export and persistent inventory status. **Interface & VLAN Reporting:** select targets/concurrency and generate existing Excel interface/VLAN report. **Configuration Backup:** select targets/concurrency, confirm sensitive read-only backup capture, restrict file access and inspect per-device failures. Refer to each existing guide for actual current filenames/fields/errors; console must not invent output.

## Errors, safety and limitations
- Missing/invalid profile, credential workbook or expired Teleport session: explain issue without exposing secrets; no network operation until prerequisites are satisfied.
- Invalid concurrency: reprompt; cancellation/back makes no network changes.
- Corrupt/mismatched plan and workbook, ineligible dependencies, and unapproved rows: fail closed or skip according to existing executor; do not silently generate a new plan or approve rows.
- Post-send timeout/lost synchronization is Unknown; do not replay. Review retained events/results and reconcile with device before a new authorized attempt.
- Configuration saves may include unrelated running changes; existing complete-running-config backup, partial-save and EdgeSwitch interruption disclosures remain mandatory.
- No automatic rollback, unattended apply, extra vendor support or performance optimization is included in this proposal.
- Only deterministic tests can be run by Codex; real equipment checks and configuration validation are owner-operated. This design document is not proof the menu has been implemented.

The definitive CLI syntax, output workbook filenames and precise interactive prompts must be updated from Codex's source/tests before the feature is reported as implemented.
