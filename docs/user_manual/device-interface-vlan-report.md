# Interface and VLAN report — operator manual

**Script:** `scripts/device_interface_vlan_report.py`. **Purpose:** collect read-only interface and VLAN facts from approved Excel targets and produce an Excel report.

## Prerequisites and safety
Run from the repository root with Python 3.11+, installed `requirements.txt`, `PYTHONPATH=src` if required, and an authenticated `tsh` profile. The input workbook contains approved device targets; credential material must not be committed. Provide all four required Teleport routing options: `--proxy`, `--cluster`, `--bastion-host`, `--bastion-user` (strings). Linux Teleport key/certificate file paths may be required; supply `--teleport-key-path` and `--teleport-cert-path` (optional paths, default unset). No script here performs configuration apply.

## Inputs and defaults
Required positional `excel_path` (Excel file) and the four Teleport routing strings. Optional `--teleport-key-path` and `--teleport-cert-path` (paths, unset); `--inventory-path` (`data/inventory/inventory.json`); `--reports-dir` (`outputs/reports/interface_vlan`); `--log-root` (`outputs/logs`); `--spool-root` (`outputs/runs/interface_vlan_report`); `--config` (`orbitflow.toml`).

## Examples
Linux:
```bash
python scripts/device_interface_vlan_report.py outputs/devices.xlsx --proxy teleport.example.net:443 --cluster example-cluster --bastion-host example-bastion --bastion-user example-user --teleport-key-path "$TELEPORT_KEY_PATH" --teleport-cert-path "$TELEPORT_CERT_PATH"
```
Windows PowerShell:
```powershell
python scripts/device_interface_vlan_report.py .\outputs\devices.xlsx --proxy teleport.example.net:443 --cluster example-cluster --bastion-host example-bastion --bastion-user example-user
```
## Expected outcomes
Creates report output in `outputs/reports/interface_vlan` by default; device failures may be isolated rather than aborting every target. Inspect workbook for interface/VLAN observations and run/error records. Input or run-level errors print `Interface/VLAN report failed. Check application logs and retained run spool.` Detailed report sheet contract remains in the [main executable reference](../../README.md#batch-interface-and-vlan-report). No device configuration changes.

## Interactive console adapter (Issue #123)

This workflow is also available through `python -m orbitflow.menu`; see the [console manual](interactive-operations-console.md) for environment profile, target workbook selection, per-run concurrency, confirmation and output/recovery behavior. Direct CLI flags and service contracts remain supported. Default `orbitflow.toml` execution loading now prefers validated shared profile pacing when present; explicit alternate config files retain their semantics.

Console target selection (Issue #123 revision): after choosing a device workbook, choose all (blank) or unique comma-separated nonempty device row numbers, counted from 1 after the header. Only selected rows are dispatched; concurrency is still prompted every run. See the [console guide](interactive-operations-console.md) for cancellation and fixed actionable failure diagnostics. Direct CLI input selection is unchanged.

## Full-range VLAN rendering and offline recovery (Issue #142)

The existing `Interfaces`, `VLAN_Database`, and `Run_Errors` sheets and columns
are preserved. In Tagged VLANs and wholly numeric Bridge Domains lists,
consecutive canonical IDs in 1–4094 are rendered as inclusive `a-b` ranges
(runs of at least three). Ordering and duplicate IDs are preserved; numeric
runs are never sorted or merged across intervening values. Mixed named domain
lists remain literal. `ALL`, `NONE`, and blank remain distinct.

Service Mappings uses `identity(a-b)` **only** for consecutive exact pairs:
`identity(2-4094)` expands to `2 -> 2; 3 -> 3; ...; 4094 -> 4094`.
This is a pairwise identity range. Other mappings (including nonidentity,
named services, inner-tag expressions and untagged mappings) remain literal.
For the IOS trunk allowed VLANs `2-4094`, native VLAN `445`, the report shows:

- Untagged VLAN: `445`
- Tagged VLANs: `2-4094`
- Bridge Domains: `445, 2-444, 446-4094`
- Service Mappings: `untagged -> 445; identity(2-4094)`

These are presentation rules over normalized capability data; they do not
change the observation, infer new relationships, or remove the native VLAN
from a normalized tagged list. Expand ranges in order to recover the exact
original lists and identity pairs. Existing normalization rules, including
omission of VLAN 1, are unchanged.

A completed retained spool, including an older spool with expanded strings and
status `output_failed`, can regenerate without Teleport, credentials or device
connections. Run from the repository root, replacing `RUN_ID` with the actual
retained run directory name. Linux:

```bash
export PYTHONPATH=src
python -c "from orbitflow.reporting import export_report_spool; print(export_report_spool('outputs/runs/interface_vlan_report/RUN_ID', 'outputs/reports/interface_vlan/recovered.xlsx', cleanup=False))"
```

Windows PowerShell:

```powershell
$env:PYTHONPATH = 'src'
python -c "from orbitflow.reporting import export_report_spool; print(export_report_spool('outputs/runs/interface_vlan_report/RUN_ID', 'outputs/reports/interface_vlan/recovered.xlsx', cleanup=False))"
```

Public API: `export_report_spool(spool_path, path, *, cleanup=True,
allow_partial=False) -> pathlib.Path`. Paths accept strings or Path objects.
Default `cleanup=True` removes the spool after successful output; use
`cleanup=False` while validating recovery. Default `allow_partial=False`
requires completed collection. `allow_partial=True` explicitly permits an
incomplete collection and retains its spool. Regeneration streams one outcome
at a time and preserves failed-outcome rows in `Run_Errors`.
The interactive console's existing report recovery action uses this same export
path; no new menu action is required.

Compaction also applies during export of older rows. Any remaining cell over
32,767 characters raises `ValueError` identifying sheet, row, column letter and
character count, without exposing its contents. Nothing is silently truncated;
the spool is retained and any existing destination workbook is preserved. Such
fields require investigation using the protected local spool before retrying.

## Validation commands

Linux automated tests:

```bash
PYTHONPATH=src python -m pytest -q tests/test_device_reporting.py tests/test_vlan_capability.py tests/test_result_spool.py tests/test_production_paths.py
```

Windows PowerShell automated tests:

```powershell
$env:PYTHONPATH = 'src'
python -m pytest -q tests/test_device_reporting.py tests/test_vlan_capability.py tests/test_result_spool.py tests/test_production_paths.py
```

For offline validation, run the recovery command above, inspect the three sheets,
expand the compact ranges, and compare against the retained local spool. For the
owner's 699-outcome case, confirm all 699 outcomes remain accounted for and the
seven failed outcomes retain their error records; partial capability failures
may also retain interface rows. Confirm native VLAN 445 and every service pair
on the affected trunk.

For live read-only validation, use the Linux or Windows collection command in
**Examples** above with operator-approved targets and actual routing options.
Inspect the same fields and error records. This issue's automated fixtures are
synthetic; owner spool recovery, Windows execution and live-device validation
remain operator-controlled and are not claimed as performed.
