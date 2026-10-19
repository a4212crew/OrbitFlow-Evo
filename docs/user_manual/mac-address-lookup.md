# MAC Address Lookup

Read-only terminal lookup for Catalyst C3750X/C3850, ME3600X, ASR920, NCS540,
Huawei NE05/NE05E and EdgeSwitch. Implemented sample parsers have offline tests;
owner live collection validation on Linux and Windows remains pending. Huawei
`display mac-address` and EdgeSwitch `show mac-addr-table all` are owner-approved
candidates whose original samples omitted invocation/prompt. No live testing by Codex.

Launch `python -m orbitflow.menu`, choose **7. MAC Address Lookup**, then:

1. **Search MAC Address**: enter dotted or colon MAC (case-insensitive) and device
   IP. Invalid input stops before network access. Choose the existing credential
   workbook; exactly one matching IP row is required (duplicates are ambiguous).
   Confirm network collection. No concurrency prompt. Every match prints one
   cohesive record with observation key, normalized
   MAC, full attachment, group/domain and mapping, physical name or
   unresolved/nonphysical, and evidenced port type. Repeated MACs in different
   domains/ports remain separate records. Match and error counts distinguish
   no-match from failure.
2. **List All MAC Addresses**: enter VLAN 1-4094, select workbook and all or unique
   loaded device row positions, choose concurrency 1-5 (blank=1), then confirm.
   Only proven VLAN matches enter the main sheet. Unknown mappings are explicit
   in Details; inspect Run Errors before treating a partial result as complete.
3. **Back**. Main Exit is now 8. `b` cancels at prompts; declining confirmation
   creates no connection. Concurrency is never saved.

Use the existing non-secret `data/sys_config/configuration-profile.toml` with
Teleport routing, pacing and device/inventory paths. Existing profiles remain
compatible. Device workbook columns are `management_ip`, `username`, `password`,
optional `secret`; no full-estate search fallback. Run `tsh login` externally if
the session expires. Linux requires configured identity/certificate files. Passwords,
OTPs and private key contents must never enter the profile or command arguments.

One timestamp/UUID workbook per run appears in `outputs/reports/mac_table/`.
The main **MAC Addresses** sheet has exactly, in order: Device IP; Device Name;
Equipment Type; Physical Interface name; Port Type; Mac address. Equipment Type
uses observed hardware model, falling back to family. Each observation gets its own
row, including repeated MACs and four separate rows for four entries on one trunk.
**Details** keys observations by target position/IP/source position, with selected per-device row
ordinal, full attachment and separate raw attachment, domain, VLANs, original/normalized type, source scope, destination
detail, mapping/classification, physical identity and forwarding semantics and collection source. **Bridge Domains** preserves XR group/domain/internal ID, AC/PW attachment states, backup flags and counts, keyed by device and domain. **Totals**
separates table, local selection and supplied slot scopes. **Run Errors** contains
device/stage/category only. Cells are literal text, headers frozen and filterable.
Blank physical names and Unknown port type are deliberate when evidence is absent.

Normalized run spools remain under `outputs/runs/mac_table/`; sanitized module
logs under `outputs/logs/mac_table/YYYY-MM-DD/`. Export failure retains collected
data. The direct CLI can regenerate without reconnecting; recovery is intentionally
not a third menu action.

On Windows PowerShell, from the repository:

```powershell
$env:PYTHONPATH = (Resolve-Path src).Path
python -m orbitflow.menu --help
python -m orbitflow.mac_cli --help
python -m orbitflow.mac_cli search --mac aabb.ccdd.eeff --ip 192.0.2.1 --confirm
python -m orbitflow.mac_cli list --vlan 445 --rows 1,2 --concurrency 2 --confirm
python -m orbitflow.mac_cli export outputs/runs/mac_table/RUN outputs/reports/mac_table/recovered.xlsx
```

Linux equivalents (operator live execution pending):

```bash
export PYTHONPATH="$PWD/src"
python -m orbitflow.menu --help
python -m orbitflow.mac_cli --help
python -m orbitflow.mac_cli search --mac aabb.ccdd.eeff --ip 192.0.2.1 --confirm
python -m orbitflow.mac_cli list --vlan 445 --rows 1,2 --concurrency 2 --confirm
python -m orbitflow.mac_cli export outputs/runs/mac_table/RUN outputs/reports/mac_table/recovered.xlsx
```

These documentation IPs are examples. Network commands require separately approved
operator-controlled targets. CLI `search` requires --mac/--ip; `list` requires
--vlan, defaults all rows and concurrency=1. Both accept --profile (default above),
--devices (profile workbook by default), --xr-location (default 0/RP0/CPU0), and
require --confirm. XR location is validated; no alternate nodes are guessed.
`export` takes spool/output positional paths, optional --allow-partial; no profile
or Teleport session is needed. Invalid input fails before connection; CLI prints a
fixed failure diagnostic on recognized application errors. Network CLI prints the
report path; inspect all supporting sheets for status, even when main is empty.

