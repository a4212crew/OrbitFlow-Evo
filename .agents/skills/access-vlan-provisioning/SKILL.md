---
name: access-vlan-provisioning
description: Use for OrbitFlow access VLAN provisioning, provisioning Excel input, dry-run/precheck/apply/verify modes, validation, deterministic candidate configuration, pre/post checks, audit output, rollback evidence, or provisioning tests.
---

# Access VLAN Provisioning

## Use This Skill When

Use for access VLAN provisioning, provisioning workbook schema, dry-run/apply/verify behaviour, pre/post checks, VLAN validation, deterministic candidate orchestration, audit/rollback evidence, and provisioning tests.

Vendor command changes cross into the relevant vendor CLI capability; load that vendor skill only when commands/parsers/verification behaviour are being changed.

## Adjacent Capability Boundaries — Do Not Load by Default

References below describe ownership boundaries, not automatic context dependencies.

- `../jumphost-connectivity/SKILL.md` — load only for transport/session changes or transport defects.
- `../excel-inventory/SKILL.md`
- `../device-execution/SKILL.md` — load when changing multi-device execution/concurrency behaviour — load only when target/input schema or credential precedence changes.
- vendor CLI skills — load only for vendor command, parser, or verification changes.

## Safety Model

Provisioning is non-destructive by default.

Conceptual modes:
- `dry-run` — validate, pre-check as appropriate, generate candidate, do not apply;
- `precheck-only` — capture current state only;
- `apply` — explicit configuration change;
- `verify-only` — validate requested state without changing configuration.

If no explicit change mode is selected, default to non-destructive behaviour.

## Required Workflow

```text
Read row
-> validate
-> acquire device session through OrbitFlow transport
-> pre-check current state
-> validate interface/service assumptions
-> generate deterministic candidate
-> if dry-run: record and stop
-> if apply: capture rollback evidence
-> apply configuration
-> post-check verification
-> record result/audit/error/rollback evidence
```

Do not implement independent SSH in provisioning code.

Provisioning may reuse the shared device-execution layer, but configuration-changing workflows must not automatically inherit the read-only concurrency setting. The approved concurrency limit for change workflows must be explicit and preserve all pre-check/apply/verify/audit safeguards.

## Provisioning Input

Expected concepts:
- Device Name
- Device IP
- Platform
- Port Name
- Location ID
- RSP
- Service ID
- VLAN
- Action
- optional explicit Description
- optional credential/port fields where legacy compatibility requires them

Generated description baseline:

```text
<Location ID> | <RSP> | <Service ID> | VLAN-<VLAN>
```

An allowed explicit description override takes precedence.

## VLAN Validation

- VLAN must be an integer.
- Normal valid range is `1..4094`.
- Reject empty, non-numeric, negative, or out-of-range values.
- Invalid rows must not be configured.
- Record validation failure.

## Vendor Configuration

Do not keep vendor command syntax here. Load the relevant vendor skill.

Do not guess alternate service models when a platform rejects a command. Stop that row and record failure unless the requested workflow explicitly defines an alternative.

## Pre-check and Verification

Pre-check must confirm enough current state to safely generate/apply the requested change.

Post-check must verify the requested outcome deterministically. Command transmission alone is not success.

## Rollback Evidence

Before applying configuration:
- capture relevant pre-change configuration;
- store it in audit/rollback output;
- generate a rollback candidate only where deterministic and safe.

Do not automatically execute rollback unless a separately approved rollback mode exists. Never guess unknown prior configuration.

## Provisioning Workbook

Expected logical worksheets:
- `Provisioning_Result`
- `Provisioning_Errors`
- `Provisioning_Audit_Log`
- `Rollback_Config`

Record request identity, mode, precheck status, whether config was applied, verification, final result/error, relevant command/audit evidence, and captured rollback state without exposing credentials.

## Error Handling

Handle per-row validation errors, missing fields, unsupported platform, interface not found, transport timeout, authentication failure, command rejection, commit/save failure, verification failure, and workbook failures.

Where safe, continue processing remaining rows.

## Tests

Tests must not require live devices for deterministic logic.

Cover VLAN validation, description generation/override, unsupported platform handling, vendor configuration generation, pre-check decision logic, verification logic, and output writers.
