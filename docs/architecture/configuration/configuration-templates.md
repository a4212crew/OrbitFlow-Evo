# Deterministic Configuration Templates — Proposed

Templates support **new service configuration**, not just remediation. A reviewed template has an identifier and immutable version, supported device families/operations, typed input schema, required preconditions, rendering logic and expected postconditions.

Example: `ensure_vlan_present(vlan_id, vlan_name)` for a supported switch family. Operator provides targets and values through a form, CLI argument or spreadsheet. The template validates VLAN numeric ranges, reserved IDs, existing assignment conflicts, intended service name and platform capability before producing device-specific operations. No unreviewed free-form interpolation or runtime LLM command synthesis.

## Input paths

- **Manual commands:** retain authored command text, selected targets, change intent and explicit verification/recovery evidence; use a restricted/approved operation profile for first deployment.
- **Excel/CSV:** parse typed rows; show per-row errors; map a row to target and template variables; report exact generated commands for approval. A bad row is isolated unless batch continuation risks safety.
- **Compliance:** supply validated findings to a remediation planner, which uses the same template/intent mechanism where appropriate.

## Governance

Preview rendered configuration and intended differences without applying. Approval binds target set, template version, parameter values and produced actions. Keep templates distinct from a future desired-state inventory. Phase 1 should support a small allowlisted set (e.g., VLAN create/allowed-list add), with tests for duplicates, platform variation, unsafe replacements and no-op behavior.

## Agreed engineer-selection model (future)

An engineer first reviews evidence-backed existing interface/VLAN methodology
resolved by the existing read-only audit machinery, then manually selects an
approved template. The selected template may update existing configuration or
create a new interface/service when prerequisite resource checks succeed. Do
not automatically choose a template from the device type or detected method.

- **Standard change:** pre-approved immutable template version, compatible
  device/interface profile, bounded parameters, per-row validation and rollout
  constraints; no additional per-change reviewer only while policy conditions
  remain satisfied. Operator intent, audit and future live checks remain.
- **Advanced change:** engineer-authored CLI, including exact ordered commands
  imported from Excel; separately authorised review and stricter checks.
- **Bulk:** Excel identifies targets, receives resolved configuration/evidence,
  records human validation and selected templates; export separate per-device
  plans with a parent batch manifest, row outcomes and explicit exclusions.
- Both paths use the same versioned Change Plan contract and are **offline
  proposals** until separately implemented. See
  [interface methodology review](interface-methodology-review.md).

## Proposed lifecycle-aware template catalogue

Support explicit, non-interchangeable actions: `create`, `update`, `detach`, `remove`, `retire`. Create and update templates should compute a minimal patch from reviewed existing state. **Removal is separately governed** by [configuration removal](configuration-removal.md): per-interface membership withdrawal must not imply removal of VLAN database, bridge-domain or VSI objects; service-instance deletion must not implicitly remove shared forwarding domains. Template identifiers/versions must distinguish operation and scope. The uploaded workbook's RM01+ snippets are candidate rules only, not executable templates or claims of supported vendor syntax. Standard-change pre-approval for a creation template never automatically authorises a destructive removal.
