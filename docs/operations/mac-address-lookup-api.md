# MAC lookup Python API

Read-only, synchronous APIs; no web server, peer traversal or configuration writes.
Requires the normal OrbitFlow Python dependencies and resolved device context.
Caller owns the established transport session. Commands and validation status are
listed in the [manual](../user_manual/mac-address-lookup.md).

```python
from orbitflow.capabilities.mac import MacService, normalize_mac, parse_mac_table
from orbitflow.capabilities.bridge_domains import BridgeDomainService, parse_bridge_domains
from orbitflow.capabilities.mac_forwarding import enrich, lookup_vlan

snapshot = MacService(timeout=30, xr_location="0/RP0/CPU0").collect(session, context, cli=cli)
hits = snapshot.lookup(mac="AABB.CCDD.EEFF")
exact = snapshot.lookup(interface="Gi0/24+Efp3999", platform=context.platform)
parent = snapshot.lookup(interface="Gi0/24", platform=context.platform, include_children=True)
# Optional independent collection, XR only:
bridges = BridgeDomainService().collect(session, context, cli=cli)
rows = enrich(snapshot, context, interfaces, vlans, bridges)
vlan_rows = lookup_vlan(rows, 445)
```

`normalize_mac(str)` accepts exactly dotted xxxx.xxxx.xxxx, colon xx:xx:xx:xx:xx:xx
or Huawei xxxx-xxxx-xxxx, case-insensitively; invalid values raise fixed ValueError.
`parse_mac_table(output, platform)` accepts cisco_ios/cisco_xe/cisco_xr/huawei_vrp/
ubiquiti_edgeswitch. Unrecognized, malformed, truncated and command-error tables
raise ValueError; a recognized completed header-only MAC table succeeds empty.
The collector's shared CLI requires command completion before parsing.

`MacSnapshot` exposes entries, total, scoped_totals, source and local `lookup` filters
(mac/interface/domain/platform/include_children=False). Local results count their
own entries. Exact lookup keeps duplicate records. `MacEntry` fields are mac,
domain, attachment, original_type, kind, scope and ifindex (Huawei supporting
PEVLAN/CEVLAN/LSP fields are retained in this destination-detail field).

`BridgeSnapshot.lookup(interface=None, neighbor=None, pw_id=None, internal_id=None)`
requires at least one exact key; neighbor requires PW pair. `for_destination(str)`
handles XR local, remote tuple and routed internal-ID destinations. Results are
tuples: zero and multiple results remain unresolved. Domains expose attachments,
state and counts; references do not create InterfaceRecords. Counts retain reported
ACs/VFIs/PWs/PBBs/VNIs totals and `<kind> up` values without comparison.
Malformed AC/PW content, unknown section headings and nonempty VFI sections raise
ValueError. Known `List of VFIs:` and `List of Access VFIs:` headings are valid
empty boundaries, including consecutive sections and trailing sections; no VFI
forwarding semantics are inferred. Empty AC/PW sections also succeed.

`resolve_attachment(attachment, platform, interfaces, vlans=None)` returns
attachment/physical/classification/port_type/semantics. `enrich(snapshot, context,
interfaces=(), vlans=None, bridges=None)` returns one EnrichedMac per input entry,
including normalized domains (XR: full group/domain), VLANs and explicit mapping outcome.
XR VLAN proof requires the exact normalized configured bridge-domain binding
identity to agree with the unique operational group/domain, for local and remote
MAC destinations. Same domain names in different groups do not prove a match. `lookup_vlan`
requires an integer 1-4094, returns only proven matching observations.

Issue #132: `MacEntry.scope` retains `vlan` or `bridge-domain` for IOS/IOS-XE
source tables; existing Huawei slot and XR scope semantics remain. Enrichment
preserves explicit ME3600X/ASR920 numeric VLANs, exact EFP encapsulation, and
`3/N` EdgeSwitch logical `lag N` ownership only with one exact independently
observed/configured aggregate identity (raw attachment/IfIndex unchanged). Missing
or ambiguous identities remain unresolved; member references are insufficient.
A uniquely joined/configured XR untagged AC may associate with the one distinct
explicit dot1q VLAN of configured peers in that exact group/domain. Zero/multiple
peer tags and ambiguous bindings remain Unknown; ingress semantics stay untagged.

The reusable `orbitflow.compliance.resolvers.forwarding_classifications(context,
state)` returns immutable `ForwardingClassification(interface_name, port_type,
configuration_owner)` tuples through existing family validation, without policy
execution. Missing configuration/unsupported families return an empty tuple.
It exposes classification, not numeric audit memberships as ingress VLANs.

Application entry points in `orbitflow.mac_lookup`:

- `resolve_target(targets, address)`: one canonical matching workbook row;
  deterministic missing/ambiguous/missing-credentials ValueError before connection.
- `collect_device(target, transport_config, store, *, mac=None, vlan=None,
  xr_location='0/RP0/CPU0')`: one device, five normalized row groups (main/details/
  totals/errors/operational bridge attachments). Collection failure raises; optional enrichment failures produce
  errors while preserving MACs. A valid empty selection is distinct from failure.
- `run_lookup(targets, transport_config, *, mac=None, vlan=None,
  inventory_path='data/inventory/inventory.json', reports_dir='outputs/reports/mac_table',
  spool_root='outputs/runs/mac_table', log_root='outputs/logs', execution_config=None,
  xr_location='0/RP0/CPU0')`: Path of one workbook; uses shared execution defaults
  when no ExecutionConfig supplied. Menu/CLI explicitly use concurrency 1 by default.
- `export_mac_spool(spool_path, path, *, allow_partial=False)`: offline Path result;
  refuses wrong task or incomplete run by default, retains spool after success.

Direct API callers supply credentials through normal target/transport interfaces;
never put them in source or logs. Known target credentials are removed from persisted
normalized values. Details includes full display Observed Attachment and separate
Raw Attachment; the six main columns are unchanged. Empty operational domains
retain a Bridge Domains row with blank attachment identity fields and supplied counts.
Export failure preserves the spool and propagates the error.
