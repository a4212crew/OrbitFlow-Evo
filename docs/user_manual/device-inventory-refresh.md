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

## Interactive console adapter (Issue #123)

This workflow is also available through `python -m orbitflow.menu`; see the [console manual](interactive-operations-console.md) for environment profile, target workbook selection, per-run concurrency, confirmation and output/recovery behavior. Direct CLI flags and service contracts remain supported. Default `orbitflow.toml` execution loading now prefers validated shared profile pacing when present; explicit alternate config files retain their semantics.

Console target selection (Issue #123 revision): after choosing a device workbook, choose all (blank) or unique comma-separated nonempty device row numbers, counted from 1 after the header. Only selected rows are dispatched; concurrency is still prompted every run. See the [console guide](interactive-operations-console.md) for cancellation and fixed actionable failure diagnostics. Direct CLI input selection is unchanged.

Python API: `orbitflow.inventory_refresh.refresh_inventory_from_excel(..., target_positions=None)` additionally accepts a nonempty iterable of unique zero-based loaded device row positions. Positions must be integers in range (booleans rejected); invalid selections raise `ValueError` before connecting. Selected rows run in workbook order through shared execution. Omitted stored devices retain the existing not-requested export semantics. The default `None` preserves whole-workbook refresh.

## Shared progress presentation (Issue #144)

See [CLI progress and durable results](cli-progress.md) for interactive and redirected
output, phase-specific counters, saved paths, partial/interrupted/export-failure
semantics and the coverage table (including specialist/lifecycle exemptions).
Device/workflow semantics and existing arguments are unchanged. Deterministic
terminal fixtures are separate from pending owner-operated Linux/Windows validation.


### Fresh collection and retained evidence (2026-10-31)

Continue using the existing Excel inputs, columns and selections. Every normal
collection execution contacts its requested devices again in a distinct run;
prior observations do not repair a failed current collection. Inventory exports
retain explicitly labelled latest-known stable facts after failure. Deliberate
offline export/recovery uses only the selected historical run, without reconnecting;
planning binding, age, trust and authorization restrictions still apply.
See the [audit and owner validation steps](../operations/issue-162-processing-audit.md#fresh-collection-contract-revision-2026-10-31).
