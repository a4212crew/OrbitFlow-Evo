# Change Plan Contract — Proposed

The format below is **illustrative**, not an implemented or finalized serialization schema.

```yaml
schema_version: 1
change_id: CHG-EXAMPLE-001
source:
  kind: manual                 # manual | spreadsheet | template | compliance
  reference: operator-request # sanitized source reference / finding / version
intent:
  summary: Add VLAN 3500 to approved switches
  operation: ensure_vlan_present
  parameters:
    vlan_id: 3500
    vlan_name: CUSTOMER-SERVICE
targets:
  - inventory_id: SW-EXAMPLE-01
    expected_platform: cisco_iosxe
    expected_state_fingerprint: <sanitized-observation-token>
verification:
  desired_facts:
    - vlan_id: 3500
      present: true
execution_policy:
  dry_run: true
  require_approval: true
  backup_required: true
  save_after_verify: true
  max_concurrent_devices: 1
  max_devices_per_run: 5
  stop_after_failures: 1
  recovery_strategy: manual_or_supported_checkpoint
approval:
  status: pending
  approver: null
  approved_plan_digest: null
```

## Invariants

- Targets resolve through canonical inventory/DeviceContext; refuse hostname/platform mismatch or ambiguous resolution.
- A target can have its own rendered operations, expected facts, execution constraints and outcome.
- Record source provenance and template/policy versions; approve the immutable digest of fully resolved targets, operations and preconditions.
- Separate *intent* from rendered commands. Commands must be deterministic, platform-reviewed and visible before approval.
- Secrets and raw secret-bearing configuration are excluded from plans, logs, diffs and approval artifacts.
- Preconditions compare **relevant** live fields against plan assumptions immediately before apply. If changed, block or regenerate; avoid comparing irrelevant entire configurations.
- Idempotent operations should detect already-correct state and skip safely; conflicting existing state blocks and requires review.
- Explicitly represent verification capability, rollback availability and unknown outcome. Never infer rollback commands by blindly reversing arbitrary CLI.
- Plan schema evolution requires versioning and validation tests. Approval expires or is revoked when target, commands, risk, or state-dependent assumptions materially change.
