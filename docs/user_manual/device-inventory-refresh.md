# Device inventory refresh — operator manual

**Script:** `scripts/device_inventory_refresh.py`. **Purpose:** refresh device inventory from an approved Excel target list and export an inventory workbook. Read-only device collection; writes local inventory and report artifacts.

## Prerequisites and safety
Run from the repository root with Python 3.11+, installed `requirements.txt`, `PYTHONPATH=src` if required, and an authenticated `tsh` profile. The input workbook contains approved device targets; credential material must not be committed. Provide all four required Teleport routing options: `--proxy`, `--cluster`, `--bastion-host`, `--bastion-user` (strings). Linux Teleport key/certificate file paths may be required; supply `--teleport-key-path` and `--teleport-cert-path` (optional paths, default unset). No script here performs configuration apply.

## Inputs and defaults
Required positional `excel_path` (Excel filename); required Teleport routing strings as above. Optional paths: `--inventory-path` (`data/inventory/inventory.json`), `--reports-dir` (`outputs/reports/inventory`), `--spool-root` (`outputs/runs/inventory_refresh`), `--log-root` (`outputs/logs`), `--config` (`orbitflow.toml`), and optional key/cert paths (unset). File paths are relative to working directory unless absolute.

## Examples
Linux:
```bash
python scripts/device_inventory_refresh.py outputs/devices.xlsx --proxy teleport.example.net:443 --cluster example-cluster --bastion-host example-bastion --bastion-user example-user --teleport-key-path "$TELEPORT_KEY_PATH" --teleport-cert-path "$TELEPORT_CERT_PATH"
```
Windows PowerShell (using an already authenticated Teleport profile):
```powershell
python scripts/device_inventory_refresh.py .\outputs\devices.xlsx --proxy teleport.example.net:443 --cluster example-cluster --bastion-host example-bastion --bastion-user example-user
```
## Expected outcomes and troubleshooting
Successful runs update the configured inventory JSON and create a uniquely named `inventory_<UTC timestamp>_<UUID>.xlsx` in the reports directory. Terminal prints `Inventory refresh started.` and `Inventory workbook saved in the configured reports directory. Review Run_Attempts for target failures.` Review the workbook `Run_Attempts` sheet for per-target failures. Missing/bad input, transport failures or output-path problems can produce a sanitized `Inventory refresh/export failed` message; inspect application/inventory logs and retained spool. Device changes are not performed. See [repository setup](../../README.md).
