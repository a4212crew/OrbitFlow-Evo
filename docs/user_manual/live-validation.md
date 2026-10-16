# Live validation utilities — operator manual

These utilities are **read-only on network devices** but may update local inventory snapshots. They are validation helpers, not production configuration apply. Source entry points: `scripts/live_validate_inventory.py`, `scripts/live_validate_inventory_batch.py`, `scripts/live_validate_vlans.py` and `scripts/live_validate_interfaces.py`.

## Script modes and inputs

| Entry point | Required inputs and defaults | Expected result |
|---|---|---|
| `python scripts/live_validate_inventory.py` | No command-line arguments. Uses target, identity and Teleport constants defined in the script; interactively prompts for a device password. | Prints device context and inventory state before/after, writes snapshot to configured local inventory path |
| `python scripts/live_validate_inventory_batch.py TARGETS.xlsx` | Required Excel targets positional argument; fixed in-script Teleport defaults and snapshot paths. | Prints per-target successes/failures, totals, results JSON and log path; default results path `data/live_validation/inventory_validation_results.json` |
| `python scripts/live_validate_vlans.py` | No command-line arguments; in-script connection constants; interactive password. | Prints VLAN/service objects and interface VLAN observations |
| `scripts/live_validate_interfaces.py` | Exposes Python `run_live_validation(device_host, platform, credentials, transport_config, *, device_name=None, inventory_path=Path("data/live_validation/inventory.json"), output=sys.stdout)`. **No standalone CLI main**. | Returns interface records and prints the observed interface list |

## Scenarios

After reviewing and adjusting source-local target configuration for the one-device scripts, Linux:
```bash
python scripts/live_validate_inventory.py
python scripts/live_validate_vlans.py
python scripts/live_validate_inventory_batch.py outputs/devices.xlsx
```

Windows PowerShell with an authenticated compatible Teleport profile:
```powershell
python scripts/live_validate_inventory.py
python scripts/live_validate_vlans.py
python scripts/live_validate_inventory_batch.py .\outputs\devices.xlsx
```

These scripts **do not take** the `--proxy`, `--cluster`, `--bastion-host` or `--bastion-user` switches used by production batch scripts; connection values are defined in their source. Verify and customize these values before running. Interface validation is a library-style helper and should be invoked through a caller that provides credentials and transport configuration.

**Expected failures:** incorrect static target identity, expired Teleport session, invalid Excel target or missing device credentials may prevent connection. Batch results retain per-target classifications; never treat a successful script exit as proof that every target passed. No device configuration is applied. Refer to the [main operator setup](../../README.md).
