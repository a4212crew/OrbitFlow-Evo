# EdgeSwitch interface-status collection: observed output variants (2026-10-08)

## Status and scope

**Confirmed parser defect; not yet fixed.** The reusable `InterfaceService` raises `InterfaceCapabilityError` on six Ubiquiti EdgeSwitch devices during VLAN-compliance collection. The nested exception is `ValueError` in `src/orbitflow/vendors/ubiquiti/interfaces.py:parse_interfaces_status`. This does **not** establish a faulty physical interface. The VLAN compliance workflow can proceed with its separate VLAN collection even where interface observation fails.

This note captures supplied operator CLI observations and sanitised run diagnostics. Do not treat it as implemented parser behaviour or completed live remediation.

## Affected live devices

| Management IP | Device | Failure in parser | Root-cause evidence |
| --- | --- | --- | --- |
| `10.125.3.135` | `C-CAUL-189HAWTH-BAS1` | line 40 | Captured output includes the additional `Media Type` header/column |
| `10.125.3.142` | `R-MALV-54GLEN-BAS1` | line 40 | Captured output includes the additional `Media Type` header/column |
| `10.125.3.175` | `R-CAUL-AUBIN-BAS1` | line 40 | Captured output includes the additional `Media Type` header/column |
| `10.125.3.141` | `R-MALV-1GLEN-BAS1` | line 40 | Captured output includes the additional `Media Type` header/column |
| `10.121.9.3` | `NSW-PEAK-26GOVER-BAS1` | line 40 | Same logged exception location; **CLI output not supplied**, so variant is unconfirmed |
| `10.125.11.132` | `R-PRAH-WILLI-BAS3` | line 70 | Standard header; line for port `0/4` contains a non-breaking space (`U+00A0`) in the description |

The log excerpts contain two runs on 2026-10-08 and show the same failure paths; the 19-device validation evaluated all targets but included six interface-collection errors. The latest log entries for the six are around 04:52 UTC. Avoid assuming the exact rejected row text from the exception log: sanitised diagnostics intentionally omit exception messages and raw device output.

## Supported source formats observed on real devices

The command is `show interfaces status all`, normally after `terminal length 0`.

**Six-column standard header** (confirmed at `10.125.11.132`):

```text
                                         Link    Physical    Physical    Flow Control
Port       Name                          State   Mode        Status      Status
---------  ----------------------------  ------  ----------  ----------  ------------
```

**Seven-column Media Type header** (confirmed at four devices listed above):

```text
                                         Link    Physical    Physical    Media               Flow Control
Port       Name                          State   Mode        Status      Type                Status
---------  ----------------------------  ------  ----------  ----------  ------------------  ------------
```

Both formats contain physical ports such as `0/1`, `0/10`, `0/26` and short `3/1`–`3/6` rows with only the link state. Media Type examples carry `Unknown`. The footer observed is `Flow Control:Disabled`. There are no grounds to classify the short `3/x` rows as erroneous solely because trailing fields are blank.

In the standard-header sample, port `0/4` has description `LW0024035 -\u00a0168 Williams Ro`. The `U+00A0` between the hyphen and number is meaningful evidence for the line-70 failure: the parser slices using fixed character offsets and requires ASCII spaces between columns. The port itself reports `Up`. Do not normalise Unicode in a way that shifts fixed-width boundaries; preserve the field value correctly.

## Current implementation and diagnosis

- `src/orbitflow/vendors/ubiquiti/interfaces.py`: `_HEADER` is a single exact three-line constant; `_COLUMN_SPANS` is derived from that separator line. `parse_interfaces_status()` raises at line 40 when a header differs from the one accepted exact layout.
- The same parser uses fixed-column slicing and structural checks for row validity. The standard-header device with `U+00A0` fails at the row-validation path (line 70 in the observed revision).
- `src/orbitflow/capabilities/interfaces.py:InterfaceService.collect()` wraps these `ValueError` failures as `InterfaceCapabilityError`. `src/orbitflow/vlan_compliance.py` logs the per-stage failure but continues evaluating other stages/targets.
- The new shared run-level diagnostics from Issue #67/PR #68 are **merged**. They help identify exception category and safe file/function/line metadata; they do not intentionally log raw command output.

## Proposed parser-fix acceptance criteria (future separate Issue)

1. Recognise **both verified header variants** and select column boundaries from the matched variant rather than guessing from arbitrary headers.
2. Parse legitimate Unicode whitespace in descriptions (including `U+00A0`) without corrupting fixed-width column alignment.
3. Preserve port names, descriptions, and correct `Up`/`Down` operational state, including blank descriptions, `Auto D`, and short `3/x` rows.
4. Continue to reject unknown, malformed, incomplete or truncated non-empty output and rejected commands; do not silently downgrade to empty-success collections.
5. Add deterministic sanitized fixtures/tests representing both captured variants and problematic description characters; avoid persisting credentials, banner text or raw device dumps in test fixtures.
6. Run targeted EdgeSwitch parser and shared-capability regression tests, then operator-led live collection for all six listed devices; separately verify `10.121.9.3`'s actual output format.
7. Keep changes vendor-local and reusable across workflows. Do not change transport, result-spool implementation, VLAN compliance policy evaluation or other vendor parsers.

## Related but separate backlog

The planned VLAN compliance resolver/status work ("Issue B") remains separate: Catalyst/ME3600X explicit-mode versus wrong-configuration classification, Huawei NE05E VSI-bound child consolidation without Catalyst-like parent trunk requirement, and an unresolved Catalyst mode remaining a wrong-configuration finding per owner direction. This is **not implemented** by the EdgeSwitch parser-fix documentation and should not be conflated with the issue above.

Governance: create work via a GitHub Issue and Codex branch/PR; require tests, Atlas review, operator validation and **explicit user merge approval**.
