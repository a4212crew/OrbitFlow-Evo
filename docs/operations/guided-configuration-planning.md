# Guided bulk configuration planning (C1–C4)

This workflow creates **offline candidates only**. It never opens a device
connection, performs live prechecks, applies CLI, saves/commits configuration,
backs up a device, or implements rollback/resume. Inventory is latest-known
identity evidence, not current configuration. Operator workbook validation is
required before merge approval. Automated synthetic validation is not that signoff.

## Initial catalogue version 1

| Action entered by engineer | Compatible platform/family/profile | Parameters | Selection |
|---|---|---|---|
| `access port` | IOS C3750X/c3750x_switching or XE C3850/c3850_switching, classic_switchport flag | Required `vlan`; optional `description` | cisco.access v1 |
| `trunk VLAN add` | Same Catalyst profiles | Required comma-separated `vlans` | cisco.trunk.add v1 |
| `trunk VLAN replace` | Same Catalyst profiles | Required comma-separated `vlans` | cisco.trunk.replace v1 |
| `EVC` | IOS ME3600X/me3600x_evc or XE ASR920/asr920_evc, evc flag | Required `service_instance`, `outer_vlan`, `bridge_domain`; optional `inner_vlan`, parent-interface `description` | Engineer chooses cisco.evc.local/M03 or cisco.evc.global/M02 v1 |
| `tagged subinterface` | Huawei VRP NE05E/ne05e, dot1q_subinterface flag | Required `vlan`; optional `description` | huawei.dot1q/M08 v1 |
| `manual CLI` | Explicit inventory identity and interface; advanced review only | Literal ordered lines in Manual | No template or inferred safe effects |

No other template is implemented: EdgeSwitch, IOS-XR attachments, VSI/QinQ,
removal and automatic methodology remediation remain unsupported. Flags, family
and OS must all match. Catalogue versions are code-owned immutable definitions;
new syntax/parameter semantics require a new template/catalogue version.

VLANs are 2–4094, excluding 1002–1005. Lists accept comma-separated integers,
not ranges/all/except, and contain at most 256 distinct input entries. SI and BD
IDs are independently required integers 1–4094. The only approved optional
defaults are omission of description and inner tag. SI, VLAN and BD are never
inferred from one another. No template changes shutdown state or creates a VLAN
database object implicitly. Referenced resources and interface prerequisites
must be verified in a future separately qualified live workflow.

Use full canonical interface names, e.g. `GigabitEthernet1/0/1`, not `Gi1/0/1`.
Cisco templates here target explicit physical/aggregate interfaces. Huawei
requires an explicitly entered subinterface such as `GigabitEthernet0/1/1.3500`;
the workflow never derives an interface from a service/VLAN reference. Interface
existence and hardware/release support are unverified offline preconditions.

## Operator commands and synthetic workbooks

From the repository root with its Python dependencies and `src` on PYTHONPATH
(the same environment used by existing scripts):

```powershell
$env:PYTHONPATH = "$PWD/src"
python scripts/configuration_samples.py --output outputs/validation/configuration-guided-sample
```

The generator uses documentation IPs and synthetic identities only. It writes:

- `inventory.json`: three synthetic snapshots, never production inventory.
- `requests.xlsx`: six mixed-device intent rows; no template IDs required.
- `guided.xlsx` and `guided.json`: generated action-specific fields and bound provenance.
- `completed.xlsx` and `completed.json`: an example engineer completion with local/global EVC selection, two templates and ordered advanced CLI on an interface.
- `conflicts.xlsx`: add/replace conflict, missing device, unsupported profile inputs.

Directories/files are exclusively created. For another run use new paths and a
new batch ID. Do not overwrite reviewed artifacts.

Exercise prepare independently (expect six rows, EVC choices empty, required
fields empty, and optional defaults clearly shown):

```powershell
python scripts/configuration_job.py prepare outputs/validation/configuration-guided-sample/requests.xlsx --inventory outputs/validation/configuration-guided-sample/inventory.json --output outputs/validation/configuration-guided-sample/operator-guided.xlsx
```

Open `operator-guided.xlsx` in Excel. Retain its sibling `.json`. Fill values in
Parameters for the selected template only; choose each EVC template/version in
Requests using Choices. Assign unique per-device positive `order` values and
optional comma-separated predecessor row IDs in `depends_on`. Dependencies must
exist on that device and have smaller order values. Workbook row sorting does
not change operation order or source provenance. Leave source identity/action
fields unchanged; a new intent or inventory snapshot requires prepare again.

For manual CLI, use a separate request row on the same interface, then fill its
generated Manual reference, positive line order and literal command cells.
Prepare generates a reference/blank command row if no reference was supplied.
Manual CLI does not implicitly enter an interface context: include exact context
commands when required. Never paste credentials, raw device captures or opaque
payloads. Credential markers and known sensitive constructs are rejected before
output; no lexical filter can recognize arbitrary unlabeled secrets.

Plan the supplied completion for a reproducible acceptance example:

```powershell
python scripts/configuration_job.py plan outputs/validation/configuration-guided-sample/completed.xlsx --inventory outputs/validation/configuration-guided-sample/inventory.json --batch-id SAMPLE-C1-C4
python scripts/configuration_job.py validate-batch outputs/runs/configuration/SAMPLE-C1-C4/manifest.json
python -m orbitflow.configuration.cli validate outputs/runs/configuration/SAMPLE-C1-C4/plan-0001.json
```

