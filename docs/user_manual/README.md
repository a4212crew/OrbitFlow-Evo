# OrbitFlow-Evo User Manuals

This directory is the **canonical home for user guides for user-executable scripts and command-line workflows**. Both **Atlas** (documentation-only, reviewable GitHub changes) and **Codex** (during authorized implementation/fixes) can create and maintain these Markdown guides. Atlas owns consistency and PR review.

## Interactive Operations Console

- [Interactive Operations Console — operator guide](interactive-operations-console.md): implemented menus, environment profile, cancellation, recovery and validation commands; direct CLIs remain supported.

## Guide index

- [Confirmed Catalyst/EdgeSwitch execution](configuration-execution.md): apply CLI, Linux/Windows commands, recovery and validation.
- [Execution and standalone capability APIs](../operations/configuration-execution-api.md): prepare/confirm, switchport parsers/collectors, verifier and save.

Executable guides are indexed below. Source/test-linked reference documents remain at their established locations for compatibility.

- [Device inventory refresh](device-inventory-refresh.md) — CLI, options, report output and failures.
- [Interface/VLAN observation report](device-interface-vlan-report.md) — read-only collection and Excel reporting.
- [VLAN compliance](device-vlan-compliance.md) — collection, methodology report, and offline re-export.
- [Configuration backup](device-configuration-backup.md) — sensitive read-only backup collection.
- [Retired v1 operator guide (compatibility link)](configuration-plan.md) — historical offline-plan CLI pointer; do not use as the current bulk workflow.
- [Development orchestration controller](orchestration-controller.md) — dry-run, watch and task lifecycle.
- [Live validation utilities](live-validation.md) — single-device inventory/VLAN and batch inventory validation helpers.
- [Configuration template workbook engineer guide](configuration-template-guide.md) — full operator walkthrough for all 22 worksheets, per-field inputs, proposed CLI/result cases, review and troubleshooting.
- [Bulk configuration planning v2](bulk-configuration-planning.md) — **current** complete operator manual: purpose, all CLI flags, Linux/Windows commands, 22 templates, input schemas and expected results.
- [Configuration template reference](../operations/configuration-template-reference.md) — detailed scenarios and output expectations.

As each executable guide is reviewed and migrated, add a **script-named Markdown guide here** and a link in this index. Preserve existing source/test-dependent documents and their paths until all references are reconciled.

## Required guide content

Each guide must be verified against the actual CLI implementation and include: purpose and safety classification; executable/module path; prerequisites and supported devices; all arguments with types, defaults and validations; usage scenarios; sanitized sample input; copy-ready commands for supported Linux and Windows environments; **expected result per scenario**, including files, reports or responses; warnings, errors, logs and validation status.

Follow [documentation-management/SKILL.md](../../.agents/skills/documentation-management/SKILL.md). Do not invent CLI flags or output formats. Do not store credentials or sensitive device output.

## Safe operator documentation smoke checks

These checks validate that the locally installed revision exposes the documented entry points. They **do not** exercise authentication, device sessions, workbook generation, live read-only collection, or production configuration changes. Run from the checked-out PR branch or, after owner-approved merge, updated `main`; install the project requirements first.

Linux (from the repository root):

```bash
python scripts/device_inventory_refresh.py --help
python scripts/device_interface_vlan_report.py --help
python scripts/device_vlan_compliance.py --help
python scripts/device_configuration_backup.py --help
python scripts/configuration_plan.py --help
python -m orbitflow.configuration.v2.cli --help
python scripts/orchestration_v2/controller.py --help
```

Windows PowerShell (from the repository root):

```powershell
python .\scripts\device_inventory_refresh.py --help
python .\scripts\device_interface_vlan_report.py --help
python .\scripts\device_vlan_compliance.py --help
python .\scripts\device_configuration_backup.py --help
python .\scripts\configuration_plan.py --help
python -m orbitflow.configuration.v2.cli --help
python .\scripts\orchestration_v2\controller.py --help
```

For the configuration-v2 module, ensure the package is installed or `src` is in `PYTHONPATH`, as described in the repository setup. A successful smoke check exits normally and prints argparse/CLI usage. Compare subcommands, required arguments and defaults against the individual manuals. Record any mismatch for a documentation-only correction on this PR; do not put credentials, sensitive configuration output or Teleport key material in review comments. Full operator scenarios on Linux/Windows and controlled read-only device checks require an owner-operated environment and remain **not executed by Atlas**.

- [MAC Address Lookup](mac-address-lookup.md): two console actions, direct CLI, offline recovery and pending owner validation.
