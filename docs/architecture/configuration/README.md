# Configuration Management Architecture (Proposed)

Status: approved design direction. Offline Phases 1–2 are implemented; see
[Offline Change Plans v1](offline-plans.md) for the executable contract and CLI.
Device execution and later phases remain proposed.

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

No device apply, remote approval service, rollback automation, or desired-state
datastore is implemented. Later phases require separately scoped issues,
deterministic tests, and operator-controlled live testing.

## Next proposed increment: engineer-reviewed interface methodology

[Interface methodology resolution and template review](interface-methodology-review.md)
records the agreed bulk workflow and a gap assessment against the existing
`AuditResolver`. It is a proposed extension only: no M01–M07 method IDs,
engineer review import, template registry or bulk Change Plan workflow is
implemented by offline Phases 1–2.

- [Configuration removal and service retirement](configuration-removal.md): proposed removal scopes, dependency checks, platform risk gates and test obligations. No destructive executor is implemented.
