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

## V1 input resource bound (Issue #162)

The retained v1 CLI/API reads request and plan files with a **16 MiB byte bound
before UTF-8/JSON decoding**. This exceeds the closed schema's maximum canonical
content (100 targets, 100 small VLAN operations each) and prevents an oversized
unvalidated file from exhausting memory. Oversize/encoding errors raise fixed
`PlanError` diagnostics; the CLI returns status 2. Existing schemas, canonical
digests, signed approvals and arguments are unchanged. This bound also applies
to unusually padded/reformatted input files; keep canonical artifacts intact.

Offline regression on Linux:

```bash
PYTHONPATH=src python -m pytest tests/test_configuration_plans.py -q
```

Windows PowerShell:

```powershell
$env:PYTHONPATH = (Join-Path (Get-Location) 'src')
python -m pytest tests/test_configuration_plans.py -q
```

Synthetic tests cover pre-decode oversize rejection, v1 CLI errors, historical
plans, digests, mutation and signed approval safety. Native Windows validation
remains owner-controlled and pending.
