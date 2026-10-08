# Universal Configuration Management — Proposed Architecture

## Goal

Support **new configuration** and **compliance remediation** through one controlled change pipeline, avoiding a compliance-specific device pusher.

## Sources and ownership

1. Manual CLI: explicitly provided operator commands, with device/platform targeting and declared verification/recovery.
2. Spreadsheet/CSV: validated rows mapped into a deterministic plan; no direct execution from raw cells.
3. Templates: reviewed, versioned templates plus typed values generate vendor-specific intended changes.
4. Compliance: remediation proposals derived from validated audit findings, not from ad-hoc re-parsing of raw CLI.

All sources produce a **Change Plan**, not device commands executed immediately. Planning is side-effect-free. The shared configuration orchestrator handles approval, change-specific preflight, execution policy, recording and verification. Platform adapters implement platform-dependent apply/commit/recovery. Shared DeviceContext, session, device-execution and logging layers remain authoritative for target identity, transport, device-scoped concurrency, and diagnostics.

## Lifecycle

```text
Source -> normalize -> Change Plan -> offline validation -> explicit approval
       -> refresh live state/prechecks -> backup -> controlled apply
       -> post-change verification -> persist/save where supported
       -> record outcome or controlled recovery / escalation
```

A plan is immutable after approval; edits or material target-state drift require regeneration/reapproval. A plan may contain multiple targets but execution status is per target; do not represent partial success as global success. Keep observation, desired state, planned action, actual device response and verified outcome distinct.

## Boundaries and non-goals

- Runtime config generation and decision-making must be deterministic; no LLM-invented device commands.
- No implied automatic self-remediation, blanket rollback, or unapproved deployment.
- Platform/device-family capability profile—not the OS label alone—determines whether a command type, commit mode and recovery method are supported.
- Do not duplicate SSH, Teleport, worker pools, vendor parsers, result-spooling or reporting in the configuration feature.
- Future UI, scheduling and drift reconciliation are separate capabilities over the same Change Plan contract.
