---
name: ubiquiti-network-cli
description: Use for Ubiquiti EdgeSwitch CLI behaviour in OrbitFlow, including interface collection, access VLAN/PVID configuration, verification, firmware caveats, and EdgeSwitch-specific parsing.
---

# Ubiquiti EdgeSwitch CLI

## Use This Skill When

Use for EdgeSwitch-specific commands, parsing, configuration generation, or verification.

Also use:
- `../interface-collector/SKILL.md`
- `../vlan-observation/SKILL.md`
- `../access-vlan-provisioning/SKILL.md`

Do not add UISP API behaviour to this skill unless a future explicit task expands scope.

## Interface Collection

Primary baseline:

```text
terminal length 0
show interfaces status all
```

Do not use `show interfaces description` or guess a fallback command.

Mapping guidance:
- interface `Name`, if present -> Port Description;
- link state/status -> Oper Status;
- if admin status is not clearly available, use empty/`unknown`; do not guess.

### Confirmed interface-status parser limitations (2026-10-08; fix pending)

**This section documents observed devices and a required fix, not implemented support.** The current parser in `src/orbitflow/vendors/ubiquiti/interfaces.py` accepts one exact three-line fixed-width header. Real EdgeSwitch devices have at least two *valid* variants:

- Standard, six-column: `Port | Name | Link State | Physical Mode | Physical Status | Flow Control Status`.
- Media variant, seven-column: the same columns with `Media Type` inserted before `Flow Control Status`. Four captured devices returned this layout and hit `parse_interfaces_status`'s exact-header rejection. A fifth has the same log location but no raw output capture; do not assert its variant as confirmed.
- A standard-format device uses a non-breaking space (U+00A0) **inside the Name/description field** for port `0/4`. Current fixed-width row parsing rejected it. Fix Unicode whitespace handling without shifting column boundaries or changing the description's meaning.
- Both variants show blank names, `Auto D` physical modes, and short `3/x` rows that omit trailing columns; valid `Up`/`Down` link state remains authoritative. `Flow Control:Disabled` appears as a footer.

The command remains `show interfaces status all`; do not invent fallback commands, skip invalid rows, or silently mark malformed non-empty output as an empty successful collection. Select parsing offsets from an explicitly recognised header variant, not from arbitrary terminal text. Preserve port IDs, source descriptions and link state, and reject unknown/truncated tables.

A parser exception wrapped by `InterfaceCapabilityError` indicates the interface-observation capability failed, **not** that a particular physical switch port is broken. Diagnostics log exception category and safe code location, not raw device output. Add deterministic sanitized fixtures for both layouts, U+00A0 descriptions and short `3/x` rows before changing behaviour; run vendor/shared capability regressions and operator live validation for all six affected devices. Full device evidence, IP inventory and future issue acceptance criteria: `docs/operations/edgeswitch-interface-status-observations-2026-10-08.md`.

**Scope boundary:** Keep EdgeSwitch parser remediation separate from the pending Catalyst/ME3600X/Huawei VLAN resolver and `wrong_configuration` policy work.

## Access VLAN Baseline

Conceptual candidate:

```text
configure
interface <Port Name>
description "<Description>"
vlan pvid <VLAN>
vlan participation include <VLAN>
vlan tagging <VLAN> disable
exit
write memory
```

Pre/post checks may include:

```text
show running-config interface <Port Name>
show interfaces status all
show vlan
```

Verification should confirm interface existence, matching description, requested PVID, VLAN participation, and untagged/access state.

## Firmware Caveat

EdgeSwitch syntax may vary by firmware.

If an expected command is rejected, capture failure and stop that row. Do not guess alternate syntax unless the platform profile/task explicitly defines it.

Rollback must use captured pre-change configuration; do not guess previous state.


## VLAN Observation

Approved read-only configuration source:

```text
show running-config
```

Parse the global `vlan database` section and VLAN lists/ranges.

Per-interface VLAN facts may include:
- `vlan pvid <id>`;
- `vlan participation include <vlans>`;
- `vlan participation exclude <vlans>`;
- `vlan tagging <vlans>`.

Confirmed customer/hybrid example:

```text
vlan pvid 445
vlan participation include 445,1101
vlan tagging 1101
```

Interpret VLAN 445 as PVID/untagged, VLAN 1101 as tagged, and both as referenced VLANs.

A trunk/uplink may participate in and tag the same broad VLAN set. Preserve observed membership/tagging facts and let the later analysis layer decide consistency.
