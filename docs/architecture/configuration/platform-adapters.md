# Configuration Platform Adapters — Proposed

## Contract

A single-device adapter declares capabilities and implements operations appropriate to its OS and device family, rather than exposing one universal unsafe `send_config` assumption.

Suggested contract: `capabilities(context)`, `precheck(context,plan)`, `capture_checkpoint(...)`, `render/validate_operations(...)`, `apply(...)`, `verify(...)`, `persist_or_confirm(...)`, and `recover(...)` when explicitly supported. Each returns structured status/evidence. Shared transport owns sessions, and shared execution owns per-device resource lifecycle.

| Family | Execution model | Safety requirements |
| --- | --- | --- |
| Cisco IOS / IOS-XE | Imperative running-config changes; separate startup save | Pre/post fact checks; do not persist until verified; no promise of atomic rollback; confirm hardware/OS support for any timed rollback mechanism |
| Cisco IOS-XR | Candidate/commit-oriented configuration | Use supported commit check/confirmed and rollback features only after validating exact release/command semantics; manage confirmation deadlines and unknown state |
| Ubiquiti EdgeSwitch | Vendor CLI and persistence commands vary by model/firmware | Verify privilege, config/saving model and supported recovery on tested families; never assume Cisco equivalence |
| Huawei VRP | Vendor-specific CLI, commit/save behavior may differ by release | Explicit capability profiling and lab verification before enabling apply |
| OLT/ONU platforms | Diverse vendor APIs/CLIs and service impact | Out of initial implementation scope until separately approved and validated |

Unsupported operations block before any changes. Provide per-operation idempotence classification, persistence strategy, recovery availability, verification hooks, and secret-redaction behavior. Platform identifiers and model capability profiles remain separate. Avoid hardcoding device commands in workflow/plan orchestration.

## Delivery order

Initial proposal: IOS/IOS-XE limited, reviewed operations; then IOS-XR transactions; EdgeSwitch; Huawei and OLTs by separately approved capability milestones. Each family requires offline tests and controlled live validation.
