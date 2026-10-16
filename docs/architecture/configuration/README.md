# Configuration Management Architecture (Proposed)

Status: **offline Change Plans v1 and the separate configuration planning v2 workflow are implemented**. See [Offline Change Plans v1](offline-plans.md), [bulk planning v2 operator guide](../../operations/bulk-configuration-planning.md), and [template reference](../../operations/configuration-template-reference.md). Live configuration apply and subsequent execution phases remain proposed.

OrbitFlow will accept operator-authored CLI, tabular bulk input, reusable templates and validated compliance findings into one deterministic Change Plan. The shared configuration execution boundary controls validation, approval, prechecks, backups, device application, verification, persistence, recovery and audit.

## Documents

- [Approved template-based configuration planning (Gap C target)](guided-bulk-planning.md): 22 function-specific worksheets, live read-only validation for predefined templates, offline Manual CLI, evidence-rich per-row review and future apply boundary. **Planning implemented; live apply not implemented.**

- [Configuration management](configuration-management.md): responsibilities, boundaries and lifecycle.
- [Change Plan specification](change-plan-specification.md): canonical intent and provenance model.
- [Execution workflow](execution-workflow.md): gates, failure handling, audit and rollout controls.
- [Platform adapters](platform-adapters.md): capability-based vendor execution contracts.
- [Configuration templates](configuration-templates.md): deterministic new-configuration generation.
- [Drift detection](drift-detection.md): desired-versus-observed state and reconciliation.

## Architecture boundaries

The shared device-execution layer owns concurrency and device-scoped resources; DeviceContext and DeviceSession/transport are reused. Vendor behaviour stays behind adapters; observation/audit interpretation stays in its owning capability. Reuse existing backup, reporting and structured logging where available; do not assume an unimplemented capability exists. See [root architecture](../../../ARCHITECTURE.md) and [roadmap](../../ROADMAP.md).

No device apply, remote approval service, rollback automation, or desired-state
datastore is implemented. Later phases require separately scoped issues,
deterministic tests, and operator-controlled live testing.

## Methodology resolution and deferred engineering review

[Interface methodology resolution and template review](interface-methodology-review.md)
records the agreed bulk workflow and a gap assessment against the existing
`AuditResolver`. M01–M08 read-only methodology resolution is implemented separately from the offline Change Plan v1. Gap B engineer review import is deferred; the approved replacement Gap C design is documented above (Issue #88 / PR #89 superseded). The separate configuration v2 template catalogue and bulk planning workflow are implemented; consult the current operator guide and source for supported template details. Engineer review import and live configuration apply remain separately gated and are not implied by planning support.

- [Configuration removal and service retirement](configuration-removal.md): proposed removal scopes, dependency checks, platform risk gates and test obligations. No destructive executor is implemented.
