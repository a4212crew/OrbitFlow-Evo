# Configuration Management Architecture (Proposed)

Status: approved design direction; **not implemented**. This directory describes planned capabilities, not runnable device-change procedures.

OrbitFlow will accept operator-authored CLI, tabular bulk input, reusable templates and validated compliance findings into one deterministic Change Plan. The shared configuration execution boundary controls validation, approval, prechecks, backups, device application, verification, persistence, recovery and audit.

## Documents

- [Configuration management](configuration-management.md): responsibilities, boundaries and lifecycle.
- [Change Plan specification](change-plan-specification.md): canonical intent and provenance model.
- [Execution workflow](execution-workflow.md): gates, failure handling, audit and rollout controls.
- [Platform adapters](platform-adapters.md): capability-based vendor execution contracts.
- [Configuration templates](configuration-templates.md): deterministic new-configuration generation.
- [Drift detection](drift-detection.md): desired-versus-observed state and reconciliation.

## Architecture boundaries

The shared device-execution layer owns concurrency and device-scoped resources; DeviceContext and DeviceSession/transport are reused. Vendor behaviour stays behind adapters; observation/audit interpretation stays in its owning capability. Reuse existing backup, reporting and structured logging where available; do not assume an unimplemented capability exists. See [root architecture](../../../ARCHITECTURE.md) and [roadmap](../../../ROADMAP.md).

No device apply, approval service, rollback automation, or desired-state datastore is implied by this documentation. Implementation requires separately scoped issues, deterministic tests, and operator-controlled live testing.
