# Retired guide — legacy offline configuration plans v1

> **Retired as an active operator guide (2026-10-16).** This path is retained as a compatibility pointer for existing links, not as the current bulk planning instructions. The legacy `scripts/configuration_plan.py` / `orbitflow.configuration` v1 offline plan CLI still exists; retiring this page does **not** remove the script or claim v1 is unsupported. Historical v1 design: [Offline Change Plans v1](../architecture/configuration/offline-plans.md).

**Current user workflow:** [Bulk configuration planning v2](bulk-configuration-planning.md) includes purpose, available commands, all 22 templates, inputs, expected outputs, safe Linux/Windows examples and review limitations. Detailed template-by-template CLI outcomes are in the [configuration template reference](../operations/configuration-template-reference.md).

If you still intentionally use the v1 CLI, verify its available arguments with `python scripts/configuration_plan.py --help` and consult the v1 architecture contract; **do not treat the v2 commands or workbook as v1-compatible**. Neither workflow provides live configuration apply.

## Shared progress presentation (Issue #144)

See [CLI progress and durable results](cli-progress.md) for interactive and redirected
output, phase-specific counters, saved paths, partial/interrupted/export-failure
semantics and the coverage table (including specialist/lifecycle exemptions).
Device/workflow semantics and existing arguments are unchanged. Deterministic
terminal fixtures are separate from pending owner-operated Linux/Windows validation.
