# OrbitFlow-Evo — Configuration Template Workbook Engineer Guide

**Scope:** Configuration Planning v2 · Catalogue 2.3 · Linux Bash and Windows PowerShell  
**Documentation status:** Operator guide for current implemented planning behaviour; deterministic/source-reviewed examples are not proof of hardware validation.  
**Safety:** Planning and review only — **never executes device configuration, save, commit, rollback, or deployment**.

## 1. Purpose and workflow

This guide walks network engineers through the **Excel configuration template**: choose a device-family worksheet; enter parameters starting at row 3; run the read-only planner; inspect existing evidence, proposed CLI, warnings and blockers; and record an offline Pending/Approve/Reject decision. The 21 predefined templates collect device evidence through shared read-only connectivity. **Manual CLI does not connect** and does not validate command meaning or device impact. Offline approval is not execution authorization.

The canonical [bulk planning manual](bulk-configuration-planning.md) lists every v2 CLI option and environment configuration. The [technical template reference](../operations/configuration-template-reference.md) contains the authoritative detailed field matrices and evidence rules. The corresponding [approved Catalyst](../architecture/configuration/approved-catalyst-templates.md) and [approved ME/ASR/EdgeSwitch](../architecture/configuration/approved-me3600x-asr920-edgeswitch-templates.md) contracts govern Templates 1–16; **17–22 are provisional catalogue behaviours without owner sign-off or live validation**. Retire the old v1 user guide separately; the v1 Python entry point continues to exist.

### Complete workflow

1. Activate the OrbitFlow virtual environment, set `PYTHONPATH=src`, and authenticate with Teleport where read-only collection is needed.
2. Generate `bulk-input.xlsx` with the `input` command.
3. Open **Introduction** to navigate to the appropriate vendor worksheet. Read worksheet A1/header comments and enter requests **from row 3**. A worksheet may contain many requests; different worksheets may target the same or different devices.
4. Supply credentials **only** in a separate protected `devices.xlsx`; the planning workbook contains only the management IP and configuration inputs.
5. Run `plan` to collect read-only evidence, validate each row, generate proposed CLI, and write `plan.json` and `plan.xlsx`.
6. Compare the evidence and proposed commands with independently known device state; resolve errors, conflicts, dependency warnings or stale evidence by correcting the original input/re-observing and generating **new** plan artifacts.
7. Edit **only Engineer Decision** cells in the generated **plan.xlsx** to Pending, Approve or Reject. A decision does not apply configuration, provide authenticated approval, or override unresolved safety blockers.

### Input workbook rules

- The template workbook has an Introduction directory and 22 worksheets. Row 2 holds the column headers; **data begins at row 3**.
- Use the exact vendor worksheet, not a generic sheet. `management_ip` is required on every request. Match addresses to the separate device credentials workbook for predefined templates.
- Required fields may not be empty. Optional blank fields have template-specific meaning — often *preserve the parent/interface description*, but blank optional **EVC child** fields are omitted on complete service-instance recreation.
- Enter VLAN IDs as integers where a single VLAN field is required. Lists/ranges are allowed **only** for the fields and syntax explicitly documented below. Use full canonical names for Catalyst interfaces.
- Requests for the same device are evaluated **worksheet left-to-right and row top-to-bottom**. Earlier requests can create projected prerequisites, but a Pending or rejected prerequisite does not make a dependent change deployment-ready.
- No passwords, OTPs, tokens, URLs, formulas or secret-bearing commands/text are allowed in template inputs. Use sanitized example addresses from `192.0.2.0/24` rather than real targets in published documentation.

## 2. Prerequisites and executable commands

From the repository root with Python 3.11+ and project dependencies installed:

**Linux (Bash):**

```bash
cd ~/Projects/OrbitFlow-Evo
source .venv/bin/activate
export PYTHONPATH="$PWD/src"
python -m orbitflow.configuration.v2.cli --help
python -m orbitflow.configuration.v2.cli input bulk-input.xlsx
# Edit input workbook; put predefined template rows at row 3 or later.
python -m orbitflow.configuration.v2.cli plan bulk-input.xlsx \
  --devices "$HOME/secure/devices.xlsx" \
  --proxy "TELEPORT_PROXY:443" --cluster "TELEPORT_CLUSTER" \
  --bastion-host "BASTION_HOST" --bastion-user "BASTION_USER" \
  --teleport-key-path "$TELEPORT_KEY_PATH" \
  --teleport-cert-path "$TELEPORT_CERT_PATH" \
  --max-concurrent-devices 1
```

**Windows (PowerShell):**

```powershell
cd C:\Path\To\OrbitFlow-Evo
.\.venv\Scripts\Activate.ps1
$env:PYTHONPATH = (Join-Path (Get-Location) "src")
python -m orbitflow.configuration.v2.cli --help
python -m orbitflow.configuration.v2.cli input bulk-input.xlsx
# Edit input workbook; put predefined template rows at row 3 or later.
python -m orbitflow.configuration.v2.cli plan bulk-input.xlsx `
  --devices "C:\Operator\devices.xlsx" `
  --proxy "TELEPORT_PROXY:443" --cluster "TELEPORT_CLUSTER" `
  --bastion-host "BASTION_HOST" --bastion-user "BASTION_USER" `
  --max-concurrent-devices 1
```

**Manual CLI only** (all request rows in Manual CLI, no predefined rows): `python -m orbitflow.configuration.v2.cli plan manual-only.xlsx` — neither devices workbook nor Teleport flags are used. The CLI has **two** v2 commands, `input PATH` and `plan WORKBOOK [OUTPUT.json]`. View `input --help` and `plan --help` for the exact set of flags; common additional plan options: `--inventory-path` (default `data/inventory/inventory.json`), `--config` (default `orbitflow.toml`), `--devices` (default `devices.xlsx`), and optional `--max-concurrent-devices`. There is **no** v2 CLI `approve`, `apply`, `execute`, `review` or `--timeout` flag.

### Output files and expected result

If no explicit destination is given, a fresh `outputs/reports/configuration/<timestamp>_<target>/` directory contains:

- **`plan.json`:** Immutable digest-bound plan with original inputs, sanitized observations, projected states, proposed CLI, dependencies and integrity metadata. This is the authoritative untruncated record.
- **`plan.xlsx`:** Excel review with inputs, **Existing Evidence**, **Proposed CLI**, **Live Validation**, **Consistency**, **Dependencies**, **No-op**, **Validation Status**, **Error Details**, **Warnings**, **Blockers** and **Engineer Decision**. An **Introduction** sheet and, when needed, **Evidence Details** provide navigation and source excerpts. For Templates 1–16, certain internal fields stay only in JSON.
- **Logs:** `outputs/logs/configuration/YYYY-MM-DD/bulk_planning.log`; observation spools under `outputs/runs/configuration_observation/`; transport diagnostics in transport logs.

Successful output prints the plan digest with an **offline review only** notice. The CLI exits with error category and code 2 on fatal planning/export errors; individual invalid rows remain visible with errors and no proposed CLI while safe peers can continue. Existing output file paths are not overwritten.

## 3. Template selection guide

