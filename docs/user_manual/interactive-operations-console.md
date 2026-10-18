# Interactive Operations Console

Implemented for Issue #123. The console is a terminal adapter over existing services; direct CLIs and public APIs remain supported. Deterministic Windows validation is recorded in the devlog; Linux and owner-operated live validation remain pending.

## Launch and cancellation

Install repository requirements with Python 3.11+ and run from the repository root.

Linux:
```bash
export PYTHONPATH="$PWD/src"
python -m orbitflow.menu --help
printf '7\n' | python -m orbitflow.menu
python -m orbitflow.menu
```

Windows PowerShell:
```powershell
$env:PYTHONPATH = "$PWD/src"
python -m orbitflow.menu --help
'7' | python -m orbitflow.menu
python -m orbitflow.menu
```

The only option is `--profile PATH` (optional Path, default `data/sys_config/configuration-profile.toml`). Relative paths resolve from the working directory. Enter `b`, `back` or `cancel` at any prompt to return without starting the selected workflow. EOF/Ctrl+C exits; interrupting an active executor can leave partial/Unknown outcomes and requires retained-run review, never replay.

## Menus

Main: Configuration Management; Device Inventory; Interface & VLAN Reporting; VLAN Compliance; Configuration Backup; Environment Setting; Exit.

Configuration Management: Generate Input Template; Generate Configuration Plan; Execute Approved Plan; Review Executed Plan; Regenerate Execution Report; Back. There is no Review Plans action: edit only Engineer Decision cells in the generated workbook outside the console.

Inventory and Interface & VLAN Reporting each offer Run, offline report regeneration and Back. Configuration Backup offers Run and Back. VLAN Compliance offers standard Run, Run with Methodology Report, offline regeneration and Back. Recovery offers explicit partial export for supported read-only spools; compliance recovery can export either compliance or methodology records. Original spools are retained.

## Environment profile

First use of a profile-dependent action opens Environment Setting. All fields are prompted, with current/default values used on blank input; save is atomic after schema validation. Cancellation saves nothing. Routing fields are `proxy` (host[:port], without URL scheme), `cluster`, `bastion_host`, `bastion_user`. Optional `teleport_key_path` and `teleport_cert_path` contain filenames only, required for Linux transport. Passwords, OTPs, tokens, private key content and raw output never belong in this profile; unknown fields and persisted concurrency are rejected. The default local profile is Git-ignored; protect alternate profiles yourself.

Execution settings `connection_start_interval` (default 1.0) and `connection_retry_delay` (default 5.0) accept finite nonnegative seconds. Malformed, negative or nonfinite entries re-prompt with fixed feedback without echoing the value; cancellation at any point retains the previous profile unchanged. First-use setup imports legacy `orbitflow.toml` pacing. The shipped root `orbitflow.toml` is retired; existing local legacy files remain supported as fallback: existing loaders using their default `orbitflow.toml` name prefer the new validated profile when present, otherwise use legacy settings. Explicit alternate `--config` files keep their behavior. Direct CLI concurrency remains five when using the profile; interactive concurrency is always separately selected.

Profile paths:

| Field | Default |
|---|---|
| devices | data/input/devices.xlsx |
| templates | data/input/generated_template |
| plans | outputs/reports/plan_configuration |
| execution_reports | outputs/reports/configuration_execution |
| inventory | data/inventory/inventory.json |

Each applicable live operation prompts `Concurrent devices [1-5, default 1]:`. Blank means one; other than integers 1-5 reprompt. Selection is never persisted. Apply concurrency is a separate selection bound into executor preparation. Offline work never prompts concurrency or checks Teleport.

Before connecting, the console validates the device workbook through the shared loader (`management_ip`, `username`, `password` headers), displays input/target count/concurrency/safety/output scope, and requires confirmation. It checks destination access and `tsh status --format=json`: active proxy (`profile_url` or legacy `proxy_url`), cluster and timezone-aware unexpired `valid_until` must match. If both proxy fields are present, both must match; conflicting or empty fields are rejected. HTTPS prefix and trailing slash are accepted without relaxing host/port matching. Missing tsh, malformed output, expiry or routing mismatch stops the run. Authenticate externally with operator-controlled `tsh login`; the console never handles OTPs. Optional identity files must be readable. Device-row failures remain isolated by existing services.

## Configuration lifecycle

Generate Input Template writes the existing Introduction plus 22 template sheets to `config_template_YYYYMMDD_NNN.xlsx`, using local calendar date and collision-safe sequence without overwriting. Generate Configuration Plan lists eligible `.xlsx` files from the configured templates directory, newest modification time first (filename order breaks ties). Excel temporary `~$` files and directories are excluded. Choose by number; the final option accepts an explicit file path. Empty or missing directories still offer explicit path entry; invalid menu numbers re-prompt and `b` cancels. It then asks, when predefined requests require observation, a device workbook and read-only run confirmation. Manual-only planning stays offline. Output is a uniquely reserved directory containing immutable `plan.json` and matching editable `plan.xlsx`; their exact paths and digest are printed. The source workbook is unchanged.

Manually edit Engineer Decision cells to Pending/Approve/Reject. Execute Approved Plan asks for the plan JSON, reviewed workbook, device workbook and apply concurrency. It loads and validates the selected immutable JSON, displays its digest and passes that digest to the existing workbook verifier; no digest transcription is required. Select the trusted original JSON independently of the editable workbook. Existing preparation validates immutable content, protected cells, decisions/dependencies and eligibility. Its safety summary precedes the separate `Confirm execution? [y/N]:` prompt. Declining never connects. The unchanged executor owns fresh identity/state/drift and privilege checks, protected backup, ordered approved commands, independent verification/save, durable journals, replay prevention and Unknown/partial recovery. Whole-running-config saves can include unrelated changes and partial changes; EdgeSwitch can interrupt management. No unattended apply or automatic rollback is supported.

