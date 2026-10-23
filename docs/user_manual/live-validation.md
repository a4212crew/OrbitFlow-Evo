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

## Cisco terminal width (Issue #114)

Shared `DeviceCLI` sessions require `terminal width 511` before their first
Cisco adapter operation or configuration capture. Successful width setup is
cached for that shell across interface/VLAN observation, compliance and v2
planning lookups. Short inventory identity probes retain their existing setup.
Temporary `CiscoIOSCLI` and `CiscoXRCLI` shells require width during construction.
Paging setup remains `terminal length 0`. These are EXEC session settings;
no configuration apply/save is performed.

`DeviceCLI.configure(..., setup_commands=())` accepts an optional tuple of
required setup commands, cached only after a synchronized, accepted response.
Cisco callers supply `("terminal width 511",)`. Rejection raises
`InteractiveCLIError`; timeout raises `InteractiveCLITimeout` and invalidates
the borrowed shell. Standalone Cisco setup raises `CiscoIOSCLIError` or
`CiscoIOSCLITimeout` and closes its channel. Both paths preserve parent transport
ownership. Workflows may wrap these errors or report unavailable evidence.
Do not retry on the failed shell. Diagnostics identify setup without copying
device output. There is no fallback to short interface names or relaxed echoes.

Cisco's independent [IOS-XR terminal services reference](https://www.cisco.com/c/en/us/td/docs/iosxr/asr9000/general-administration/command/b-general-administration-command-ios-xr-asr9000/m-terminal-services-commands.html)
documents EXEC `terminal width`, range 0–512, as session-only. This supports
511 syntactically; it does not prove acceptance on a particular NCS540 release.

Deterministic tests on Linux (from the repository root):

```bash
python -m pytest -q tests/test_cisco_terminal_width.py tests/test_cisco_ios_cli.py tests/test_shared_cli.py tests/test_cli_lifecycle.py
python -m pytest -q
```

The same commands in Windows PowerShell:

```powershell
python -m pytest -q tests/test_cisco_terminal_width.py tests/test_cisco_ios_cli.py tests/test_shared_cli.py tests/test_cli_lifecycle.py
python -m pytest -q
```

Windows execution and all new live-device validation remain owner tasks.
Synthetic CRLF-wrapped echoes demonstrate why exact echo synchronization can
time out; the original device echo bytes were not captured, so this remains a
root-cause hypothesis. Owner-reported manual read-only ME3600X and ASR920 tests
succeeded after width 511; automatic setup has not yet been live-validated.

Owner read-only verification, using an authenticated Teleport profile and
operator-controlled credentials/session creation from the existing Transport
API example in the [README](../../README.md#transport-api):

1. Use a fresh established session and one `DeviceCLI(session)` context. Resolve
   inventory with `DeviceInventoryResolver.resolve(..., cli=cli)`, then call
   `InterfaceService.collect(session, context, cli=cli)` and
   `VlanService.collect(session, context, cli=cli)` on that same shell. Do not
   manually send a width command first.
2. On ME3600X call `VlanService().service_detail(session, context,
   "GigabitEthernet0/24", 545, cli=cli)`; on ASR920 use
   `"TenGigabitEthernet0/0/24"`. Confirm `status == "present"` and
   `operational_status == "up"` where the owner confirms that service is up.
   Repeat the lookup; verify width was initialized once using a sanitized
   command-name trace, without recording raw device output.
3. On C3750X (IOS), C3850 (IOS-XE), and NCS540 (IOS-XR), confirm setup acceptance,
   interface/VLAN normalized results and a subsequent `show clock` response.
   Use the device's actual inventory identity; do not substitute OS labels for
   hardware families. Width acceptance is pending on these three families.
4. Repeat collection without `cli=` to exercise temporary vendor shells.
   Exercise existing read-only compliance, backup and v2 observation/planning
   workflows with operator-approved inputs; verify canonical interface names,
   preserved backup content, and unchanged planning evidence. No apply/save.
5. Record family, software release, OS, accepted/rejected setup, normalized
   result and shell continuity only. A rejection must fail explicitly; a
   timeout must prevent shell reuse. Do not publish credentials, banners or
   raw saved configurations. Report each family's result separately.

The following helper is executable inside an operator's existing Python caller.
Pass a **fresh session before opening any shell**, using the README Transport API
connection block with operator-owned `config` and credentials. It updates only a
local validation inventory and prints normalized status, never raw CLI output:

```python
from pathlib import Path
from orbitflow.capabilities import InterfaceService, VlanService
from orbitflow.inventory import DeviceInventoryResolver, JsonInventoryStore
from orbitflow.vendors.common import DeviceCLI


def verify_cisco_width(session, management_ip):
    resolver = DeviceInventoryResolver(JsonInventoryStore(
        Path("data/inventory/cisco-width-validation.json")))
    with DeviceCLI(session) as cli:
        context = resolver.resolve(session, management_ip=management_ip, cli=cli)
        interfaces = InterfaceService().collect(session, context, cli=cli)
        state = VlanService().collect(session, context, cli=cli)
        print(context.device_family, context.platform, len(interfaces),
              len(state.interfaces), len(state.objects))
        ports = {"ME3600X": "GigabitEthernet0/24",
                 "ASR920": "TenGigabitEthernet0/0/24"}
        if context.device_family in ports:
            for _ in range(2):
                detail = VlanService().service_detail(
                    session, context, ports[context.device_family], 545, cli=cli)
                print(detail["status"], detail.get("operational_status"))
                assert detail["status"] == "present"
                assert detail["operational_status"] == "up"
        assert cli.run_command("show clock").strip()
```

Expected: correct family/OS, nonempty interface records, family-appropriate VLAN
or service counts, present/up for the two owner-confirmed SI 545 targets, and a
synchronized clock reply. A down/missing service needs owner investigation;
do not change the device to satisfy this check. For temporary-shell checks use
fresh connections if the device permits only one shell per SSH connection.

## Shared progress presentation (Issue #144)

See [CLI progress and durable results](cli-progress.md) for interactive and redirected
output, phase-specific counters, saved paths, partial/interrupted/export-failure
semantics and the coverage table (including specialist/lifecycle exemptions).
Device/workflow semantics and existing arguments are unchanged. Deterministic
terminal fixtures are separate from pending owner-operated Linux/Windows validation.