| # | Excel worksheet | Typical purpose | Approval scope |
|---|---|---|---|
| 1 | [C3750X VLAN Database](#template-1--c3750x-vlan-database) | Create/rename global VLAN | Signed-off contract; hardware validation pending |
| 2 | [C3750X Access Port](#template-2--c3750x-access-port) | Plan single access VLAN | Signed-off contract; hardware validation pending |
| 3 | [C3750X Trunk Port](#template-3--c3750x-trunk-port) | Plan trunk VLAN membership | Signed-off contract; hardware validation pending |
| 4 | [C3750X Description](#template-4--c3750x-description) | Change an interface description | Signed-off contract; hardware validation pending |
| 5 | [C3850X VLAN Database](#template-5--c3850x-vlan-database) | Create/rename global VLAN | Signed-off contract; hardware validation pending |
| 6 | [C3850X Access Port](#template-6--c3850x-access-port) | Plan single access VLAN | Signed-off contract; hardware validation pending |
| 7 | [C3850X Trunk Port](#template-7--c3850x-trunk-port) | Plan trunk VLAN membership | Signed-off contract; hardware validation pending |
| 8 | [C3850X Description](#template-8--c3850x-description) | Change an interface description | Signed-off contract; hardware validation pending |
| 9 | [ME3600X VLAN Database](#template-9--me3600x-vlan-database) | Create/rename global VLAN | Signed-off contract; hardware validation pending |
| 10 | [ME3600X EVC](#template-10--me3600x-evc) | Recreate service instance with encapsulation and BD | Signed-off contract; hardware validation pending |
| 11 | [ME3600X Description](#template-11--me3600x-description) | Change an interface description | Signed-off contract; hardware validation pending |
| 12 | [ASR920 EVC](#template-12--asr920-evc) | Recreate service instance with encapsulation and BD | Signed-off contract; hardware validation pending |
| 13 | [ASR920 Description](#template-13--asr920-description) | Change an interface description | Signed-off contract; hardware validation pending |
| 14 | [EdgeSwitch VLAN Database](#template-14--edgeswitch-vlan-database) | Create/rename global VLAN | Signed-off contract; hardware validation pending |
| 15 | [EdgeSwitch VLAN Port](#template-15--edgeswitch-vlan-port) | Change EdgeSwitch port VLAN/PVID | Signed-off contract; hardware validation pending |
| 16 | [EdgeSwitch Description](#template-16--edgeswitch-description) | Change an interface description | Signed-off contract; hardware validation pending |
| 17 | [NCS540 L2VPN](#template-17--ncs540-l2vpn) | Plan XR L2 transport attachment | Provisional; not signed off |
| 18 | [NCS540 Description](#template-18--ncs540-description) | Change an interface description | Provisional; not signed off |
| 19 | [NE05E VLAN Database](#template-19--ne05e-vlan-database) | Create/rename global VLAN | Provisional; not signed off |
| 20 | [NE05E Subinterface VSI](#template-20--ne05e-subinterface-vsi) | Plan Huawei VSI binding | Provisional; not signed off |
| 21 | [NE05E Description](#template-21--ne05e-description) | Change an interface description | Provisional; not signed off |
| 22 | [Manual CLI](#template-22--manual-cli) | Free-form offline CLI | Provisional; not signed off |

## 4. Individual template procedures

**How to use the template sections:** Each section below supplies the exact worksheet input column contract, worked inputs, expected generated CLI or no-op/blockers, evidence requirements, special dependencies and validation scope. For every template use **the same** `input` and `plan` commands from Section 2; template names are **worksheet choices, not separate CLI subcommands**. The expected CLI examples depend on the *stated observed device state* and must not be pasted into devices as an OrbitFlow command.

### Template 1 — C3750X VLAN Database

Status: signed-off detailed contract; deterministic validation only, owner live validation pending.

| Input column | Requirement | Allowed values / forbidden values / example |
|---|---|---|
| `management_ip` | Required | IPv4/IPv6 literal; e.g. 192.0.2.91. No hostname, credentials or URL. |
| `vlan_id` | Required | One integer VLAN ID; family bounds below. No list/range, ALL, 0 or 4095. |
| `name` | Required | Family-specific VLAN name limits below; no empty name, quotes, semicolon or backslash. |

Bounds: 1–4094 excluding 1002–1005; names =32 ASCII [A-Za-z0-9_.:-], no spaces. VLAN 445,545 or 200-100 in vlan_id is invalid. Empty/overlong names block; Customer Site is invalid on Cisco, valid on EdgeSwitch/NE05E within length bounds.

| Filled input (plus management_ip) and observed state | Expected result |
|---|---|
| vlan_id=901; name=Customer; absent global VLAN | `configure terminal / vlan 901 / name Customer / end` |
| vlan_id=901; name=Customer; existing name Customer | No-op, empty CLI |
| vlan_id=901; name=Customer; existing name Old | Rename with VLAN_RENAME_IMPACT; same CLI, no deletion |
| vlan_id=1002; name=Customer | Invalid input, no CLI |
| vlan_id=901; name=Customer; unknown evidence | Blocked; never infer absent |

Evidence: full reliable running-config global VLAN declaration/list/name plus `show vlan id 901`. Explicit absence creates; operational failure/inconclusive output falls back only to complete config, annotated VLAN_LOOKUP_FALLBACK. Conflicting reliable names/existence block. Inactive/down is informational. An empty reliably collected database proves absence. Interface membership and service references do not establish global existence. Earlier approved creation supplies prerequisites to later ME EVC; conflicting same-ID requests block and cite rows. EdgeSwitch port membership never requires global creation. No interface command is emitted here.

**Engineer operating procedure for C3750X VLAN Database:**

1. In `bulk-input.xlsx`, select the **C3750X VLAN Database** worksheet, populate the exact fields shown above from row 3 (or later), and keep the credential workbook separate.
2. Run the **same v2 `plan` command** from Section 2. For predefined templates verify that live read-only collection identified the intended device, target object and current state; for Manual CLI no connection is performed.
3. Open the **C3750X VLAN Database** tab in generated `plan.xlsx`. Inspect the original entered values, Existing Evidence (if applicable), Proposed CLI, Live Validation, Consistency, Dependencies, No-op, Warnings, Blockers and Engineer Decision; compare the worked examples above against the actual evidence.
4. If invalid or blocked, repair the **input** or missing prerequisites/evidence and regenerate a fresh plan; do not edit the generated CLI/evidence. Record Pending/Approve/Reject only after review; no decision deploys the proposal.

**Approval:** Signed-off detailed contract; deterministic validation only. Hardware/software live validation remains owner-controlled.


### Template 2 — C3750X Access Port

Status: signed-off detailed contract; deterministic validation only, owner live validation pending.

| Input column | Requirement | Allowed values / forbidden values / example |
|---|---|---|
| `management_ip` | Required | IPv4/IPv6 literal; e.g. 192.0.2.91. No hostname, credentials or URL. |
| `interface` | Required | Existing explicit interface identifier; platform details and sample below. No whitespace except EdgeSwitch lag N; no shell metacharacters. |
| `vlan_id` | Required | One integer VLAN ID; family bounds below. No list/range, ALL, 0 or 4095. |
| `description` | Optional | Printable ASCII text with spaces/case, e.g. Customer Site Alpha; no secrets, quotes, semicolon or backslash. Blank optional preserves existing description. |

Interface: full canonical Cisco name, e.g. GigabitEthernet1/0/1; no abbreviated Gi names. vlan_id: one integer 1–4094 excluding 1002–1005. Optional description preserves blank; input has no action/native VLAN.

| Filled input (plus management_ip) and observed state | Expected result |
|---|---|
| interface=GigabitEthernet1/0/1; vlan_id=445; description=Customer; empty/dynamic/access different | `configure terminal / interface GigabitEthernet1/0/1 / description Customer / switchport / switchport mode access / switchport access vlan 445 / end` |
| same interface; vlan_id=445; description blank; explicit access VLAN already 445 | No-op; existing description preserved |
| vlan_id=445; missing global VLAN | Nonblocking GLOBAL_VLAN_REQUIRED; proposed access CLI, no auto-create |
| same input after earlier Pending/Reject database prerequisite | Dependency not approved; cannot claim readiness |
| same input on configured trunk or routed no switchport | Show proposal; ACCESS_CONVERSION_BLOCKED |
| same input on channel-group member | PHYSICAL_PORT_CHANNEL_MEMBER; no redirection |
| vlan_id=1002 or interface=Gi1/0/1 | Invalid, no CLI |

Evidence: full physical stanza and logical Port-channel evidence where owned; approved show vlan id lookup/config fallback for target VLAN. Explicit access mode wins over residual trunk statements, which warn. Access VLAN without explicit mode/empty/dynamic mode warns; inferred default VLAN alone is not a complete match. Shutdown retained. Earlier Access then Description is compatible, warns both rows, final description wins. Access versus Trunk on same effective resource blocks. Unknown syntax/owner/evidence is never waived by a No-op.

**Engineer operating procedure for C3750X Access Port:**

1. In `bulk-input.xlsx`, select the **C3750X Access Port** worksheet, populate the exact fields shown above from row 3 (or later), and keep the credential workbook separate.
2. Run the **same v2 `plan` command** from Section 2. For predefined templates verify that live read-only collection identified the intended device, target object and current state; for Manual CLI no connection is performed.
3. Open the **C3750X Access Port** tab in generated `plan.xlsx`. Inspect the original entered values, Existing Evidence (if applicable), Proposed CLI, Live Validation, Consistency, Dependencies, No-op, Warnings, Blockers and Engineer Decision; compare the worked examples above against the actual evidence.
4. If invalid or blocked, repair the **input** or missing prerequisites/evidence and regenerate a fresh plan; do not edit the generated CLI/evidence. Record Pending/Approve/Reject only after review; no decision deploys the proposal.

**Approval:** Signed-off detailed contract; deterministic validation only. Hardware/software live validation remains owner-controlled.


### Template 3 — C3750X Trunk Port

Status: signed-off detailed contract; deterministic validation only, owner live validation pending.

| Input column | Requirement | Allowed values / forbidden values / example |
|---|---|---|
| `management_ip` | Required | IPv4/IPv6 literal; e.g. 192.0.2.91. No hostname, credentials or URL. |
| `interface` | Required | Existing explicit interface identifier; platform details and sample below. No whitespace except EdgeSwitch lag N; no shell metacharacters. |
| `action` | Required | Exact family-specific selection below; no lowercase aliases. |
| `vlans` | Required | Comma-separated integers/inclusive ranges, e.g. 445,545-546. Nonempty, no duplicates, reversed ranges, ALL or NONE input. API uses a list of integer IDs. |
| `native_vlan` | Optional | One integer in Catalyst VLAN bounds. Blank retains existing/default native VLAN; separate from allowed membership. |
| `description` | Optional | Printable ASCII text with spaces/case, e.g. Customer Site Alpha; no secrets, quotes, semicolon or backslash. Blank optional preserves existing description. |

Interface: full canonical Cisco name. action exactly Add, Remove or Replace; vlans one/comma/inclusive ranges with no duplicates, 1–4094 excluding 1002–1005. ALL/NONE are observed symbolic states, **not input values**. native_vlan same bounds, optional and independent; description optional. Blank optional inputs preserve native/default VLAN 1 and description.

| Filled input (plus management_ip and interface=GigabitEthernet1/0/2) and state | Expected CLI/result |
|---|---|
| action=Add; vlans=445,545; explicit baseline=445 | `configure terminal / interface GigabitEthernet1/0/2 / switchport trunk allowed vlan add 445,545 / end` (all requested IDs) |
| action=Add; vlans=445; explicit baseline contains 445 | No-op if all other requested fields match |
| action=Add; vlans=445; no explicit allowed baseline (ALL) | ADD_REQUIRES_EXPLICIT_BASELINE, even if No-op; use Replace |
| action=Remove; vlans=445; no baseline (ALL) | `switchport trunk allowed vlan remove 445` in configuration/interface/end; projected ALL except 445; service warning |
| action=Remove; vlans=445; explicit baseline=545 | No-op |
| action=Replace; vlans=445,545-546; existing trunk | `switchport trunk allowed vlan 445,545,546` in configuration/interface/end; service-impact warning for changes |
| action=Replace; vlans=445; empty interface | Setup `switchport / switchport trunk encapsulation dot1q / switchport mode trunk` before `switchport trunk allowed vlan 445` |
| action=Replace; vlans=445; existing access | Full setup proposal, TRUNK_CONVERSION_BLOCKED |
| action=Add; vlans=445; native_vlan=545; description=Customer; tags match | Only requested differing native/description commands; no redundant allowed command |
| action=Remove; vlans=445; native_vlan=445 | NATIVE_VLAN_IMPACT warning; inspect unchanged versus requested native state carefully |
| action=Replace; vlans=ALL or 200-100 or 1002 | Invalid, no CLI |

Evidence: reconstruct all original allowed base/add/remove/except statements in source order; preserve ALL and NONE distinctly. The collector requests operational VLAN lookups for input IDs; trunk evaluation uses configured allowed-list state and does not require global database existence or auto-create VLANs. The global-VLAN warning and database dependency rule described for Access do not add a trunk database prerequisite. Resolve physical members to audited Port-channel owner, retain both stanzas and TARGET_RESOLVED_TO_PORT_CHANNEL; absent/conflicting owner blocks. C3850X never emits an encapsulation selector. C3750X adds it only for new/conversion trunks. Optional differing native VLAN/description render only when requested. No shutdown/MTU changes. Compatible Add?Add and Replace?Remove use projected state and overlap warnings; other unapproved overlapping pairs block. Unknown baseline syntax blocks, never treated as an empty list.

**Engineer operating procedure for C3750X Trunk Port:**

1. In `bulk-input.xlsx`, select the **C3750X Trunk Port** worksheet, populate the exact fields shown above from row 3 (or later), and keep the credential workbook separate.
2. Run the **same v2 `plan` command** from Section 2. For predefined templates verify that live read-only collection identified the intended device, target object and current state; for Manual CLI no connection is performed.
3. Open the **C3750X Trunk Port** tab in generated `plan.xlsx`. Inspect the original entered values, Existing Evidence (if applicable), Proposed CLI, Live Validation, Consistency, Dependencies, No-op, Warnings, Blockers and Engineer Decision; compare the worked examples above against the actual evidence.
4. If invalid or blocked, repair the **input** or missing prerequisites/evidence and regenerate a fresh plan; do not edit the generated CLI/evidence. Record Pending/Approve/Reject only after review; no decision deploys the proposal.

**Approval:** Signed-off detailed contract; deterministic validation only. Hardware/software live validation remains owner-controlled.


### Template 4 — C3750X Description

Status: signed-off detailed contract; deterministic validation only, owner live validation pending.

| Input column | Requirement | Allowed values / forbidden values / example |
|---|---|---|
| `management_ip` | Required | IPv4/IPv6 literal; e.g. 192.0.2.91. No hostname, credentials or URL. |
| `interface` | Required | Existing explicit interface identifier; platform details and sample below. No whitespace except EdgeSwitch lag N; no shell metacharacters. |
| `description` | Required | Printable ASCII text with spaces/case, e.g. Customer Site Alpha; no secrets, quotes, semicolon or backslash. Blank optional preserves existing description. |

Required description; target example `GigabitEthernet1/0/1`. Catalyst requires full canonical FastEthernet/GigabitEthernet/TenGigabitEthernet/FortyGigabitEthernet/HundredGigE/Port-channel/Vlan/Loopback names with numeric slash components and optional numeric suffix; abbreviations like Gi1/0/1 are invalid. Other catalogue identifiers accept [A-Za-z0-9][A-Za-z0-9./:-]* (EdgeSwitch also lag N), but actual unambiguous observed existence is mandatory. Physical and supported logical/aggregate targets stay exact; no LAG redirect.

| Filled input (plus management_ip) and observed state | Expected result |
|---|---|
| interface=GigabitEthernet1/0/1; description=Customer Site Alpha; old/empty text | `configure terminal / interface GigabitEthernet1/0/1 / description Customer Site Alpha / end` |
| same input; matching text | No-op |
| same input; physical member of aggregate | Change exact member description only |
| description blank, target missing/ambiguous, or unreliable source | Invalid input or evidence blocker |
| same target in two rows; identical description | Later No-op, compatible overlap warning for approved families |
| same target in two rows; different descriptions | Ordered overlap blocker |

Evidence: exact interface declaration plus preserved configuration and original observed description, never redirected to aggregate. Approved Cisco keeps complete parent/child stanza through `!`; EdgeSwitch through `exit`, including unrelated PoE/MTU/STP/VLAN/PVID. VLAN defects can warn but no VLAN repair occurs. NCS540 provisional renderer retains `l2transport` when evidenced, and rejects unresolved declarations; NE05E remains provisional, with existing scoped facts rather than a new full-stanza guarantee. Provisional family overlap behavior is conservative, so do not assume the approved-family duplicate warning exemption.

**Engineer operating procedure for C3750X Description:**

1. In `bulk-input.xlsx`, select the **C3750X Description** worksheet, populate the exact fields shown above from row 3 (or later), and keep the credential workbook separate.
2. Run the **same v2 `plan` command** from Section 2. For predefined templates verify that live read-only collection identified the intended device, target object and current state; for Manual CLI no connection is performed.
3. Open the **C3750X Description** tab in generated `plan.xlsx`. Inspect the original entered values, Existing Evidence (if applicable), Proposed CLI, Live Validation, Consistency, Dependencies, No-op, Warnings, Blockers and Engineer Decision; compare the worked examples above against the actual evidence.
4. If invalid or blocked, repair the **input** or missing prerequisites/evidence and regenerate a fresh plan; do not edit the generated CLI/evidence. Record Pending/Approve/Reject only after review; no decision deploys the proposal.

**Approval:** Signed-off detailed contract; deterministic validation only. Hardware/software live validation remains owner-controlled.


### Template 5 — C3850X VLAN Database

Status: signed-off detailed contract; deterministic validation only, owner live validation pending.

| Input column | Requirement | Allowed values / forbidden values / example |
|---|---|---|
| `management_ip` | Required | IPv4/IPv6 literal; e.g. 192.0.2.91. No hostname, credentials or URL. |
| `vlan_id` | Required | One integer VLAN ID; family bounds below. No list/range, ALL, 0 or 4095. |
| `name` | Required | Family-specific VLAN name limits below; no empty name, quotes, semicolon or backslash. |

Bounds: 1–4094 excluding 1002–1005; names =32 ASCII [A-Za-z0-9_.:-], no spaces. VLAN 445,545 or 200-100 in vlan_id is invalid. Empty/overlong names block; Customer Site is invalid on Cisco, valid on EdgeSwitch/NE05E within length bounds.

| Filled input (plus management_ip) and observed state | Expected result |
|---|---|
| vlan_id=901; name=Customer; absent global VLAN | `configure terminal / vlan 901 / name Customer / end` |
| vlan_id=901; name=Customer; existing name Customer | No-op, empty CLI |
| vlan_id=901; name=Customer; existing name Old | Rename with VLAN_RENAME_IMPACT; same CLI, no deletion |
| vlan_id=1002; name=Customer | Invalid input, no CLI |
| vlan_id=901; name=Customer; unknown evidence | Blocked; never infer absent |

Evidence: full reliable running-config global VLAN declaration/list/name plus `show vlan id 901`. Explicit absence creates; operational failure/inconclusive output falls back only to complete config, annotated VLAN_LOOKUP_FALLBACK. Conflicting reliable names/existence block. Inactive/down is informational. An empty reliably collected database proves absence. Interface membership and service references do not establish global existence. Earlier approved creation supplies prerequisites to later ME EVC; conflicting same-ID requests block and cite rows. EdgeSwitch port membership never requires global creation. No interface command is emitted here.

**Engineer operating procedure for C3850X VLAN Database:**

1. In `bulk-input.xlsx`, select the **C3850X VLAN Database** worksheet, populate the exact fields shown above from row 3 (or later), and keep the credential workbook separate.
2. Run the **same v2 `plan` command** from Section 2. For predefined templates verify that live read-only collection identified the intended device, target object and current state; for Manual CLI no connection is performed.
3. Open the **C3850X VLAN Database** tab in generated `plan.xlsx`. Inspect the original entered values, Existing Evidence (if applicable), Proposed CLI, Live Validation, Consistency, Dependencies, No-op, Warnings, Blockers and Engineer Decision; compare the worked examples above against the actual evidence.
4. If invalid or blocked, repair the **input** or missing prerequisites/evidence and regenerate a fresh plan; do not edit the generated CLI/evidence. Record Pending/Approve/Reject only after review; no decision deploys the proposal.

**Approval:** Signed-off detailed contract; deterministic validation only. Hardware/software live validation remains owner-controlled.


### Template 6 — C3850X Access Port

Status: signed-off detailed contract; deterministic validation only, owner live validation pending.

| Input column | Requirement | Allowed values / forbidden values / example |
|---|---|---|
| `management_ip` | Required | IPv4/IPv6 literal; e.g. 192.0.2.91. No hostname, credentials or URL. |
| `interface` | Required | Existing explicit interface identifier; platform details and sample below. No whitespace except EdgeSwitch lag N; no shell metacharacters. |
| `vlan_id` | Required | One integer VLAN ID; family bounds below. No list/range, ALL, 0 or 4095. |
| `description` | Optional | Printable ASCII text with spaces/case, e.g. Customer Site Alpha; no secrets, quotes, semicolon or backslash. Blank optional preserves existing description. |

Interface: full canonical Cisco name, e.g. GigabitEthernet1/0/1; no abbreviated Gi names. vlan_id: one integer 1–4094 excluding 1002–1005. Optional description preserves blank; input has no action/native VLAN.

| Filled input (plus management_ip) and observed state | Expected result |
|---|---|
| interface=GigabitEthernet1/0/1; vlan_id=445; description=Customer; empty/dynamic/access different | `configure terminal / interface GigabitEthernet1/0/1 / description Customer / switchport / switchport mode access / switchport access vlan 445 / end` |
| same interface; vlan_id=445; description blank; explicit access VLAN already 445 | No-op; existing description preserved |
| vlan_id=445; missing global VLAN | Nonblocking GLOBAL_VLAN_REQUIRED; proposed access CLI, no auto-create |
| same input after earlier Pending/Reject database prerequisite | Dependency not approved; cannot claim readiness |
| same input on configured trunk or routed no switchport | Show proposal; ACCESS_CONVERSION_BLOCKED |
| same input on channel-group member | PHYSICAL_PORT_CHANNEL_MEMBER; no redirection |
| vlan_id=1002 or interface=Gi1/0/1 | Invalid, no CLI |

Evidence: full physical stanza and logical Port-channel evidence where owned; approved show vlan id lookup/config fallback for target VLAN. Explicit access mode wins over residual trunk statements, which warn. Access VLAN without explicit mode/empty/dynamic mode warns; inferred default VLAN alone is not a complete match. Shutdown retained. Earlier Access then Description is compatible, warns both rows, final description wins. Access versus Trunk on same effective resource blocks. Unknown syntax/owner/evidence is never waived by a No-op.

**Engineer operating procedure for C3850X Access Port:**

1. In `bulk-input.xlsx`, select the **C3850X Access Port** worksheet, populate the exact fields shown above from row 3 (or later), and keep the credential workbook separate.
2. Run the **same v2 `plan` command** from Section 2. For predefined templates verify that live read-only collection identified the intended device, target object and current state; for Manual CLI no connection is performed.
3. Open the **C3850X Access Port** tab in generated `plan.xlsx`. Inspect the original entered values, Existing Evidence (if applicable), Proposed CLI, Live Validation, Consistency, Dependencies, No-op, Warnings, Blockers and Engineer Decision; compare the worked examples above against the actual evidence.
4. If invalid or blocked, repair the **input** or missing prerequisites/evidence and regenerate a fresh plan; do not edit the generated CLI/evidence. Record Pending/Approve/Reject only after review; no decision deploys the proposal.

**Approval:** Signed-off detailed contract; deterministic validation only. Hardware/software live validation remains owner-controlled.


### Template 7 — C3850X Trunk Port

Status: signed-off detailed contract; deterministic validation only, owner live validation pending.

| Input column | Requirement | Allowed values / forbidden values / example |
|---|---|---|
| `management_ip` | Required | IPv4/IPv6 literal; e.g. 192.0.2.91. No hostname, credentials or URL. |
| `interface` | Required | Existing explicit interface identifier; platform details and sample below. No whitespace except EdgeSwitch lag N; no shell metacharacters. |
| `action` | Required | Exact family-specific selection below; no lowercase aliases. |
| `vlans` | Required | Comma-separated integers/inclusive ranges, e.g. 445,545-546. Nonempty, no duplicates, reversed ranges, ALL or NONE input. API uses a list of integer IDs. |
| `native_vlan` | Optional | One integer in Catalyst VLAN bounds. Blank retains existing/default native VLAN; separate from allowed membership. |
| `description` | Optional | Printable ASCII text with spaces/case, e.g. Customer Site Alpha; no secrets, quotes, semicolon or backslash. Blank optional preserves existing description. |

Interface: full canonical Cisco name. action exactly Add, Remove or Replace; vlans one/comma/inclusive ranges with no duplicates, 1–4094 excluding 1002–1005. ALL/NONE are observed symbolic states, **not input values**. native_vlan same bounds, optional and independent; description optional. Blank optional inputs preserve native/default VLAN 1 and description.

| Filled input (plus management_ip and interface=GigabitEthernet1/0/2) and state | Expected CLI/result |
|---|---|
| action=Add; vlans=445,545; explicit baseline=445 | `configure terminal / interface GigabitEthernet1/0/2 / switchport trunk allowed vlan add 445,545 / end` (all requested IDs) |
| action=Add; vlans=445; explicit baseline contains 445 | No-op if all other requested fields match |
| action=Add; vlans=445; no explicit allowed baseline (ALL) | ADD_REQUIRES_EXPLICIT_BASELINE, even if No-op; use Replace |
| action=Remove; vlans=445; no baseline (ALL) | `switchport trunk allowed vlan remove 445` in configuration/interface/end; projected ALL except 445; service warning |
| action=Remove; vlans=445; explicit baseline=545 | No-op |
| action=Replace; vlans=445,545-546; existing trunk | `switchport trunk allowed vlan 445,545,546` in configuration/interface/end; service-impact warning for changes |
| action=Replace; vlans=445; empty interface | Setup `switchport / switchport mode trunk` before `switchport trunk allowed vlan 445` |
| action=Replace; vlans=445; existing access | Full setup proposal, TRUNK_CONVERSION_BLOCKED |
| action=Add; vlans=445; native_vlan=545; description=Customer; tags match | Only requested differing native/description commands; no redundant allowed command |
| action=Remove; vlans=445; native_vlan=445 | NATIVE_VLAN_IMPACT warning; inspect unchanged versus requested native state carefully |
| action=Replace; vlans=ALL or 200-100 or 1002 | Invalid, no CLI |

Evidence: reconstruct all original allowed base/add/remove/except statements in source order; preserve ALL and NONE distinctly. The collector requests operational VLAN lookups for input IDs; trunk evaluation uses configured allowed-list state and does not require global database existence or auto-create VLANs. The global-VLAN warning and database dependency rule described for Access do not add a trunk database prerequisite. Resolve physical members to audited Port-channel owner, retain both stanzas and TARGET_RESOLVED_TO_PORT_CHANNEL; absent/conflicting owner blocks. C3850X never emits an encapsulation selector. C3750X adds it only for new/conversion trunks. Optional differing native VLAN/description render only when requested. No shutdown/MTU changes. Compatible Add?Add and Replace?Remove use projected state and overlap warnings; other unapproved overlapping pairs block. Unknown baseline syntax blocks, never treated as an empty list.

**Engineer operating procedure for C3850X Trunk Port:**

1. In `bulk-input.xlsx`, select the **C3850X Trunk Port** worksheet, populate the exact fields shown above from row 3 (or later), and keep the credential workbook separate.
2. Run the **same v2 `plan` command** from Section 2. For predefined templates verify that live read-only collection identified the intended device, target object and current state; for Manual CLI no connection is performed.
3. Open the **C3850X Trunk Port** tab in generated `plan.xlsx`. Inspect the original entered values, Existing Evidence (if applicable), Proposed CLI, Live Validation, Consistency, Dependencies, No-op, Warnings, Blockers and Engineer Decision; compare the worked examples above against the actual evidence.
4. If invalid or blocked, repair the **input** or missing prerequisites/evidence and regenerate a fresh plan; do not edit the generated CLI/evidence. Record Pending/Approve/Reject only after review; no decision deploys the proposal.

**Approval:** Signed-off detailed contract; deterministic validation only. Hardware/software live validation remains owner-controlled.


### Template 8 — C3850X Description

Status: signed-off detailed contract; deterministic validation only, owner live validation pending.

| Input column | Requirement | Allowed values / forbidden values / example |
|---|---|---|
| `management_ip` | Required | IPv4/IPv6 literal; e.g. 192.0.2.91. No hostname, credentials or URL. |
| `interface` | Required | Existing explicit interface identifier; platform details and sample below. No whitespace except EdgeSwitch lag N; no shell metacharacters. |
| `description` | Required | Printable ASCII text with spaces/case, e.g. Customer Site Alpha; no secrets, quotes, semicolon or backslash. Blank optional preserves existing description. |

Required description; target example `GigabitEthernet1/0/1`. Catalyst requires full canonical FastEthernet/GigabitEthernet/TenGigabitEthernet/FortyGigabitEthernet/HundredGigE/Port-channel/Vlan/Loopback names with numeric slash components and optional numeric suffix; abbreviations like Gi1/0/1 are invalid. Other catalogue identifiers accept [A-Za-z0-9][A-Za-z0-9./:-]* (EdgeSwitch also lag N), but actual unambiguous observed existence is mandatory. Physical and supported logical/aggregate targets stay exact; no LAG redirect.

| Filled input (plus management_ip) and observed state | Expected result |
|---|---|
| interface=GigabitEthernet1/0/1; description=Customer Site Alpha; old/empty text | `configure terminal / interface GigabitEthernet1/0/1 / description Customer Site Alpha / end` |
| same input; matching text | No-op |
| same input; physical member of aggregate | Change exact member description only |
| description blank, target missing/ambiguous, or unreliable source | Invalid input or evidence blocker |
| same target in two rows; identical description | Later No-op, compatible overlap warning for approved families |
| same target in two rows; different descriptions | Ordered overlap blocker |

Evidence: exact interface declaration plus preserved configuration and original observed description, never redirected to aggregate. Approved Cisco keeps complete parent/child stanza through `!`; EdgeSwitch through `exit`, including unrelated PoE/MTU/STP/VLAN/PVID. VLAN defects can warn but no VLAN repair occurs. NCS540 provisional renderer retains `l2transport` when evidenced, and rejects unresolved declarations; NE05E remains provisional, with existing scoped facts rather than a new full-stanza guarantee. Provisional family overlap behavior is conservative, so do not assume the approved-family duplicate warning exemption.

**Engineer operating procedure for C3850X Description:**

1. In `bulk-input.xlsx`, select the **C3850X Description** worksheet, populate the exact fields shown above from row 3 (or later), and keep the credential workbook separate.
2. Run the **same v2 `plan` command** from Section 2. For predefined templates verify that live read-only collection identified the intended device, target object and current state; for Manual CLI no connection is performed.
3. Open the **C3850X Description** tab in generated `plan.xlsx`. Inspect the original entered values, Existing Evidence (if applicable), Proposed CLI, Live Validation, Consistency, Dependencies, No-op, Warnings, Blockers and Engineer Decision; compare the worked examples above against the actual evidence.
4. If invalid or blocked, repair the **input** or missing prerequisites/evidence and regenerate a fresh plan; do not edit the generated CLI/evidence. Record Pending/Approve/Reject only after review; no decision deploys the proposal.

**Approval:** Signed-off detailed contract; deterministic validation only. Hardware/software live validation remains owner-controlled.


### Template 9 — ME3600X VLAN Database

Status: signed-off detailed contract; deterministic validation only, owner live validation pending.

| Input column | Requirement | Allowed values / forbidden values / example |
|---|---|---|
| `management_ip` | Required | IPv4/IPv6 literal; e.g. 192.0.2.91. No hostname, credentials or URL. |
| `vlan_id` | Required | One integer VLAN ID; family bounds below. No list/range, ALL, 0 or 4095. |
| `name` | Required | Family-specific VLAN name limits below; no empty name, quotes, semicolon or backslash. |

Bounds: 1–4094 excluding 1002–1005; names =32 ASCII [A-Za-z0-9_.:-], no spaces. VLAN 445,545 or 200-100 in vlan_id is invalid. Empty/overlong names block; Customer Site is invalid on Cisco, valid on EdgeSwitch/NE05E within length bounds.

| Filled input (plus management_ip) and observed state | Expected result |
|---|---|
| vlan_id=901; name=Customer; absent global VLAN | `configure terminal / vlan 901 / name Customer / end` |
| vlan_id=901; name=Customer; existing name Customer | No-op, empty CLI |
| vlan_id=901; name=Customer; existing name Old | Rename with VLAN_RENAME_IMPACT; same CLI, no deletion |
| vlan_id=1002; name=Customer | Invalid input, no CLI |
| vlan_id=901; name=Customer; unknown evidence | Blocked; never infer absent |

Evidence: full reliable running-config global VLAN declaration/list/name plus `show vlan id 901`. Explicit absence creates; operational failure/inconclusive output falls back only to complete config, annotated VLAN_LOOKUP_FALLBACK. Conflicting reliable names/existence block. Inactive/down is informational. An empty reliably collected database proves absence. Interface membership and service references do not establish global existence. Earlier approved creation supplies prerequisites to later ME EVC; conflicting same-ID requests block and cite rows. EdgeSwitch port membership never requires global creation. No interface command is emitted here.

**Engineer operating procedure for ME3600X VLAN Database:**

1. In `bulk-input.xlsx`, select the **ME3600X VLAN Database** worksheet, populate the exact fields shown above from row 3 (or later), and keep the credential workbook separate.
2. Run the **same v2 `plan` command** from Section 2. For predefined templates verify that live read-only collection identified the intended device, target object and current state; for Manual CLI no connection is performed.
3. Open the **ME3600X VLAN Database** tab in generated `plan.xlsx`. Inspect the original entered values, Existing Evidence (if applicable), Proposed CLI, Live Validation, Consistency, Dependencies, No-op, Warnings, Blockers and Engineer Decision; compare the worked examples above against the actual evidence.
4. If invalid or blocked, repair the **input** or missing prerequisites/evidence and regenerate a fresh plan; do not edit the generated CLI/evidence. Record Pending/Approve/Reject only after review; no decision deploys the proposal.

**Approval:** Signed-off detailed contract; deterministic validation only. Hardware/software live validation remains owner-controlled.


### Template 10 — ME3600X EVC

Status: signed-off detailed contract; deterministic validation only, owner live validation pending.

| Input column | Requirement | Allowed values / forbidden values / example |
|---|---|---|
| `management_ip` | Required | IPv4/IPv6 literal; e.g. 192.0.2.91. No hostname, credentials or URL. |
| `interface` | Required | Existing explicit interface identifier; platform details and sample below. No whitespace except EdgeSwitch lag N; no shell metacharacters. |
| `service_instance_id` | Required | Integer 1–4000, independent of outer VLAN, push_vlan and BD. No 0/4001. |
| `encapsulation` | Required | Exact selector below; conditional outer/inner input rules apply. |
| `bridge_domain` | Required | EVC integer 1–4094 (ME excludes 1002–1005); NCS540 nonempty ASCII name [A-Za-z0-9_.:-]+, e.g. CUSTOMER-445. |
| `outer_vlan` | Conditional | Required for tagged encapsulation, forbidden for untagged. EVC compact inclusive ID/range/list 1–4094; NCS540 one integer 1–4094. No reversed range, ALL or NONE. |
| `inner_vlan` | Conditional | Required only for QinQ; forbidden otherwise. EVC ID/range/list 1–4094 or any (normalized to 1-4094); NCS540 one integer 1–4094. |
| `rewrite` | Optional | Blank defaults to None; exactly None, Pop 1 symmetric, Pop 2 symmetric, Push dot1q, Push dot1q symmetric. Matrix below is mandatory; no substitution. |
| `push_vlan` | Conditional | Required only with either Push, otherwise forbidden. One integer 1–4094, independent of ingress VLANs. No list/range. |
| `split_horizon_group` | Optional | Integer 0–15; explicit 0 is retained, blank means omit on child recreation. No -1/16. |
| `description` | Optional | Printable ASCII text with spaces/case, e.g. Customer Site Alpha; no secrets, quotes, semicolon or backslash. Child-only; blank omits existing description on recreation. |
| `interface_description` | Optional | Parent-only description; blank preserves. Printable ASCII 1–256, no secrets, double quotes, semicolon or backslash. |

See the [complete matrix and scenario table](#evc-complete-encapsulation-x-rewrite-matrix-templates-10-and-12) below; both EVC sheets have exactly the same child input grammar. Interface accepts physical/aggregate FastEthernet/GigabitEthernet/TenGigabitEthernet/Port-channel or Fa/Gi/Te/Po followed by numeric slash components, without subinterface suffix. Ingress outer/inner IDs are 1–4094, including IDs otherwise reserved in a global switching database. ME global BD uses its stricter database bounds.

Every row renders `configure terminal / interface GigabitEthernet0/1 / no service instance 3000 / service instance 3000 ethernet / <complete child commands> / end`. It never returns No-op, even when matching or confirmed absent. Existing target triggers SERVICE_INSTANCE_RECREATE_IMPACT. Service Instance Differences lists exact unique before/after commands, added/removed settings and recreation/existence. OMITTED_CHILD_SETTINGS means old child commands absent from desired specification; nested syntax facts and ending `!` are not duplicate omitted commands. All unrelated children and parent commands are preserved. A blank child description/group/rewrite can remove old settings; blank interface_description preserves parent text. Group 0 is explicit, not absence.

ME parent requires both switchport mode trunk and switchport trunk allowed vlan none; compatible empty parent can initialize both. A missing BD global VLAN warns with GLOBAL_VLAN_REQUIRED and retains the missing ID for future pre-apply checks; it does not block alone or trigger auto-creation. An explicitly planned earlier database creation retains its approval dependency. ASR uses inline BD only, no ME switchport setup; compatible empty parent can propose no ip address. Neither guesses no shutdown/MTU/STP. Routed, incompatible, physical LAG-owned parents block. Unknown child ingress, duplicate instance ID, unknown forwarding syntax or conflicting detail/config block. QinQ overlap compares outer/inner pairs; unrelated service with intersecting ingress blocks (single-tag versus QinQ coexistence is not assumed safe). Repeated same-ID EVC rows conflict; distinct disjoint ingress children can sequence with warnings.

Evidence: exact sanitized parent declaration and parent-level settings/terminator, and only the requested service-instance child (including its terminator when present), policies/admin/ownership and narrowly relevant dependencies, plus `show ethernet service instance id 3000 interface GigabitEthernet0/1 detail`. Explicit absence must identify requested ID/interface. Up/Down stays operational evidence (Down warns); unparseable/rejected detail falls back to reliable config with SERVICE_DETAIL_FALLBACK, never inferred absence. Contradictory reliable ingress/rewrite/BD/group blocks SERVICE_OBSERVATION_CONFLICT. ME global lookup uses show vlan id <BD>; fallback is annotated. ASR global-binding relationships conflict and are never automatically migrated.

The shared detail parser accepts hardware `Associated Interface:` and `Service Instance ID:` fields and matches short names such as g0/16, g0/0/12 and te0/1 to expanded device names. Only a matching `Service Instance ID <ID> on interface <PORT> does not exist` proves absence. CLI rejection/timeout remains error; unsupported, partial or mismatched detail remains unknown. Dot1q/QinQ ethertype annotations are normalized for facts while original output, description, Up/Down and microblocks remain evidence. A valid instance without a bridge-domain microblock is present, with forwarding evidence incomplete; Existing Evidence labels this and SERVICE_DETAIL_INCOMPLETE blocks planning even when config contains a BD. Repeat owner-controlled read-only validation on both families is needed to confirm release-specific replies, command failures and JSON/XLSX agreement; no device apply/save is implemented.

**Engineer operating procedure for ME3600X EVC:**

1. In `bulk-input.xlsx`, select the **ME3600X EVC** worksheet, populate the exact fields shown above from row 3 (or later), and keep the credential workbook separate.
2. Run the **same v2 `plan` command** from Section 2. For predefined templates verify that live read-only collection identified the intended device, target object and current state; for Manual CLI no connection is performed.
3. Open the **ME3600X EVC** tab in generated `plan.xlsx`. Inspect the original entered values, Existing Evidence (if applicable), Proposed CLI, Live Validation, Consistency, Dependencies, No-op, Warnings, Blockers and Engineer Decision; compare the worked examples above against the actual evidence.
4. If invalid or blocked, repair the **input** or missing prerequisites/evidence and regenerate a fresh plan; do not edit the generated CLI/evidence. Record Pending/Approve/Reject only after review; no decision deploys the proposal.

**Approval:** Signed-off detailed contract; deterministic validation only. Hardware/software live validation remains owner-controlled.


### Template 11 — ME3600X Description

Status: signed-off detailed contract; deterministic validation only, owner live validation pending.

| Input column | Requirement | Allowed values / forbidden values / example |
|---|---|---|
| `management_ip` | Required | IPv4/IPv6 literal; e.g. 192.0.2.91. No hostname, credentials or URL. |
| `interface` | Required | Existing explicit interface identifier; platform details and sample below. No whitespace except EdgeSwitch lag N; no shell metacharacters. |
| `description` | Required | Printable ASCII text with spaces/case, e.g. Customer Site Alpha; no secrets, quotes, semicolon or backslash. Blank optional preserves existing description. |

Required description; target example `GigabitEthernet0/1`. Catalyst requires full canonical FastEthernet/GigabitEthernet/TenGigabitEthernet/FortyGigabitEthernet/HundredGigE/Port-channel/Vlan/Loopback names with numeric slash components and optional numeric suffix; abbreviations like Gi1/0/1 are invalid. Other catalogue identifiers accept [A-Za-z0-9][A-Za-z0-9./:-]* (EdgeSwitch also lag N), but actual unambiguous observed existence is mandatory. Physical and supported logical/aggregate targets stay exact; no LAG redirect.

| Filled input (plus management_ip) and observed state | Expected result |
|---|---|
| interface=GigabitEthernet0/1; description=Customer Site Alpha; old/empty text | `configure terminal / interface GigabitEthernet0/1 / description Customer Site Alpha / end` |
| same input; matching text | No-op |
| same input; physical member of aggregate | Change exact member description only |
| description blank, target missing/ambiguous, or unreliable source | Invalid input or evidence blocker |
| same target in two rows; identical description | Later No-op, compatible overlap warning for approved families |
| same target in two rows; different descriptions | Ordered overlap blocker |

Evidence: exact interface declaration plus preserved configuration and original observed description, never redirected to aggregate. Approved Cisco keeps complete parent/child stanza through `!`; EdgeSwitch through `exit`, including unrelated PoE/MTU/STP/VLAN/PVID. VLAN defects can warn but no VLAN repair occurs. NCS540 provisional renderer retains `l2transport` when evidenced, and rejects unresolved declarations; NE05E remains provisional, with existing scoped facts rather than a new full-stanza guarantee. Provisional family overlap behavior is conservative, so do not assume the approved-family duplicate warning exemption.

**Engineer operating procedure for ME3600X Description:**

1. In `bulk-input.xlsx`, select the **ME3600X Description** worksheet, populate the exact fields shown above from row 3 (or later), and keep the credential workbook separate.
2. Run the **same v2 `plan` command** from Section 2. For predefined templates verify that live read-only collection identified the intended device, target object and current state; for Manual CLI no connection is performed.
3. Open the **ME3600X Description** tab in generated `plan.xlsx`. Inspect the original entered values, Existing Evidence (if applicable), Proposed CLI, Live Validation, Consistency, Dependencies, No-op, Warnings, Blockers and Engineer Decision; compare the worked examples above against the actual evidence.
4. If invalid or blocked, repair the **input** or missing prerequisites/evidence and regenerate a fresh plan; do not edit the generated CLI/evidence. Record Pending/Approve/Reject only after review; no decision deploys the proposal.

**Approval:** Signed-off detailed contract; deterministic validation only. Hardware/software live validation remains owner-controlled.


### Template 12 — ASR920 EVC

Status: signed-off detailed contract; deterministic validation only, owner live validation pending.

| Input column | Requirement | Allowed values / forbidden values / example |
|---|---|---|
| `management_ip` | Required | IPv4/IPv6 literal; e.g. 192.0.2.91. No hostname, credentials or URL. |
| `interface` | Required | Existing explicit interface identifier; platform details and sample below. No whitespace except EdgeSwitch lag N; no shell metacharacters. |
| `service_instance_id` | Required | Integer 1–4000, independent of outer VLAN, push_vlan and BD. No 0/4001. |
| `encapsulation` | Required | Exact selector below; conditional outer/inner input rules apply. |
| `bridge_domain` | Required | EVC integer 1–4094 (ME excludes 1002–1005); NCS540 nonempty ASCII name [A-Za-z0-9_.:-]+, e.g. CUSTOMER-445. |
| `outer_vlan` | Conditional | Required for tagged encapsulation, forbidden for untagged. EVC compact inclusive ID/range/list 1–4094; NCS540 one integer 1–4094. No reversed range, ALL or NONE. |
| `inner_vlan` | Conditional | Required only for QinQ; forbidden otherwise. EVC ID/range/list 1–4094 or any (normalized to 1-4094); NCS540 one integer 1–4094. |
| `rewrite` | Optional | Blank defaults to None; exactly None, Pop 1 symmetric, Pop 2 symmetric, Push dot1q, Push dot1q symmetric. Matrix below is mandatory; no substitution. |
| `push_vlan` | Conditional | Required only with either Push, otherwise forbidden. One integer 1–4094, independent of ingress VLANs. No list/range. |
| `split_horizon_group` | Optional | Integer 0–15; explicit 0 is retained, blank means omit on child recreation. No -1/16. |
| `description` | Optional | Printable ASCII text with spaces/case, e.g. Customer Site Alpha; no secrets, quotes, semicolon or backslash. Child-only; blank omits existing description on recreation. |
| `interface_description` | Optional | Parent-only description; blank preserves. Printable ASCII 1–256, no secrets, double quotes, semicolon or backslash. |

See the [complete matrix and scenario table](#evc-complete-encapsulation-x-rewrite-matrix-templates-10-and-12) below; both EVC sheets have exactly the same child input grammar. Interface accepts physical/aggregate FastEthernet/GigabitEthernet/TenGigabitEthernet/Port-channel or Fa/Gi/Te/Po followed by numeric slash components, without subinterface suffix. Ingress outer/inner IDs are 1–4094, including IDs otherwise reserved in a global switching database. ME global BD uses its stricter database bounds.

Every row renders `configure terminal / interface GigabitEthernet0/1 / no service instance 3000 / service instance 3000 ethernet / <complete child commands> / end`. It never returns No-op, even when matching or confirmed absent. Existing target triggers SERVICE_INSTANCE_RECREATE_IMPACT. Service Instance Differences lists exact unique before/after commands, added/removed settings and recreation/existence. OMITTED_CHILD_SETTINGS means old child commands absent from desired specification; nested syntax facts and ending `!` are not duplicate omitted commands. All unrelated children and parent commands are preserved. A blank child description/group/rewrite can remove old settings; blank interface_description preserves parent text. Group 0 is explicit, not absence.

ME parent requires both switchport mode trunk and switchport trunk allowed vlan none; compatible empty parent can initialize both. A missing BD global VLAN warns with GLOBAL_VLAN_REQUIRED and retains the missing ID for future pre-apply checks; it does not block alone or trigger auto-creation. An explicitly planned earlier database creation retains its approval dependency. ASR uses inline BD only, no ME switchport setup; compatible empty parent can propose no ip address. Neither guesses no shutdown/MTU/STP. Routed, incompatible, physical LAG-owned parents block. Unknown child ingress, duplicate instance ID, unknown forwarding syntax or conflicting detail/config block. QinQ overlap compares outer/inner pairs; unrelated service with intersecting ingress blocks (single-tag versus QinQ coexistence is not assumed safe). Repeated same-ID EVC rows conflict; distinct disjoint ingress children can sequence with warnings.

Evidence: exact sanitized parent declaration and parent-level settings/terminator, and only the requested service-instance child (including its terminator when present), policies/admin/ownership and narrowly relevant dependencies, plus `show ethernet service instance id 3000 interface GigabitEthernet0/1 detail`. Explicit absence must identify requested ID/interface. Up/Down stays operational evidence (Down warns); unparseable/rejected detail falls back to reliable config with SERVICE_DETAIL_FALLBACK, never inferred absence. Contradictory reliable ingress/rewrite/BD/group blocks SERVICE_OBSERVATION_CONFLICT. ME global lookup uses show vlan id <BD>; fallback is annotated. ASR global-binding relationships conflict and are never automatically migrated.

**Engineer operating procedure for ASR920 EVC:**

1. In `bulk-input.xlsx`, select the **ASR920 EVC** worksheet, populate the exact fields shown above from row 3 (or later), and keep the credential workbook separate.
2. Run the **same v2 `plan` command** from Section 2. For predefined templates verify that live read-only collection identified the intended device, target object and current state; for Manual CLI no connection is performed.
3. Open the **ASR920 EVC** tab in generated `plan.xlsx`. Inspect the original entered values, Existing Evidence (if applicable), Proposed CLI, Live Validation, Consistency, Dependencies, No-op, Warnings, Blockers and Engineer Decision; compare the worked examples above against the actual evidence.
4. If invalid or blocked, repair the **input** or missing prerequisites/evidence and regenerate a fresh plan; do not edit the generated CLI/evidence. Record Pending/Approve/Reject only after review; no decision deploys the proposal.

**Approval:** Signed-off detailed contract; deterministic validation only. Hardware/software live validation remains owner-controlled.


### Template 13 — ASR920 Description

Status: signed-off detailed contract; deterministic validation only, owner live validation pending.

| Input column | Requirement | Allowed values / forbidden values / example |
|---|---|---|
| `management_ip` | Required | IPv4/IPv6 literal; e.g. 192.0.2.91. No hostname, credentials or URL. |
| `interface` | Required | Existing explicit interface identifier; platform details and sample below. No whitespace except EdgeSwitch lag N; no shell metacharacters. |
| `description` | Required | Printable ASCII text with spaces/case, e.g. Customer Site Alpha; no secrets, quotes, semicolon or backslash. Blank optional preserves existing description. |

Required description; target example `GigabitEthernet0/1`. Catalyst requires full canonical FastEthernet/GigabitEthernet/TenGigabitEthernet/FortyGigabitEthernet/HundredGigE/Port-channel/Vlan/Loopback names with numeric slash components and optional numeric suffix; abbreviations like Gi1/0/1 are invalid. Other catalogue identifiers accept [A-Za-z0-9][A-Za-z0-9./:-]* (EdgeSwitch also lag N), but actual unambiguous observed existence is mandatory. Physical and supported logical/aggregate targets stay exact; no LAG redirect.

| Filled input (plus management_ip) and observed state | Expected result |
|---|---|
| interface=GigabitEthernet0/1; description=Customer Site Alpha; old/empty text | `configure terminal / interface GigabitEthernet0/1 / description Customer Site Alpha / end` |
| same input; matching text | No-op |
| same input; physical member of aggregate | Change exact member description only |
| description blank, target missing/ambiguous, or unreliable source | Invalid input or evidence blocker |
| same target in two rows; identical description | Later No-op, compatible overlap warning for approved families |
| same target in two rows; different descriptions | Ordered overlap blocker |

Evidence: exact interface declaration plus preserved configuration and original observed description, never redirected to aggregate. Approved Cisco keeps complete parent/child stanza through `!`; EdgeSwitch through `exit`, including unrelated PoE/MTU/STP/VLAN/PVID. VLAN defects can warn but no VLAN repair occurs. NCS540 provisional renderer retains `l2transport` when evidenced, and rejects unresolved declarations; NE05E remains provisional, with existing scoped facts rather than a new full-stanza guarantee. Provisional family overlap behavior is conservative, so do not assume the approved-family duplicate warning exemption.

**Engineer operating procedure for ASR920 Description:**

1. In `bulk-input.xlsx`, select the **ASR920 Description** worksheet, populate the exact fields shown above from row 3 (or later), and keep the credential workbook separate.
2. Run the **same v2 `plan` command** from Section 2. For predefined templates verify that live read-only collection identified the intended device, target object and current state; for Manual CLI no connection is performed.
3. Open the **ASR920 Description** tab in generated `plan.xlsx`. Inspect the original entered values, Existing Evidence (if applicable), Proposed CLI, Live Validation, Consistency, Dependencies, No-op, Warnings, Blockers and Engineer Decision; compare the worked examples above against the actual evidence.
4. If invalid or blocked, repair the **input** or missing prerequisites/evidence and regenerate a fresh plan; do not edit the generated CLI/evidence. Record Pending/Approve/Reject only after review; no decision deploys the proposal.

**Approval:** Signed-off detailed contract; deterministic validation only. Hardware/software live validation remains owner-controlled.


### Template 14 — EdgeSwitch VLAN Database

Status: signed-off detailed contract; deterministic validation only, owner live validation pending.

| Input column | Requirement | Allowed values / forbidden values / example |
|---|---|---|
| `management_ip` | Required | IPv4/IPv6 literal; e.g. 192.0.2.91. No hostname, credentials or URL. |
| `vlan_id` | Required | One integer VLAN ID; family bounds below. No list/range, ALL, 0 or 4095. |
| `name` | Required | Family-specific VLAN name limits below; no empty name, quotes, semicolon or backslash. |

Bounds: 2–4093; names =32 ASCII characters including spaces. VLAN 445,545 or 200-100 in vlan_id is invalid. Empty/overlong names block; Customer Site is invalid on Cisco, valid on EdgeSwitch/NE05E within length bounds.

| Filled input (plus management_ip) and observed state | Expected result |
|---|---|
| vlan_id=901; name=Customer; absent global VLAN | `vlan database / vlan 901 / vlan name 901 "Customer" / exit` |
| vlan_id=901; name=Customer; existing name Customer | No-op, empty CLI |
| vlan_id=901; name=Customer; existing name Old | Rename with VLAN_RENAME_IMPACT; same CLI, omit vlan 901 when already present |
| vlan_id=1; name=Customer | Invalid input, no CLI |
| vlan_id=901; name=Customer; unknown evidence | Blocked; never infer absent |

Evidence: full reliable running-config global VLAN declaration/list/name plus `show vlan 901`. Explicit absence creates; operational failure/inconclusive output falls back only to complete config, annotated VLAN_LOOKUP_FALLBACK. Conflicting reliable names/existence block. Inactive/down is informational. An empty reliably collected database proves absence. Interface membership and service references do not establish global existence. Earlier approved creation supplies prerequisites to later ME EVC; conflicting same-ID requests block and cite rows. EdgeSwitch port membership never requires global creation. No interface command is emitted here.

**Engineer operating procedure for EdgeSwitch VLAN Database:**

1. In `bulk-input.xlsx`, select the **EdgeSwitch VLAN Database** worksheet, populate the exact fields shown above from row 3 (or later), and keep the credential workbook separate.
2. Run the **same v2 `plan` command** from Section 2. For predefined templates verify that live read-only collection identified the intended device, target object and current state; for Manual CLI no connection is performed.
3. Open the **EdgeSwitch VLAN Database** tab in generated `plan.xlsx`. Inspect the original entered values, Existing Evidence (if applicable), Proposed CLI, Live Validation, Consistency, Dependencies, No-op, Warnings, Blockers and Engineer Decision; compare the worked examples above against the actual evidence.
4. If invalid or blocked, repair the **input** or missing prerequisites/evidence and regenerate a fresh plan; do not edit the generated CLI/evidence. Record Pending/Approve/Reject only after review; no decision deploys the proposal.

**Approval:** Signed-off detailed contract; deterministic validation only. Hardware/software live validation remains owner-controlled.


### Template 15 — EdgeSwitch VLAN Port

Status: signed-off detailed contract; deterministic validation only, owner live validation pending.

| Input column | Requirement | Allowed values / forbidden values / example |
|---|---|---|
| `management_ip` | Required | IPv4/IPv6 literal; e.g. 192.0.2.91. No hostname, credentials or URL. |
| `interface` | Required | Existing explicit interface identifier; platform details and sample below. No whitespace except EdgeSwitch lag N; no shell metacharacters. |
| `action` | Required | Exact family-specific selection below; no lowercase aliases. |
| `tagged_vlans` | Conditional | One/comma/inclusive range/list 2–4093; required for Remove; Add/Change requires this and/or pvid. Example 545,745-746. No ALL/NONE/1/4094/reversed ranges. |
| `pvid` | Conditional | Optional Add/Change integer 2–4093; forbidden for Remove even if unchanged. May also occur in tagged_vlans; blank retains current PVID. |
| `description` | Optional | Printable ASCII text with spaces/case, e.g. Customer Site Alpha; no secrets, quotes, semicolon or backslash. Blank optional preserves existing description. |

Interface example 0/1 or evidenced lag 1. Only Add/Change or Remove. tagged_vlans IDs and pvid 2–4093. Forbidden: Replace, vlan_id, untagged_vlans, mode, vlans, replace_untagged. See the full [action/PVID/tagged scenario table below](#edgeswitch-complete-action-x-taggedpvid-cases-template-15). All operations use `configure / interface 0/1 / <differences> / exit / exit`; No-op emits nothing.

Independent configured include/exclude/tagged/PVID are retained, including exclude 746 AND tagging 746. Tagging is never intersected away against membership for planning. Current/Configured/Tagging from show vlan are distinct; Current Exclude versus Configured Include never authorizes an automatic fix. Complete interface evidence through exit includes unrelated PoE/storm-control/MTU/BPDU/protected-port settings; no such commands render. Global VLAN absence gives VLAN_NOT_IN_DATABASE informational warning, never auto-creation. Existing Evidence contains only interface-scoped PVID, participation and tagging configuration; show vlan <ID> and global database evidence stay in immutable JSON for warnings/checks. Operational lookup uses reliable complete running-config fallback; contradictory reliable global observations and unknown config still block.

Earlier Remove then Add/Change explicitly replaces membership/tagging; PVID change then Remove frees the old PVID. For port-to-port changes, earlier Pending adds dependency blocker, Reject removes projected effect and can expose PVID-removal blocker. Compatible port pairs warn with source rows and project membership/tagging/PVID; unsafe pairs/owned LAG members/unknown parent block. Current PVID cannot be removed until an earlier approved row changes it. Optional description affects only supplied text. Repeated fully satisfied rows No-op safely while retaining overlap warnings.

**Engineer operating procedure for EdgeSwitch VLAN Port:**

1. In `bulk-input.xlsx`, select the **EdgeSwitch VLAN Port** worksheet, populate the exact fields shown above from row 3 (or later), and keep the credential workbook separate.
2. Run the **same v2 `plan` command** from Section 2. For predefined templates verify that live read-only collection identified the intended device, target object and current state; for Manual CLI no connection is performed.
3. Open the **EdgeSwitch VLAN Port** tab in generated `plan.xlsx`. Inspect the original entered values, Existing Evidence (if applicable), Proposed CLI, Live Validation, Consistency, Dependencies, No-op, Warnings, Blockers and Engineer Decision; compare the worked examples above against the actual evidence.
4. If invalid or blocked, repair the **input** or missing prerequisites/evidence and regenerate a fresh plan; do not edit the generated CLI/evidence. Record Pending/Approve/Reject only after review; no decision deploys the proposal.

**Approval:** Signed-off detailed contract; deterministic validation only. Hardware/software live validation remains owner-controlled.


### Template 16 — EdgeSwitch Description

Status: signed-off detailed contract; deterministic validation only, owner live validation pending.

| Input column | Requirement | Allowed values / forbidden values / example |
|---|---|---|
| `management_ip` | Required | IPv4/IPv6 literal; e.g. 192.0.2.91. No hostname, credentials or URL. |
| `interface` | Required | Existing explicit interface identifier; platform details and sample below. No whitespace except EdgeSwitch lag N; no shell metacharacters. |
| `description` | Required | Printable ASCII text with spaces/case, e.g. Customer Site Alpha; no secrets, quotes, semicolon or backslash. Blank optional preserves existing description. |

Required description; target example `0/1`. Catalyst requires full canonical FastEthernet/GigabitEthernet/TenGigabitEthernet/FortyGigabitEthernet/HundredGigE/Port-channel/Vlan/Loopback names with numeric slash components and optional numeric suffix; abbreviations like Gi1/0/1 are invalid. Other catalogue identifiers accept [A-Za-z0-9][A-Za-z0-9./:-]* (EdgeSwitch also lag N), but actual unambiguous observed existence is mandatory. Physical and supported logical/aggregate targets stay exact; no LAG redirect.

| Filled input (plus management_ip) and observed state | Expected result |
|---|---|
| interface=0/1; description=Customer Site Alpha; old/empty text | `configure / interface 0/1 / description "Customer Site Alpha" / exit / exit` |
| same input; matching text | No-op |
| same input; physical member of aggregate | Change exact member description only |
| description blank, target missing/ambiguous, or unreliable source | Invalid input or evidence blocker |
| same target in two rows; identical description | Later No-op, compatible overlap warning for approved families |
| same target in two rows; different descriptions | Ordered overlap blocker |

Evidence: exact interface declaration plus preserved configuration and original observed description, never redirected to aggregate. Approved Cisco keeps complete parent/child stanza through `!`; EdgeSwitch through `exit`, including unrelated PoE/MTU/STP/VLAN/PVID. VLAN defects can warn but no VLAN repair occurs. NCS540 provisional renderer retains `l2transport` when evidenced, and rejects unresolved declarations; NE05E remains provisional, with existing scoped facts rather than a new full-stanza guarantee. Provisional family overlap behavior is conservative, so do not assume the approved-family duplicate warning exemption.

**Engineer operating procedure for EdgeSwitch Description:**

1. In `bulk-input.xlsx`, select the **EdgeSwitch Description** worksheet, populate the exact fields shown above from row 3 (or later), and keep the credential workbook separate.
2. Run the **same v2 `plan` command** from Section 2. For predefined templates verify that live read-only collection identified the intended device, target object and current state; for Manual CLI no connection is performed.
3. Open the **EdgeSwitch Description** tab in generated `plan.xlsx`. Inspect the original entered values, Existing Evidence (if applicable), Proposed CLI, Live Validation, Consistency, Dependencies, No-op, Warnings, Blockers and Engineer Decision; compare the worked examples above against the actual evidence.
4. If invalid or blocked, repair the **input** or missing prerequisites/evidence and regenerate a fresh plan; do not edit the generated CLI/evidence. Record Pending/Approve/Reject only after review; no decision deploys the proposal.

**Approval:** Signed-off detailed contract; deterministic validation only. Hardware/software live validation remains owner-controlled.


### Template 17 — NCS540 L2VPN

Status: **catalogue/provisional, not owner-approved or live-validated**.

| Input column | Requirement | Allowed values / forbidden values / example |
|---|---|---|
| `management_ip` | Required | IPv4/IPv6 literal; e.g. 192.0.2.91. No hostname, credentials or URL. |
| `interface` | Required | Existing explicit interface identifier; platform details and sample below. No whitespace except EdgeSwitch lag N; no shell metacharacters. |
| `subinterface` | Required | Integer suffix: NCS540 0–2147483647; NE05E 1–4094. Parent field must omit the suffix to avoid accidental double suffix. |
| `encapsulation` | Required | Exact selector below; conditional outer/inner input rules apply. |
| `bridge_group` | Required | Nonempty CLI identifier [A-Za-z0-9][A-Za-z0-9./:-]*, e.g. CUSTOMER; no spaces. |
| `bridge_domain` | Required | EVC integer 1–4094 (ME excludes 1002–1005); NCS540 nonempty ASCII name [A-Za-z0-9_.:-]+, e.g. CUSTOMER-445. |
| `outer_vlan` | Conditional | Required for tagged encapsulation, forbidden for untagged. EVC compact inclusive ID/range/list 1–4094; NCS540 one integer 1–4094. No reversed range, ALL or NONE. |
| `inner_vlan` | Conditional | Required only for QinQ; forbidden otherwise. EVC ID/range/list 1–4094 or any (normalized to 1-4094); NCS540 one integer 1–4094. |
| `description` | Optional | Printable ASCII text with spaces/case, e.g. Customer Site Alpha; no secrets, quotes, semicolon or backslash. Blank optional preserves existing description. |

**Provisional existing implementation only.** encapsulation exactly dot1q, QinQ or untagged (different case from EVC). Numeric outer required except untagged; numeric inner only QinQ, each 1–4094. bridge_group and bridge_domain names are independent of tags. No rewrite/pop/push/group column is present; no implicit commit. Example parent GigabitEthernet0/0/0/1; subinterface=445.

| Filled input (plus management_ip/interface/subinterface above) | Expected proposal/result |
|---|---|
| encapsulation=dot1q; outer_vlan=445; bridge_group=CUSTOMER; bridge_domain=BD445 | `configure terminal / interface GigabitEthernet0/0/0/1.445 l2transport / encapsulation dot1q 445 / exit / l2vpn / bridge group CUSTOMER / bridge-domain BD445 / interface GigabitEthernet0/0/0/1.445 / end` |
| encapsulation=QinQ; outer_vlan=300; inner_vlan=200; same group/domain | Same hierarchy, `encapsulation dot1q 300 second-dot1q 200` |
| encapsulation=untagged; tags blank; same group/domain | Same hierarchy, `encapsulation untagged` |
| description=Customer with any valid case | Description before encapsulation under subinterface |
| existing exact ingress/description and same unique L2 attachment | No-op |
| existing routed target or attachment to another BD | ROUTED_SUBINTERFACE_CONVERSION / L2VPN_ATTACHMENT_CONFLICT |
| same outer ingress on sibling subinterface | Conservative INGRESS_TAG_OVERLAP blocker, even different QinQ inner |
| QinQ without inner, untagged with outer, subinterface=-1, pop_tags=1 | Invalid input |

Evidence uses shared IOS-XR configuration facts/audit relationship validation and existing declared interfaces; service references never invent targets. Missing actual parent/evidence or unresolved owner blocks. Provisional behavior does not provide the approved ME/ASR full-child recreation contract. Cross-row interface/domain overlaps remain conservative blockers; no approval or live forwarding support is inferred from renderer output.

**Engineer operating procedure for NCS540 L2VPN:**

1. In `bulk-input.xlsx`, select the **NCS540 L2VPN** worksheet, populate the exact fields shown above from row 3 (or later), and keep the credential workbook separate.
2. Run the **same v2 `plan` command** from Section 2. For predefined templates verify that live read-only collection identified the intended device, target object and current state; for Manual CLI no connection is performed.
3. Open the **NCS540 L2VPN** tab in generated `plan.xlsx`. Inspect the original entered values, Existing Evidence (if applicable), Proposed CLI, Live Validation, Consistency, Dependencies, No-op, Warnings, Blockers and Engineer Decision; compare the worked examples above against the actual evidence.
4. If invalid or blocked, repair the **input** or missing prerequisites/evidence and regenerate a fresh plan; do not edit the generated CLI/evidence. Record Pending/Approve/Reject only after review; no decision deploys the proposal.

**Approval:** Provisional catalogue implementation, not signed-off or hardware validated. Do not treat generated CLI as certified for production.


### Template 18 — NCS540 Description

Status: **catalogue/provisional, not owner-approved or live-validated**.

| Input column | Requirement | Allowed values / forbidden values / example |
|---|---|---|
| `management_ip` | Required | IPv4/IPv6 literal; e.g. 192.0.2.91. No hostname, credentials or URL. |
| `interface` | Required | Existing explicit interface identifier; platform details and sample below. No whitespace except EdgeSwitch lag N; no shell metacharacters. |
| `description` | Required | Printable ASCII text with spaces/case, e.g. Customer Site Alpha; no secrets, quotes, semicolon or backslash. Blank optional preserves existing description. |

Required description; target example `GigabitEthernet0/0/0/1.445`. Catalyst requires full canonical FastEthernet/GigabitEthernet/TenGigabitEthernet/FortyGigabitEthernet/HundredGigE/Port-channel/Vlan/Loopback names with numeric slash components and optional numeric suffix; abbreviations like Gi1/0/1 are invalid. Other catalogue identifiers accept [A-Za-z0-9][A-Za-z0-9./:-]* (EdgeSwitch also lag N), but actual unambiguous observed existence is mandatory. Physical and supported logical/aggregate targets stay exact; no LAG redirect.

| Filled input (plus management_ip) and observed state | Expected result |
|---|---|
| interface=GigabitEthernet0/0/0/1.445; description=Customer Site Alpha; old/empty text | `configure terminal / interface GigabitEthernet0/0/0/1.445 / description Customer Site Alpha / end` |
| same input; matching text | No-op |
| same input; physical member of aggregate | Change exact member description only |
| description blank, target missing/ambiguous, or unreliable source | Invalid input or evidence blocker |
| same target in two rows; identical description | Later No-op, compatible overlap warning for approved families |
| same target in two rows; different descriptions | Ordered overlap blocker |

Evidence: exact interface declaration plus preserved configuration and original observed description, never redirected to aggregate. Approved Cisco keeps complete parent/child stanza through `!`; EdgeSwitch through `exit`, including unrelated PoE/MTU/STP/VLAN/PVID. VLAN defects can warn but no VLAN repair occurs. NCS540 provisional renderer retains `l2transport` when evidenced, and rejects unresolved declarations; NE05E remains provisional, with existing scoped facts rather than a new full-stanza guarantee. Provisional family overlap behavior is conservative, so do not assume the approved-family duplicate warning exemption.

**Engineer operating procedure for NCS540 Description:**

1. In `bulk-input.xlsx`, select the **NCS540 Description** worksheet, populate the exact fields shown above from row 3 (or later), and keep the credential workbook separate.
2. Run the **same v2 `plan` command** from Section 2. For predefined templates verify that live read-only collection identified the intended device, target object and current state; for Manual CLI no connection is performed.
3. Open the **NCS540 Description** tab in generated `plan.xlsx`. Inspect the original entered values, Existing Evidence (if applicable), Proposed CLI, Live Validation, Consistency, Dependencies, No-op, Warnings, Blockers and Engineer Decision; compare the worked examples above against the actual evidence.
4. If invalid or blocked, repair the **input** or missing prerequisites/evidence and regenerate a fresh plan; do not edit the generated CLI/evidence. Record Pending/Approve/Reject only after review; no decision deploys the proposal.

**Approval:** Provisional catalogue implementation, not signed-off or hardware validated. Do not treat generated CLI as certified for production.


### Template 19 — NE05E VLAN Database

Status: **catalogue/provisional, not owner-approved or live-validated**.

| Input column | Requirement | Allowed values / forbidden values / example |
|---|---|---|
| `management_ip` | Required | IPv4/IPv6 literal; e.g. 192.0.2.91. No hostname, credentials or URL. |
| `vlan_id` | Required | One integer VLAN ID; family bounds below. No list/range, ALL, 0 or 4095. |
| `name` | Required | Family-specific VLAN name limits below; no empty name, quotes, semicolon or backslash. |

Bounds: 1–4094; name =80 ASCII characters including spaces. VLAN 445,545 or 200-100 in vlan_id is invalid. Empty/overlong names block; Customer Site is invalid on Cisco, valid on EdgeSwitch/NE05E within length bounds.

| Filled input (plus management_ip) and observed state | Expected result |
|---|---|
| vlan_id=901; name=Customer; absent global VLAN | `system-view / vlan 901 / description Customer / quit / quit` |
| vlan_id=901; name=Customer; existing name Customer | No-op, empty CLI |
| vlan_id=901; name=Customer; existing name Old | Rename with VLAN_RENAME_IMPACT; same CLI, no deletion |
| vlan_id=0; name=Customer | Invalid input, no CLI |
| vlan_id=901; name=Customer; unknown evidence | Blocked; never infer absent |

Provisional NE05E uses observed explicit global VLAN objects and their description, not VSI references; read-only saved-configuration facts supply evidence. No approved operational lookup/fallback contract is claimed. Rename impact is a finding that currently blocks readiness, unlike approved Cisco/EdgeSwitch warning semantics. Same-device same-ID rows overlap and block; an earlier approved database proposal can support later shared dependencies.

**Engineer operating procedure for NE05E VLAN Database:**

1. In `bulk-input.xlsx`, select the **NE05E VLAN Database** worksheet, populate the exact fields shown above from row 3 (or later), and keep the credential workbook separate.
2. Run the **same v2 `plan` command** from Section 2. For predefined templates verify that live read-only collection identified the intended device, target object and current state; for Manual CLI no connection is performed.
3. Open the **NE05E VLAN Database** tab in generated `plan.xlsx`. Inspect the original entered values, Existing Evidence (if applicable), Proposed CLI, Live Validation, Consistency, Dependencies, No-op, Warnings, Blockers and Engineer Decision; compare the worked examples above against the actual evidence.
4. If invalid or blocked, repair the **input** or missing prerequisites/evidence and regenerate a fresh plan; do not edit the generated CLI/evidence. Record Pending/Approve/Reject only after review; no decision deploys the proposal.

**Approval:** Provisional catalogue implementation, not signed-off or hardware validated. Do not treat generated CLI as certified for production.


### Template 20 — NE05E Subinterface VSI

Status: **catalogue/provisional, not owner-approved or live-validated**.

| Input column | Requirement | Allowed values / forbidden values / example |
|---|---|---|
| `management_ip` | Required | IPv4/IPv6 literal; e.g. 192.0.2.91. No hostname, credentials or URL. |
| `interface` | Required | Existing explicit interface identifier; platform details and sample below. No whitespace except EdgeSwitch lag N; no shell metacharacters. |
| `subinterface` | Required | Integer suffix: NCS540 0–2147483647; NE05E 1–4094. Parent field must omit the suffix to avoid accidental double suffix. |
| `vlan_id` | Required | One integer VLAN ID; family bounds below. No list/range, ALL, 0 or 4095. |
| `encapsulation` | Required | Exact selector below; conditional outer/inner input rules apply. |
| `vsi` | Required | Existing VSI identifier [A-Za-z0-9][A-Za-z0-9./:-]*, e.g. CUSTOMER; no spaces or implicit creation. |
| `description` | Optional | Printable ASCII text with spaces/case, e.g. Customer Site Alpha; no secrets, quotes, semicolon or backslash. Blank optional preserves existing description. |
| `control_vid` | Conditional | Optional integer 1–4094 only with dot1q termination; forbidden with vlan-type dot1q. |

**Provisional existing implementation only.** Parent example GigabitEthernet0/1/0; subinterface=445; vlan_id integer 1–4094. encapsulation exactly dot1q termination or vlan-type dot1q; no QinQ. Existing VSI required; no VSI creation. Optional control_vid only for dot1q termination, integer 1–4094.

| Filled input (plus management_ip/interface/subinterface above) | Expected proposal/result |
|---|---|
| vlan_id=445; encapsulation=dot1q termination; vsi=CUSTOMER | `system-view / interface GigabitEthernet0/1/0.445 / dot1q termination vid 445 / l2 binding vsi CUSTOMER / quit / quit` |
| same plus control_vid=446; description=Customer | Description then `control-vid 446 dot1q-termination` before termination/binding |
| vlan_id=445; encapsulation=vlan-type dot1q; vsi=CUSTOMER | `system-view / interface GigabitEthernet0/1/0.445 / vlan-type dot1q 445 / l2 binding vsi CUSTOMER / quit / quit` |
| exact existing encapsulation/VSI/requested optional settings | No-op |
| VSI absent | EXISTING_VSI_REQUIRED blocker; no implicit creation |
| existing other encapsulation or VSI | SUBINTERFACE_ENCAPSULATION_CONVERSION / VSI_BINDING_CHANGE blockers |
| vlan-type dot1q plus control_vid; QinQ; subinterface=0; vlan_id=4095 | Invalid input |

Shared Huawei saved configuration and audit supply declared-interface/termination/VSI evidence. Missing actual parent or unreliable observation blocks. VLAN global database declaration and VSI existence are separate. Same-resource overlaps remain conservative blockers; optional description blank preserves. No new read-only commands, approval or firmware support are claimed by this reference.

**Engineer operating procedure for NE05E Subinterface VSI:**

1. In `bulk-input.xlsx`, select the **NE05E Subinterface VSI** worksheet, populate the exact fields shown above from row 3 (or later), and keep the credential workbook separate.
2. Run the **same v2 `plan` command** from Section 2. For predefined templates verify that live read-only collection identified the intended device, target object and current state; for Manual CLI no connection is performed.
3. Open the **NE05E Subinterface VSI** tab in generated `plan.xlsx`. Inspect the original entered values, Existing Evidence (if applicable), Proposed CLI, Live Validation, Consistency, Dependencies, No-op, Warnings, Blockers and Engineer Decision; compare the worked examples above against the actual evidence.
4. If invalid or blocked, repair the **input** or missing prerequisites/evidence and regenerate a fresh plan; do not edit the generated CLI/evidence. Record Pending/Approve/Reject only after review; no decision deploys the proposal.

**Approval:** Provisional catalogue implementation, not signed-off or hardware validated. Do not treat generated CLI as certified for production.


### Template 21 — NE05E Description

Status: **catalogue/provisional, not owner-approved or live-validated**.

| Input column | Requirement | Allowed values / forbidden values / example |
|---|---|---|
| `management_ip` | Required | IPv4/IPv6 literal; e.g. 192.0.2.91. No hostname, credentials or URL. |
| `interface` | Required | Existing explicit interface identifier; platform details and sample below. No whitespace except EdgeSwitch lag N; no shell metacharacters. |
| `description` | Required | Printable ASCII text with spaces/case, e.g. Customer Site Alpha; no secrets, quotes, semicolon or backslash. Blank optional preserves existing description. |

Required description; target example `GigabitEthernet0/1/0`. Catalyst requires full canonical FastEthernet/GigabitEthernet/TenGigabitEthernet/FortyGigabitEthernet/HundredGigE/Port-channel/Vlan/Loopback names with numeric slash components and optional numeric suffix; abbreviations like Gi1/0/1 are invalid. Other catalogue identifiers accept [A-Za-z0-9][A-Za-z0-9./:-]* (EdgeSwitch also lag N), but actual unambiguous observed existence is mandatory. Physical and supported logical/aggregate targets stay exact; no LAG redirect.

| Filled input (plus management_ip) and observed state | Expected result |
|---|---|
| interface=GigabitEthernet0/1/0; description=Customer Site Alpha; old/empty text | `system-view / interface GigabitEthernet0/1/0 / description Customer Site Alpha / quit / quit` |
| same input; matching text | No-op |
| same input; physical member of aggregate | Change exact member description only |
| description blank, target missing/ambiguous, or unreliable source | Invalid input or evidence blocker |
| same target in two rows; identical description | Later No-op, compatible overlap warning for approved families |
| same target in two rows; different descriptions | Ordered overlap blocker |

Evidence: exact interface declaration plus preserved configuration and original observed description, never redirected to aggregate. Approved Cisco keeps complete parent/child stanza through `!`; EdgeSwitch through `exit`, including unrelated PoE/MTU/STP/VLAN/PVID. VLAN defects can warn but no VLAN repair occurs. NCS540 provisional renderer retains `l2transport` when evidenced, and rejects unresolved declarations; NE05E remains provisional, with existing scoped facts rather than a new full-stanza guarantee. Provisional family overlap behavior is conservative, so do not assume the approved-family duplicate warning exemption.

**Engineer operating procedure for NE05E Description:**

1. In `bulk-input.xlsx`, select the **NE05E Description** worksheet, populate the exact fields shown above from row 3 (or later), and keep the credential workbook separate.
2. Run the **same v2 `plan` command** from Section 2. For predefined templates verify that live read-only collection identified the intended device, target object and current state; for Manual CLI no connection is performed.
3. Open the **NE05E Description** tab in generated `plan.xlsx`. Inspect the original entered values, Existing Evidence (if applicable), Proposed CLI, Live Validation, Consistency, Dependencies, No-op, Warnings, Blockers and Engineer Decision; compare the worked examples above against the actual evidence.
4. If invalid or blocked, repair the **input** or missing prerequisites/evidence and regenerate a fresh plan; do not edit the generated CLI/evidence. Record Pending/Approve/Reject only after review; no decision deploys the proposal.

**Approval:** Provisional catalogue implementation, not signed-off or hardware validated. Do not treat generated CLI as certified for production.


### Template 22 — Manual CLI

Status: **catalogue/provisional, not owner-approved or live-validated**.

| Input column | Requirement | Allowed values / forbidden values / example |
|---|---|---|
| `management_ip` | Required | IPv4/IPv6 literal; e.g. 192.0.2.91. No hostname, credentials or URL. |
| `platform` | Required | Exactly cisco_ios, cisco_xe, cisco_xr, huawei_vrp or ubiquiti_edgeswitch. |
| `mode` | Required | Exactly configuration, interface or service; metadata only, no wrapper generation. |
| `scope` | Required | Printable ASCII 1–256 affected-resource metadata; e.g. interface GigabitEthernet0/1. Not interpreted as CLI. |
| `commands` | Required | Literal multiline printable ASCII up to 16000 including CR/LF/tab; no secrets. Full hierarchy is engineer responsibility; no semantic safety claim. |

**Provisional catalogue semantics, not owner-approved/live-validated.** No device connection or evidence collection even with Approve. Explicit scope/mode are metadata, not inferred hierarchy. The literal command string is preserved including whitespace/newlines; no wrapper, save or commit is added, no semantic safety check or allowlisted effect validation is claimed. Secret screening/bounded structure still apply.

| Filled input (plus management_ip) | Expected result |
|---|---|
| platform=cisco_ios; mode=configuration; scope=interface GigabitEthernet0/1; commands multiline: configure terminal, interface GigabitEthernet0/1, description Customer, end | Exactly those four literal lines; MANUAL_EFFECTS_UNKNOWN, not_live_validated, impact unknown, not deployment-ready even Approve |
| platform=cisco_xr; mode=service; scope=CUSTOMER; commands=description Customer | Literal text only; mode/scope never add missing hierarchy or commit |
| platform=huawei_vrp; mode=interface; scope=GigabitEthernet0/1/0; commands=description Customer | Literal text only; no system-view/interface wrapper |
| mode=exec, platform=ios, blank scope/commands or commands containing credentials | Invalid input, no CLI artifact |
| Manual row plus another same-device row | Conservative overlap conflict; effects cannot be projected safely |

No No-op semantics are inferred, no fallback exists, and observation supplied for a Manual-only target is not evidence of validation. JSON/Excel decisions and digest checks are the same ordinary offline surface; no elevated approver role is introduced. V1 Manual allowlists remain unchanged in the separate v1 API.

**Engineer operating procedure for Manual CLI:**

1. In `bulk-input.xlsx`, select the **Manual CLI** worksheet, populate the exact fields shown above from row 3 (or later), and keep the credential workbook separate.
2. Run the **same v2 `plan` command** from Section 2. For predefined templates verify that live read-only collection identified the intended device, target object and current state; for Manual CLI no connection is performed.
3. Open the **Manual CLI** tab in generated `plan.xlsx`. Inspect the original entered values, Existing Evidence (if applicable), Proposed CLI, Live Validation, Consistency, Dependencies, No-op, Warnings, Blockers and Engineer Decision; compare the worked examples above against the actual evidence.
4. If invalid or blocked, repair the **input** or missing prerequisites/evidence and regenerate a fresh plan; do not edit the generated CLI/evidence. Record Pending/Approve/Reject only after review; no decision deploys the proposal.

**Approval:** Provisional catalogue implementation, not signed-off or hardware validated. Do not treat generated CLI as certified for production.

## 5. Cross-template worked scenarios

### A. Create VLAN and configure a C3750X access interface

Use **C3750X VLAN Database** first (e.g. `management_ip=192.0.2.10; vlan_id=445; name=Customer`) and **C3750X Access Port** later (e.g. `management_ip=192.0.2.10; interface=GigabitEthernet1/0/1; vlan_id=445; description=Customer`). A reliably absent VLAN yields a VLAN creation proposal; the dependent access request carries a VLAN prerequisite. **Pending or Reject on the database row does not satisfy deployment readiness**. Approved prerequisites influence projected planning state only, not real-device state. Inspect the generated JSON dependency IDs and both workbook rows before recording decisions.

### B. Modify an existing C3750X trunk

Use **C3750X Trunk Port**. Specify `action=Add`, `Remove` or `Replace` and a list/range of VLANs. Compare effective allowed VLANs and native VLAN against observed configuration. An unsafe conversion, member/aggregate ownership conflict or Add without the required explicit baseline is **blocked**; do not infer a safe conversion from a rendered CLI. The section for Template 3 contains exact request examples and expected commands.

### C. Create or update a ME3600X / ASR920 EVC

Use the family-specific **EVC** worksheet. Specify independent `service_instance_id`, `encapsulation` and `bridge_domain` fields; provide `outer_vlan`, `inner_vlan`, `rewrite` and `push_vlan` as required by the documented matrix. The planner proposes **no service instance <ID>** followed by complete child recreation; blank optional child settings can be removed. Check parent compatibility, existing child differences, service impact, global BD/VLAN prerequisites (particularly ME3600X), and any blocked rewrite combination before any decision.

### D. Change EdgeSwitch tagging and PVID

Choose **EdgeSwitch VLAN Port** with `action=Add/Change` or `Remove`. `tagged_vlans` accepts single/list/range expressions; an optional independent `pvid` can be set with Add/Change. Remove cannot include PVID and must not remove the active PVID without an earlier approved change. Compare VLAN participation, tagging, PVID and the generated command order against the collected evidence.

## 6. Understanding warnings, blockers and review decisions

| Condition | Meaning | Engineer response |
|---|---|---|
| No-op | Requested state already matches reliable observed/projection state | Confirm evidence and inspect other blockers; expect empty proposed CLI |
| Warning | Potential service impact, missing VLAN or nonfatal observation issue | Review and document intended dependency/impact |
| Blocker | Unsafe conversion, identity/ownership uncertainty, incompatible state or unsatisfied requirement | Do not assume readiness; correct input/state/evidence and re-plan |
| Invalid row | Workbook field or value is rejected | Correct **input** row and generate a new plan |
| Unavailable/stale evidence | The tool cannot establish a safe current baseline | Repair read-only connectivity or renew reliable observations |
| Pending/Approve/Reject | **Offline** engineer decisions | Does not authenticate an engineer, authorize apply, or override blockers |

For Templates 1–16, output sheets retain the common review fields; internal row IDs, evidence digests, detailed projected state and some conflict provenance are in `plan.json`. Keep the JSON/XLSX pair together. Decision integrity is checked by the underlying library `workbook.consume_decisions`; there is **no standalone v2 CLI command** for decision consumption or deployment.

## 7. Troubleshooting

- **`Planning failed (<category>)`, exit 2:** Check sanitized `bulk_planning.log`, output-file collision, invalid workbook layout, config/credential file availability, and missing required Teleport routing. Do not publish passwords or raw device output.
- **Device unavailable / evidence missing:** Check matching unique credentials row, interactive `tsh` authentication, supplied proxy/cluster/bastion settings, Linux key/certificate identity, device identity and read-only CLI support. Isolate to one target with `--max-concurrent-devices 1`.
- **`GLOBAL_VLAN_REQUIRED` or missing VLAN:** Check the actual VLAN database; if creation is intended, use the VLAN Database template earlier in worksheet order and review dependency approvals. This does not auto-create VLANs.
- **`ACCESS_CONVERSION_BLOCKED`, `PHYSICAL_PORT_CHANNEL_MEMBER` or ownership findings:** Verify interface mode and actual aggregate owner; do not bypass blocking with manual edits to proposed CLI.
- **Overlapping requests:** Inspect source worksheet/row references and consolidated final intent. Compatible description overlap may warn; competing access/trunk changes, incompatible EVC ingress and duplicate conflicting changes block.
- **Unexpected No-op or absence:** Validate the evidence freshness/reliability. Unknown or incomplete sources are not proof of absence.
- **Edited output workbook rejected by a future API consumer:** Only Engineer Decision cells are mutable. Keep original inputs/evidence and `plan.json` unchanged and bind to a trusted digest.

## 8. Validation and reference notes

The template inputs and example outcomes in this guide are transcribed from the **current source/test-linked operator reference** and reconciled with v2 catalogue/CLI schema; they are **illustrative expected plans, not recorded live test output**. Some existing historical manual text may describe unmerged branches; this guide uses current `main` as the implementation boundary. Runtime/network changes, production validation and all proposed CLI execution remain outside this documentation-only change.

Further reading: [Bulk planning v2 manual](bulk-configuration-planning.md) · [Complete technical template reference](../operations/configuration-template-reference.md) · [User manual index](README.md) · [Current implementation status](../CURRENT_STATE.md).


Issue #156 approved design: [separate Manual Configuration](../architecture/configuration/manual-configuration.md) supersedes legacy offline Manual CLI for new input generation only. Legacy plans remain offline/non-executable; predefined partial-save behavior is unchanged. The new optional profile password-hash section and success-only per-row save are implemented on this branch with synthetic deterministic tests; owner-operated live validation remains pending. Historical evidence above is retained.

## Owner-approved usability revision — implemented on this branch

Issue #156 now accepts blank command-cell separator lines while retaining literal nonblank
commands and original line numbers. Manual input selection lists only manual_*.xlsx
newest first, with explicit-path fallback. Each device publishes its own short
manual_output_YYYYMMDD_HHMMSS.xlsx report as soon as its task ends; collision suffixes
and device directories disambiguate outputs. Its continuously flushed receive-only
UTF-8 capture lives alongside the report under outputs/reports/manual_configuration/.
Reports link to real captures using portable relative hyperlinks. Structured timing,
row identity and send intents remain in the internal run journal. Legacy recovery
retains real historical capture references; missing captures have no invented link.
This supersedes timestamped/labelled captures, run-directory capture defaults, blank-line
rejection and batch-only export. Existing authorization and device safety rules remain.
No live validation is implied.
