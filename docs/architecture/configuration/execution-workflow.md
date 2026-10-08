# Configuration Execution Workflow — Proposed

## Gates

1. **Create:** build a Change Plan from a supported source; no device write.
2. **Offline validate:** schema, targets, allowed values, platform capability, deterministic rendered commands, conflicts, planned evidence and recovery availability.
3. **Review and approve:** human explicitly authorizes the exact plan digest and target set; dry-run by default; no inferred approval from collecting or generating compliance reports.
4. **Live preflight:** validate identity, session/privilege, existing service/interface state, management reachability assumptions and maintenance requirements. Re-read relevant state; stale plan blocks.
5. **Backup:** capture the required safe checkpoint/config backup, record success and location, and block if mandatory backup fails.
6. **Apply:** per-device controlled actions via adapter; record sanitized command/result metadata; do not echo secrets. Distinguish command accepted from service working.
7. **Verify:** assert declared post-change facts and critical connectivity/service checks appropriate to the change. A verification timeout is **unknown outcome**, not proof the change failed or was reverted.
8. **Persist:** save running-to-startup (where applicable) only after verification; for transactional systems confirm/commit according to adapter's semantics. Saving/confirming itself must be checked.
9. **Finalize:** durable per-target status, audit evidence, failure report and operator disposition.

## Recovery

Rollback is conditional on tested platform and change-specific capability. Prefer safe native transactional checkpoints where supported. For imperative CLI, an offline backup is **not** automatically a safe rollback method: removing commands can disrupt unrelated changes. If connectivity is lost or state cannot be established, stop, mark outcome unknown, and escalate to an operator with an out-of-band recovery path. Never retry destructive changes blindly.

## Rollout and scale

Reuse the shared device-execution layer for device-scoped isolation and outcomes. Use an independently approved configuration concurrency cap, small canary batches, pacing, max targets per run, bounded retries and a circuit breaker on failure count/rate. Freeze remaining targets when circuit breaker activates; do not automatically roll back already successful devices. Include explicit cancellation semantics and resume only after reconciling current device state.

## Audit and filesystem

Use the established filesystem convention: `outputs/runs/<task>/<run-id>/` for change manifest/status and sanitized results, `outputs/backups/configuration/` for protected backups, and `outputs/logs/<module>/YYYY-MM-DD/` for sanitized diagnostics. Retain provenance, approval, target identity, timestamps, plan digest, pre/post-check results, save/commit result, recovery actions, and final disposition. Apply permissions/retention to potentially sensitive backups; never commit device configuration or credentials to Git.

## Tests and rollout

First test plan validation and adapters with fixtures/fakes, then controlled single-device lab tests, then canary production changes only with explicit operator consent. Do not mark an adapter safe without verification of its specific platform and device family.
