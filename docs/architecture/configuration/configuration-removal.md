# Configuration Removal and Service Retirement — Proposed

Status: **design only**. No CLI removal template, bulk-removal planner, live
execution, verified rollback, or removal pre-approval is implemented.

Reference: operator-provided `VLAN Configuration Methodologies - Creation and Removal.xlsx`.
The workbook's `Removal Templates` (RM-series), `Removal Workflow` (D-series)
and `Removal Acceptance Cases` (T-series) are design/test inputs. They must be
reviewed against supported hardware/software and validated configuration
backups. Do not copy example CLI into a live executor without vendor tests.

## Separation of intent and scope

Distinguish `create`, `update`, `detach`, `remove` and `retire`.
A request MUST name the exact device/interface/service and targeted relation
or object. Removing an allowed VLAN from a trunk, replacing an access VLAN,
detaching a bridge-domain member, removing a service instance, and deleting a
shared VLAN/bridge domain/VSI are **different operations** requiring distinct
plans, validations and approval classes. A narrow request must never expand
into a shared-object deletion. Removal may cause traffic loss even when syntax
is valid; explicit authorised intent is required.

## Evidence and dependency checks

1. Read a fresh, complete, appropriately protected configuration and resolve
   target identity, capability profile, family, software, method M01–M07,
   exact interface/service keys and configuration snapshot digest.
2. Preserve observed configured *and effective* membership. Consider implicit
   all, explicit lists, exclusions, native VLAN/PVID, data/voice VLAN, LAG
   inheritance, defaults and dormant settings. `no` or `undo` may restore a
   default instead of deleting the effective service mapping.
3. Build reverse references from the existing observation/configuration facts:
   switchport database consumption, EVC service-instance ↔ global/local BD,
   XR bridge-group/BD ↔ attachment, Huawei termination ↔ VSI, EdgeSwitch
   participation/tagging, and related retained services. Separate active,
   dormant, missing and ambiguous references; lack of evidence is not proof of
   no dependencies.
4. Block shared-object deletion if any relevant consumer remains, references
   are unresolved, the source is stale/incomplete, or ownership is uncertain.
   Require explicit replacement service or retirement decision for an access
   membership. Protect management, native/PVID and unrelated customer services.
5. Render minimal, scope-limited changes; never infer deletion from desired
   absence in a compliance report. Do not silently remove unrelated object
   membership, change interface mode or create a new implicit default state.

## Planning, approval and execution boundaries

- The future plan contract must bind action, exact target/scope, reference
  evidence, source digest, dependencies, preserved-state invariants, resulting
  state, exact command sequence, vendor/firmware applicability, change risk,
  maintenance constraints, explicit recovery/unknown-outcome policy and all
  authorisation evidence in the immutable approved digest.
- Pre-approved standard-create/update templates do **not** authorise removal.
  Destructive or shared-object changes default to explicit elevated review
  until narrowly scoped removal templates are separately certified and approved.
- Excel bulk removal uses stable row IDs and per-device plans. Analyse
  dependencies **across rows**, distinguish independently safe subsets from
  coupled transactions, never silently omit invalid targets, and make the
  resulting batch membership/exclusions explicit in the approval digest.
- A future Phase 3 must repeat live identity/current-state/dependency checks,
  complete mandatory backups, enforce ordering and stop conditions, verify
  outcomes and persist only after verification. A backup alone does not
  constitute tested rollback; do not automatically synthesize inverse CLI.

## Workbook-to-tests mapping

Use the workbook's RM/D/T identifiers for traceable, deterministic fixtures:

- Trunk membership delta on restricted and implicit-all trunks must preserve
  every unrelated VLAN and reject accidental unrestricted/default behaviour.
- Access membership withdrawal requires a declared replacement or explicit
  service retirement and a platform-tested resulting state.
- EVC global/local binding detachment differs from service-instance deletion;
  neither silently deletes shared BD objects. Mixed/unresolved mappings block.
- XR bridge-domain detachment must preserve unrelated attachments and account
  for candidate/commit behavior; platform eligibility is mandatory.
- Huawei VLAN termination and VSI removal must prove remaining consumers and
  preserve independent services and parent/subinterface ownership.
- EdgeSwitch participation/tagging/PVID changes preserve other membership
  and effective tagging. Model command order and saved versus effective state.
- Test reverse-reference conflicts, stale snapshots, missing evidence, bulk
  cross-row conflicts, unsupported firmware, uncertain rollback, and aborted
  partial execution. Existing VLAN and interface VLAN compliance outputs
  remain regression-locked.
