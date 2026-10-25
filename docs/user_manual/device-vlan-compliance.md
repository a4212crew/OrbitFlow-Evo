# VLAN compliance — operator manual

**Script:** `scripts/device_vlan_compliance.py`. **Purpose:** collect and evaluate read-only VLAN/interface compliance; optionally regenerate reports from an existing spool without new connections.

## Prerequisites and safety
Run from the repository root with Python 3.11+, installed `requirements.txt`, `PYTHONPATH=src` if required, and an authenticated `tsh` profile. The input workbook contains approved device targets; credential material must not be committed. Provide all four required Teleport routing options: `--proxy`, `--cluster`, `--bastion-host`, `--bastion-user` (strings). Linux Teleport key/certificate file paths may be required; supply `--teleport-key-path` and `--teleport-cert-path` (optional paths, default unset). No script here performs configuration apply.

## Commands and inputs
**`run`:** positional `excel_path` (path), four required Teleport routing strings, optional key/cert paths (unset). Optional paths `--policy` (the application's `DEFAULT_POLICY`), `--config` (`orbitflow.toml`), `--inventory-path` (`data/inventory/inventory.json`), `--reports-dir` (`outputs/reports/vlan_compliance`), `--spool-root` (`outputs/runs/vlan_compliance`), `--log-root` (`outputs/logs`). Boolean flags `--keep-spool` (default false) and `--methodology-report` (default false).

**`export`:** required positional `spool_path` and `output_path` (paths). Optional `--log-root` (`outputs/logs`), `--keep-spool` (false), `--allow-partial` (false), `--methodology-report` (false). `export` does not require Teleport access.

## Examples and expected results
Linux collection:
```bash
python scripts/device_vlan_compliance.py run outputs/devices.xlsx --proxy teleport.example.net:443 --cluster example-cluster --bastion-host example-bastion --bastion-user example-user --teleport-key-path "$TELEPORT_KEY_PATH" --teleport-cert-path "$TELEPORT_CERT_PATH" --keep-spool
```
Produces a compliance workbook under the reports directory; terminal prints `Compliance workbook saved. Review Findings and Run_Errors.`

Windows PowerShell offline re-export:
```powershell
python scripts/device_vlan_compliance.py export .\outputs\runs\vlan_compliance\<retained-spool> .\outputs\reports\vlan_compliance\review.xlsx --allow-partial --keep-spool
```
Produces an Excel workbook from retained data, without connecting to network devices. For a separate methodology workbook, add `--methodology-report`; terminal prints `Workbook saved. Review methodology results and Run Errors.` Partial export requires explicit `--allow-partial`. An invalid spool/policy/input reports sanitized `VLAN compliance failed`; inspect logs and retained run spool. **No configuration apply.**

## Interactive console adapter (Issue #123)

This workflow is also available through `python -m orbitflow.menu`; see the [console manual](interactive-operations-console.md) for environment profile, target workbook selection, per-run concurrency, confirmation and output/recovery behavior. Direct CLI flags and service contracts remain supported. Default `orbitflow.toml` execution loading now prefers validated shared profile pacing when present; explicit alternate config files retain their semantics.

Console target selection (Issue #123 revision): after choosing a device workbook, choose all (blank) or unique comma-separated nonempty device row numbers, counted from 1 after the header. Only selected rows are dispatched; concurrency is still prompted every run. See the [console guide](interactive-operations-console.md) for cancellation and fixed actionable failure diagnostics. Direct CLI input selection is unchanged.

## Shared progress presentation (Issue #144)

See [CLI progress and durable results](cli-progress.md) for interactive and redirected
output, phase-specific counters, saved paths, partial/interrupted/export-failure
semantics and the coverage table (including specialist/lifecycle exemptions).
Device/workflow semantics and existing arguments are unchanged. Deterministic
terminal fixtures are separate from pending owner-operated Linux/Windows validation.

## Shared aggregation ownership (Issue #149)

See [shared ownership and validation](aggregation-validation.md) for child compliance
skipping, original parent headings, unchanged family forwarding checks, public
model compatibility, exact Bash/PowerShell collection and offline export commands,
and the pending owner family/workflow acceptance matrix.

EdgeSwitch logical parents show the verified saved `lag N` heading in Interface,
Config Interface and Configuration Owner, even when observed as `3/N`; observed
admin/oper state is preserved. Exactly one parent row is emitted. Missing headings
are not invented. Physical child skips, independent configuration findings and
evidence remain visible. The separate interface/VLAN report retains `3/N`.
Offline export preserves recorded names, including those in older spools.

## Concise summaries and lossless Details (Issue #149 review revision)

Confirmed physical children name the configuration owner and required-VLAN skip
once. Independent issues retain their finding codes and member/parent comparison;
VLAN lists use counts and at most eight ranges. These summaries are presentation
only: exact lists/comparisons remain in the persisted `observed.configuration_findings`
and the Details `observed` JSON; original sanitized source excerpts remain in
`evidence` JSON and Configuration Evidence / Evidence Source / Evidence Lines.
Recommendations address explicit source conflicts or request missing evidence;
the relationship alone does not authorize a device change. Inactive EdgeSwitch
tagging remains informational, independent of genuine mismatches and health.

The four sheets and all columns are unchanged. Complete sanitized cell values
of at most 30,000 characters stay inline. Every larger value is replaced by
`See Details: input N, finding M, Original Column Name`. Filter Details by Input
Position = N, Finding = M, Field = the exact original column name; sort Part
numerically and concatenate JSON Fragment **without separators**. This recovers
the complete sanitized column value. Do not combine devices, finding indices or
fields. Run Errors use `error M` as the Finding key to avoid collision with findings.
Lowercase `observed` and `evidence` fields are structured JSON, separately keyed
from display column fragments. Sanitation occurs before splitting; fragments and
references fit Excel limits. No silent truncation or new worksheets are used.
A bounded summary is recovered through its structured facts, not by expanding
the summary text. Retained historical spools use the same offline exporter and
retain their recorded finding text; policy is not re-evaluated during export.

See [validation checks](aggregation-validation.md#summary-and-overflow-review-checks)
for automated commands and owner read-only/offline review steps on both shells.