Approved device commands (run once per device via shared session):

| Family | MAC command |
|---|---|
| C3750X/C3850/ME3600X/ASR920 | `show mac address-table` |
| NCS540 | `show l2vpn forwarding bridge-domain mac-address location 0/RP0/CPU0` (configurable node via API/CLI) |
| Huawei | `display mac-address` (invocation pending owner validation) |
| EdgeSwitch | `show mac-addr-table all` (invocation pending owner validation) |

XR enrichment uses `show l2vpn bridge-domain`; other enrichment reuses existing
InterfaceService and VlanService commands/session setup. Full-table collection plus
local filtering avoids ME parent-table omissions. Never execute resynchronization
advice or follow remote peers. Available MAC address space is never learned total.

Known limits: supplied samples are excerpts, not complete release coverage. Exact
EFP mapping needs preserved service facts. Unknown service relationships cannot
match VLANs. Parents absent from both observed and configured interface facts cannot resolve physically. Aggregate entries retain
aggregate ownership; EdgeSwitch `3/N` maps exactly to `lag N`, and management
`5/1` stays nonphysical. Explicit trunk-only configuration preserves port intent
with no inferred VLAN membership. ME3600X/ASR920 use shared validated access,
EVC/trunk, hybrid and review classifications. XR untagged ACs associate only when
a unique operational/configured group/domain has one distinct explicit numeric
peer dot1q VLAN; this association does not imply tagged ingress. Existing shared
VLAN normalization omits VLAN 1 in some service profiles; no audit-policy change
is made here. Very large single-device tables remain in per-device memory and
Excel's sheet/cell limits apply; select narrower runs if a sheet would exceed its row limit. Export errors retain the spool. No claim of
live completeness or performance is made.

Offline validation (Issue #132 automated tests run on Linux; Windows execution pending):

```powershell
python -m pytest tests/test_mac_lookup.py tests/test_operations_console.py -q
python -m pytest -q
```

Owner read-only validation, still pending: authenticate externally, use an authorized
lab workbook, first cancel each action, then test match/no-match and missing/duplicate
IP, each family, VLAN != BD/EFP/suffix, CPU/remote/aggregate entries, expired session,
optional enrichment failure, list subset and concurrency 1/5, and offline export.
Compare only observed identities/relationships and supplied total fields; do not add
count mismatch warnings. Check port mode against independent shared observations.
Do not use production credentials in reports supplied for review.

See [API](../operations/mac-address-lookup-api.md) and
[architecture](../architecture/mac-address-lookup.md).

Revision validation scenarios (owner execution remains pending on both OSes):

```powershell
$env:PYTHONPATH = "src"
python -m orbitflow.menu
python -m orbitflow.mac_cli search --mac aabb.ccdd.eeff --ip 192.0.2.1 --confirm
python -m orbitflow.mac_cli list --vlan 860 --rows 1 --concurrency 1 --confirm
```

```bash
export PYTHONPATH=src
python -m orbitflow.menu
python -m orbitflow.mac_cli search --mac aabb.ccdd.eeff --ip 192.0.2.1 --confirm
python -m orbitflow.mac_cli list --vlan 860 --rows 1 --concurrency 1 --confirm
```

Replace example IP/MAC/VLAN with authorized lab targets and known observations.
In menu Search, verify a multi-hit MAC shows its own attachment/domain/physical
port/type on each keyed line. In List, choose an encapsulation VLAN different
from EFP/BD/subinterface suffix; those identifiers alone must never match.
For NCS, compare Details group/domain with the exact configured binding and
Bridge Domains evidence. Contradictory groups with identical domain names must
remain unknown and absent from the VLAN selection. Summary counts and up counts
are reported facts, including empty domains; they are never compared or recomputed.
No new command or live data is required for the deterministic revision tests.


Issue #132 offline verification (no credentials or network access):

```bash
export PYTHONPATH="$PWD/src"
python -m pytest tests/test_mac_lookup.py tests/test_vlan_configuration_audit.py tests/test_vlan_capability.py tests/test_vlan_compliance.py -q
python -m pytest -q
```

```powershell
$env:PYTHONPATH = (Resolve-Path src).Path
python -m pytest tests/test_mac_lookup.py tests/test_vlan_configuration_audit.py tests/test_vlan_capability.py tests/test_vlan_compliance.py -q
python -m pytest -q
```

For pending operator read-only verification, use the Bash/PowerShell search/list
and offline export commands above with authorized lab inputs. Include EdgeSwitch
3/1, 3/2 and 3/5, management 5/1, EFP encapsulation different from SI/BD, CPU/PW,
SVI/Port-channel and an XR untagged AC with zero/one/multiple peer tags. Verify
six main columns, one row per source observation, exact filters, Details evidence,
Totals, Run Errors, Bridge Domains and recovery export. Missing/ambiguous evidence
must stay Unknown; run partial/failure scenarios before accepting completeness.
Automated fixtures do not establish live-device or Windows validation.