Expected: three per-device plans, six input outcomes, a bound `manifest.json`,
and `configuration_preview_SAMPLE-C1-C4.xlsx`. The preview contains Summary,
Inputs (all failures/exclusions and plan paths/digests), Operations, ordered
CLI Preview (template/manual source), Findings, and Checks. EVC/Huawei plans are
`offline_validated`; the Catalyst plan is `review_required` because manual
effects are unknown. No artifact is execution-authorized.

Plan your own completion with a distinct batch ID:

```powershell
python scripts/configuration_job.py plan outputs/validation/configuration-guided-sample/operator-guided.xlsx --inventory outputs/validation/configuration-guided-sample/inventory.json --batch-id OPERATOR-C1-C4
```

For the negative exercise:

```powershell
python scripts/configuration_job.py prepare outputs/validation/configuration-guided-sample/conflicts.xlsx --inventory outputs/validation/configuration-guided-sample/inventory.json --output outputs/validation/configuration-guided-sample/conflict-guided.xlsx
# In Excel set both generated vlans value cells to 3500,3501.
python scripts/configuration_job.py plan outputs/validation/configuration-guided-sample/conflict-guided.xlsx --inventory outputs/validation/configuration-guided-sample/inventory.json --batch-id CONFLICT-C1-C4
```

Expect status 2 and retained artifacts: the known add/replace conflict blocks
the Catalyst plan; unresolved/unsupported rows remain visible. `skip` and
`reject` decisions also remain visible and conservatively block other operations
on that device. Reprepare a corrected request to obtain a complete device plan.
Failures on another identifiable device do not block an independent device.
Unmapped additional workbook rows block every generated plan. Missing required
rows, duplicate IDs/parameters, formulas, invalid values and changed inventory
fail closed. Malformed workbook structure returns status 2 before output.
The bounded initial importer accepts at most 20,000 rows and 40 columns per
sheet, 1,000 operations per device and 100 manual lines per operation. Oversized
workbooks require separate offline jobs; no batch execution/resume is implied.

## Offline review and immutable artifacts

v2 reuses `ChangePlan`, `save_plan`, `load_plan` and `ApprovalStore`; v1 remains
unchanged. The versioned closed schema re-renders every operation and recomputes
findings on load. Exact request/completed file hashes, prepared-source hash,
inventory snapshot hash, catalogue/template versions, identity, order,
dependencies, effects, checks and offline policy are included in the plan digest.
The prepared `.json` binds normalized row identity to the guided workbook.
It is content-integrity evidence, not an authenticated engineer signature.

The canonical batch manifest binds plan membership and all input outcomes.
`validate-batch` checks each plan's content digest, batch/source binding and
operation-to-input correspondence. Changing a workbook creates new plan digests
and requires fresh review; workbook edits never amend an approved artifact.

Review the exact JSON and preview, copy its actual digest, then use the existing
local authority (replace the example path/digest/expiry as appropriate):

```powershell
python -m orbitflow.configuration.cli preview outputs/runs/configuration/SAMPLE-C1-C4/plan-0001.json
python -m orbitflow.configuration.cli approve outputs/runs/configuration/SAMPLE-C1-C4/plan-0001.json --actor engineer --digest <reviewed-sha256> --expires-at 2099-01-01T00:00:00+00:00
python -m orbitflow.configuration.cli verify-approval outputs/runs/configuration/SAMPLE-C1-C4/plan-0001.json
python -m orbitflow.configuration.cli reject outputs/runs/configuration/SAMPLE-C1-C4/plan-0001.json --actor engineer
```

Use a suitable short expiry in practice. Blocked plans cannot be approved.
Review-required plans may receive an **offline review decision**, which does
not resolve unknown effects or authorize execution. The CLI labels v2 approval
verification accordingly. `ApprovalStore.verify()` rejects v2 by default;
`offline_review=True` explicitly verifies only a local review record. All v2
plans have execution authorization fixed false. Actor labels are not
authenticated elevated approval; no advanced execution authority exists here.
Existing authority integrity/expiry/rejection rules still apply.

Conflict analysis is deliberately bounded. It detects duplicate/overlapping EVC
services, incompatible interface operations, duplicate VLAN additions,
add/replace collisions, selected known manual contradictions, and conflicting
descriptions. Parent/child interactions require review. Every manual line retains
unknown effects, even when a known contradiction is also detected. It never
silently overrides a template, guesses full device state, or claims free-form
CLI is safe. Separate future C5/C6 work must qualify live prechecks, hardware,
authenticated approvals and execution policy; parallel/skip/pause/resume remains
design only.

## Validation and merge prerequisite

```powershell
python -m pytest tests/test_configuration_plans.py tests/test_configuration_guided.py tests/test_device_inventory.py -q
```

Tests disable sockets/subprocesses for the guided workflow and exercise typing,
identity, ambiguity, mixed operations, conflicts, secret rejection, immutable
digests, approvals and batch tampering. Workbook tests reopen saved files and
check values, source binding, literal cells and expected sheets.

**Pending operator signoff:** open the generated guided and consolidated preview
workbooks in Excel, complete the positive and negative exercises, confirm field
usability and readable ordered CLI, and record outcomes before merge approval.
No interactive Excel or live-device validation is claimed by the automated run.
