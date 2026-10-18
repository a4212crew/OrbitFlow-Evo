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
