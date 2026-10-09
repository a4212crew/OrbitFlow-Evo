# Methodology Patterns 8, 10, 11 and 12 — Issue #85

Implemented and tested with synthetic saved configurations. Operator-controlled
live report validation is required before completion/merge approval. No device
configuration changes or new collection commands are introduced.

| Pattern | Expected methodology report outcome |
|---|---|
| 8: pseudowire | Global `pseudowire-class NAME` is service context with no interface identity. Actual `interface pseudowire...` / PW-Ether / PW-IW stanzas retain configured and observed identity. Known pseudowire-only commands are evidence, with no M01–M08 assignment and `not_applicable`; forwarding, neighbor and attachment validation is out of scope. Unsupported encapsulation still requires review. |
| 10: routed BVI | An existing BVI explicitly attached with `routed interface BVI...` to one XR bridge-domain is `standard_configuration`, finding `VALID_ROUTED_BVI_ATTACHMENT`, and routed service context without M04. No `l2transport` is required. Missing BVI, non-routed or conflicting attachment references retain review and exact evidence. |
| 11: untagged XR | An existing l2transport subinterface with `encapsulation untagged`, its configured parent and one explicit ordinary bridge-domain attachment is standard M04, finding `VALID_UNTAGGED_BRIDGE_DOMAIN_ATTACHMENT`. The named domain remains visible; numeric ingress/audit VLAN stays empty. Missing, invalid or conflicting references remain reviewable. Suffixes and descriptions never establish a tag. |
| 12: EVC | ASR920/ME3600X service instances resolve through local `bridge-domain` or global `member <interface> service-instance <id>`. Optional `split-horizon group <nonnegative integer>` is accepted, with exact text retained. Matching local/global bindings retain M02 and M03 and are standard. Missing interfaces/SIs, conflicts, malformed modifiers and invalid/unresolved BDs remain reviewable even on shutdown interfaces. Existing ME3600X trunk/allowed-none and non-overlap standards still apply. |

Pattern 9 EdgeSwitch handling, M01–M08 scope, workbook columns, sanitization and
VLAN compliance remain unchanged. Original audit findings remain in structured
methodology Details even where the standards projection recognises a valid
untagged/BVI context. Consequently the separate compliance workbook can still
show its existing numeric-mapping/non-l2transport findings. Methodology standards
do not override policy, validate live forwarding or approve configuration.

## Operator post-PR run

From the installed project environment, use the existing read-only command,
substituting the approved target workbook and your existing Teleport parameters:

```powershell
python scripts/device_vlan_compliance.py run "<targets.xlsx>" --proxy "<proxy>" --cluster "<cluster>" --bastion-host "<bastion-host>" --bastion-user "<bastion-user>" --methodology-report --keep-spool
```

Linux retains the existing `--teleport-key-path` and `--teleport-cert-path`
options. Keep credentials in the established operator-controlled input flow;
the command requires no new credential arguments. Reports default to
`outputs/reports/vlan_compliance/`; retained spools are under
`outputs/runs/vlan_compliance/`. The extra workbook is
`methodology_resolution_<run-id>.xlsx`.

1. Include representative pseudowire, NCS540 BVI/untagged, ASR920 and ME3600X
   local/global EVC devices, plus unchanged Huawei, Catalyst and EdgeSwitch controls.
2. Check Run Errors first, including methodology failures. A failed collection
   or unavailable-evidence row is not a successful validation.
3. In Methodology Resolution and Details, verify the outcomes above against
   Evidence Details, including source line, full interface/SI identity, domain
   attachment and original CLI. Check genuine unresolved references still appear,
   including on shutdown interfaces. No synthetic interface should appear for
   a global pseudowire class or missing service reference.
4. Compare the compliance workbook with the prior report for the same saved
   configuration, policy and identities. Database/interface memberships, health,
   trigger applicability and missing VLANs must remain unchanged. Account for
   actual device/configuration changes between collections.
5. Record the run ID, tested families/patterns, report outcomes and unresolved
   exceptions for engineer review. Engineering Review Decision remains
   `not_reviewed`; automated classification does not constitute sign-off.

Recover the methodology workbook without further device access using:

```powershell
python scripts/device_vlan_compliance.py export "<spool-path>" "review.xlsx" --methodology-report --keep-spool
```

Deterministic coverage: `tests/test_methodology_relationships.py`, the existing
methodology suites and VLAN audit/observation suites. Frozen compliance hashes
were captured using the pre-Issue #85 configuration-fact parser on the new
synthetic cases; tests compare full compliance results and verify nonmutation.
