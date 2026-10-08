# ROADMAP.md — OrbitFlow Future Work

This file contains future ideas and is not a permanent instruction set.

Items here are not automatically approved implementation tasks. Move an item into an explicit task before Codex implements it.

## Potential Enhancements

- Store daily snapshots in MySQL or PostgreSQL.
- Build a web dashboard for interface changes.
- Add device grouping by region/site.
- Add email reporting for daily changes.
- Add Git-based snapshots of collected raw outputs.
- Add NMS inventory integration.
- Add topology mapping based on LLDP/CDP.
- Add controlled rollback execution only after provisioning has sufficient field testing.
- Add optional RAG/LLM summaries only after deterministic structured parsing is complete.
- Add database-backed history while preserving Excel workflows where still required.
- Add additional inventory sources only through an explicit approved architecture change.
- Expand transport/session abstraction so collectors and provisioners share one stable device-session API.
- Add credential-provider abstraction suitable for both Windows and Linux.
- Add additional vendor/platform skills as OrbitFlow scope grows.

## Universal Configuration Management (Proposed)

Architecture: [docs/architecture/configuration/](docs/architecture/configuration/README.md). These are prospective phases, not approved implementation issues or completed features.

1. Define and validate a versioned shared Change Plan contract for manual CLI, Excel/CSV, templates and compliance-derived proposals.
2. Build a non-destructive validation and approval boundary, reusing shared device execution, transport, backups and logging.
3. Introduce controlled IOS/IOS-XE execution with mandatory preflight, verified state, explicit save and safe failure/unknown-state reporting; validate in a lab first.
4. Add tested, capability-gated transactional IOS-XR support, then EdgeSwitch and other families as separately scoped work.
5. Add reviewed configuration templates, bulk input and audit-ready UI/scheduling integrations.
6. Add desired-state storage, drift detection and approval-gated reconciliation after implementation maturity.

Automated rollback must remain conditional on vendor capability and field-tested recovery. Configuration concurrency requires its own conservative, explicitly approved policy.
