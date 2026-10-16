# OrbitFlow-Evo User Manuals

This directory is the **canonical home for user guides for user-executable scripts and command-line workflows**. Both **Atlas** (documentation-only, reviewable GitHub changes) and **Codex** (during authorized implementation/fixes) can create and maintain these Markdown guides. Atlas owns consistency and PR review.

## Guide index

Executable guides are indexed below. Source/test-linked reference documents remain at their established locations for compatibility.

- [Device inventory refresh](device-inventory-refresh.md) — CLI, options, report output and failures.
- [Interface/VLAN observation report](device-interface-vlan-report.md) — read-only collection and Excel reporting.
- [VLAN compliance](device-vlan-compliance.md) — collection, methodology report, and offline re-export.
- [Configuration backup](device-configuration-backup.md) — sensitive read-only backup collection.
- [Offline configuration plans v1](configuration-plan.md) — create, validate, preview and locally approve plans.
- [Development orchestration controller](orchestration-controller.md) — dry-run, watch and task lifecycle.
- [Live validation utilities](live-validation.md) — single-device inventory/VLAN and batch inventory validation helpers.
- [Bulk configuration planning v2](bulk-configuration-planning.md) — executable operator workflow and commands (migrated manual; original operations path retained as a compatibility reference).
- [Configuration template reference](../operations/configuration-template-reference.md) — detailed scenarios and output expectations.

As each executable guide is reviewed and migrated, add a **script-named Markdown guide here** and a link in this index. Preserve existing source/test-dependent documents and their paths until all references are reconciled.

## Required guide content

Each guide must be verified against the actual CLI implementation and include: purpose and safety classification; executable/module path; prerequisites and supported devices; all arguments with types, defaults and validations; usage scenarios; sanitized sample input; copy-ready commands for supported Linux and Windows environments; **expected result per scenario**, including files, reports or responses; warnings, errors, logs and validation status.

Follow [documentation-management/SKILL.md](../../.agents/skills/documentation-management/SKILL.md). Do not invent CLI flags or output formats. Do not store credentials or sensitive device output.