Completed execution exports a uniquely named workbook under the configured execution report directory. Protected runs/journals/backups remain under `outputs/runs/configuration_execution/`; local confirmation authority remains at `data/configuration/execution/`. Review Executed Plan lists workbooks with their stored run and outcome counts. Unreadable/non-report workbooks are skipped; up to ten fixed notices identify their listing positions, followed by a skipped count. Listing continues without device access. Regenerate Execution Report takes a retained run directory and generates a new workbook offline; it never reconnects, retries writes or changes Unknown outcomes. Recovery remains available without a valid profile/session. See [execution guide](configuration-execution.md) and [execution API](../operations/configuration-execution-api.md).

## Read-only workflows and recovery

Choose the default or an alternate device workbook, then select `all` (blank default) or unique comma-separated device row numbers such as `1,3`. Numbers count nonempty device rows returned by the shared loader, starting at 1 after the header; blank rows are ignored. Before selection, the console shows the validated row count and available row-number range. Selecting `all` shows only the selected count before confirmation. An explicit selection shows up to ten row numbers and canonical management IPv4/IPv6 addresses, with an omitted-row count for larger selections. Missing or malformed addresses (including scoped IPv6 literals) show a fixed placeholder; arbitrary cell text and credential fields are never displayed. Selecting one row always shows that row number and canonical address before network confirmation. Selection preserves workbook order and duplicate address rows remain distinct. Invalid numbers re-prompt; `b` cancels before session checks. Only selected rows reach inventory/report/compliance/backup services. Planning retains predefined requests for the selected addresses, plus offline Manual CLI requests; dependencies and eligibility still belong to the planner. Execution target scope remains controlled exclusively by engineer decisions in the reviewed workbook, then the existing executor summary and separate confirmation. Inventory refresh exports to `outputs/reports/inventory/` with the configured persistent inventory. Interface/VLAN reports use `outputs/reports/interface_vlan/`. Compliance uses the existing `policies/vlan_compliance.json` policy and `outputs/reports/vlan_compliance/`; methodology is an additional workbook. Compliance retains its spool for later export. Backups contain sensitive configuration under `outputs/backups/configuration/`; restrict access. These workflows preserve existing service fields, statuses, failure handling and logs under `outputs/logs/`. Recovery reads existing run directories; input files are not guessed or relocated.

Consult [inventory](device-inventory-refresh.md), [interface/VLAN](device-interface-vlan-report.md), [compliance](device-vlan-compliance.md), [backup](device-configuration-backup.md) and [planning](bulk-configuration-planning.md) for family support and workbook fields. Profile, workbook, session/routing, plan/workbook/consumed confirmation, export/spool, missing file/executable and permission failures have fixed actionable diagnostics. Exception messages and rejected input values are never echoed; unexpected failures retain a generic notice. Service-level errors show fixed diagnostics; inspect relevant module logs and retained run artifacts without exposing credentials.

## Validation

Windows and Linux deterministic command (after setting PYTHONPATH as above):
```text
python -m pytest tests/test_operations_console.py tests/test_configuration_execution.py tests/test_device_execution.py tests/test_cli_lifecycle.py -q
python -m pytest -q
```

Owner-operated live validation only, on separately authorized lab targets: run `tsh login --proxy=<proxy>`, then `python -m orbitflow.menu`. Configure Environment Setting; run inventory, interface/VLAN, both compliance variants and backup against a lab-only workbook, checking outputs and per-device failures. Repeat with blank and maximum concurrency and verify the next run prompts again. Expire/logout tsh and verify a live run stops while offline recovery still succeeds. For explicitly authorized lab apply, generate/review a fresh plan and first decline confirmation; then separately confirm the reviewed plan, inspect backups/journals/verification/save and offline regeneration. Do not replay historical completed or Unknown changes. No production or lab device testing was performed by Codex for this issue.

Revision validation checklist (Issue #123 / PR #124): in an authorized lab workbook with at least two devices, verify the numbered address mapping, select `2`, verify its row/address in the confirmation summary, first decline to confirm no session starts, then repeat and check only that device is contacted for each read-only menu. Try `0`, duplicate numbers and `b`; no connection should occur before confirmation. In Environment Setting try `abc`, `nan`, `-1`, then a valid number; cancel and verify the previous file is unchanged. Place an unrelated or corrupt `.xlsx` beside execution reports and verify valid reports still list offline. Generate a manual-only plan offline, select its JSON and workbook, verify the displayed digest, then decline execution. Corrupt only a disposable copy of the workbook and verify preparation refuses it before any connection. These owner-operated steps are pending; they do not authorize production apply.

Owner revision checks: with a large lab workbook, select `all` and decline; verify only the count is printed and no connection starts. Select one row and check its canonical IP, then try more than ten rows and check the bounded summary. In planning, check newest-first listing, equal-time filename ordering, explicit path, empty directory, invalid number and cancellation. Validate an externally authenticated session whose status uses `profile_url`; mismatched proxy/cluster and expired sessions must still stop. Use the Windows/Linux launch and deterministic commands above; all live checks remain owner-operated and pending.
