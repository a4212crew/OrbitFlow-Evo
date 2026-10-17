# VLAN compliance — operator manual

**Script:** `scripts/device_vlan_compliance.py`. **Purpose:** collect and evaluate read-only VLAN/interface compliance; optionally regenerate reports from an existing spool without new connections.

## Prerequisites and safety
Run from the repository root with Python 3.11+, installed `requirements.txt`, `PYTHONPATH=src` if required, and an authenticated `tsh` profile. The input workbook contains approved device targets; credential material must not be committed. Provide all four required Teleport routing options: `--proxy`, `--cluster`, `--bastion-host`, `--bastion-user` (strings). Linux Teleport key/certificate file paths may be required; supply `--teleport-key-path` and `--teleport-cert-path` (optional paths, default unset). No script here performs configuration apply.

## Commands and inputs
**`run`:** positional `excel_path` (path), four required Teleport routing strings, optional key/cert paths (unset). Optional paths `--policy` (the application's `DEFAULT_POLICY`), `--config` (`orbitflow.toml`), `--inventory-path` (`data/inventory/inventory.json`), `--reports-dir` (`outputs/reports/vlan_compliance`), `--spool-root` (`outputs/runs/vlan_compliance`), `--log-root` (`outputs/logs`). Boolean flags `--keep-spool` (default false) and `--methodology-report` (default false).

**`export`:** required positional `spool_path` and `output_path` (paths). Optional `--log-root` (`outputs/logs`), `--keep-spool` (false), `--allow-partial` (false), `--methodology-report` (false). `export` does not require Teleport access.

## Examples and expected results
Linux collection:
```bash
python scripts/device_vlan_compliance.py run outputs/devices.xlsx --proxy teleport.example.net:443 --cluster example-cluster --bastion-host example-bastion --bastion-user example-user --teleport-key-path "$TELEPORT_KEY_PATH" --teleport-cert-path "$TELEPORT_CERT_PATH" --keep-spool
```
Produces a compliance workbook under the reports directory; terminal prints `Compliance workbook saved. Review Findings and Run_Errors.`

Windows PowerShell offline re-export:
```powershell
python scripts/device_vlan_compliance.py export .\outputs\runs\vlan_compliance\<retained-spool> .\outputs\reports\vlan_compliance\review.xlsx --allow-partial --keep-spool
```
Produces an Excel workbook from retained data, without connecting to network devices. For a separate methodology workbook, add `--methodology-report`; terminal prints `Workbook saved. Review methodology results and Run Errors.` Partial export requires explicit `--allow-partial`. An invalid spool/policy/input reports sanitized `VLAN compliance failed`; inspect logs and retained run spool. **No configuration apply.**

## Interactive console adapter (Issue #123)

This workflow is also available through `python -m orbitflow.menu`; see the [console manual](interactive-operations-console.md) for environment profile, target workbook selection, per-run concurrency, confirmation and output/recovery behavior. Direct CLI flags and service contracts remain supported. Default `orbitflow.toml` execution loading now prefers validated shared profile pacing when present; explicit alternate config files retain their semantics.

Console target selection (Issue #123 revision): after choosing a device workbook, choose all (blank) or unique comma-separated nonempty device row numbers, counted from 1 after the header. Only selected rows are dispatched; concurrency is still prompted every run. See the [console guide](interactive-operations-console.md) for cancellation and fixed actionable failure diagnostics. Direct CLI input selection is unchanged.
