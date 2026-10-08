# Deterministic Configuration Templates — Proposed

Templates support **new service configuration**, not just remediation. A reviewed template has an identifier and immutable version, supported device families/operations, typed input schema, required preconditions, rendering logic and expected postconditions.

Example: `ensure_vlan_present(vlan_id, vlan_name)` for a supported switch family. Operator provides targets and values through a form, CLI argument or spreadsheet. The template validates VLAN numeric ranges, reserved IDs, existing assignment conflicts, intended service name and platform capability before producing device-specific operations. No unreviewed free-form interpolation or runtime LLM command synthesis.

## Input paths

- **Manual commands:** retain authored command text, selected targets, change intent and explicit verification/recovery evidence; use a restricted/approved operation profile for first deployment.
- **Excel/CSV:** parse typed rows; show per-row errors; map a row to target and template variables; report exact generated commands for approval. A bad row is isolated unless batch continuation risks safety.
- **Compliance:** supply validated findings to a remediation planner, which uses the same template/intent mechanism where appropriate.

## Governance

Preview rendered configuration and intended differences without applying. Approval binds target set, template version, parameter values and produced actions. Keep templates distinct from a future desired-state inventory. Phase 1 should support a small allowlisted set (e.g., VLAN create/allowed-list add), with tests for duplicates, platform variation, unsafe replacements and no-op behavior.
