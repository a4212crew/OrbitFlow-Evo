# OrbitFlow-Evo User Manuals

This directory is the **canonical home for user guides for user-executable scripts and command-line workflows**. Both **Atlas** (documentation-only, reviewable GitHub changes) and **Codex** (during authorized implementation/fixes) can create and maintain these Markdown guides. Atlas owns consistency and PR review.

## Guide index

Some existing executable documentation remains at legacy locations; migration is in progress. Until the separately reviewed migration is complete, consult:

- [Inventory, interface/VLAN reporting and backups](../../README.md) — existing executable examples.
- [Bulk configuration planning v2](bulk-configuration-planning.md) — executable operator workflow and commands (migrated manual; original operations path retained as a compatibility reference).
- [Configuration template reference](../operations/configuration-template-reference.md) — detailed scenarios and output expectations.

As each executable guide is reviewed and migrated, add a **script-named Markdown guide here** and a link in this index. Preserve existing source/test-dependent documents and their paths until all references are reconciled.

## Required guide content

Each guide must be verified against the actual CLI implementation and include: purpose and safety classification; executable/module path; prerequisites and supported devices; all arguments with types, defaults and validations; usage scenarios; sanitized sample input; copy-ready commands for supported Linux and Windows environments; **expected result per scenario**, including files, reports or responses; warnings, errors, logs and validation status.

Follow [documentation-management/SKILL.md](../../.agents/skills/documentation-management/SKILL.md). Do not invent CLI flags or output formats. Do not store credentials or sensitive device output.
