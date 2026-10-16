# Configuration execution and standalone observation API

Canonical CLI and operational semantics: [execution manual](../user_manual/configuration-execution.md).
These synchronous Python APIs do not require an HTTP server. XLSX is an optional
adapter; applications can submit normalized per-row decisions directly.

```python
from orbitflow.configuration.v2.planning import load
from orbitflow.configuration.execution import ExecutionService, ApplySettings, export_results

original = load('plan.json')
service = ExecutionService()  # authority_dir='data/configuration/execution'
prepared = service.prepare(original, {'SOURCE_ROW_ID': 'Approve'},
                           expected_digest=original.digest,
                           settings=ApplySettings(max_concurrent_devices=1))
# Alternative: service.prepare_workbook(original, 'plan.xlsx', expected_digest=original.digest)
# Display prepared['summary']; await the caller's separate explicit confirmation.
```

`prepare(original: BulkPlan, decisions: dict, *, expected_digest: str,
settings=ApplySettings()) -> dict` validates immutable content and decision/dependency
intent without connecting. Decisions are row-ID mappings; values Pending/Approve/Reject;
existing plan values fill omitted decisions. `prepare_workbook(original, workbook,
*, expected_digest, settings=ApplySettings())` validates protected XLSX cells and
passes decisions to the same boundary. Both return `status`, `reference`,
`summary_digest`, `summary`, `run_path` (empty until allocation). New summaries have `awaiting_confirmation`; repeated
summaries expose their existing claimed/completed/interrupted status and reference.
Summary selected entries contain request/result/identity/verification_commands;
skipped entries retain row ID, decision and reason. Settings bind concurrency,
timeouts and connection pacing/retry. Save behavior is disclosed in the summary.

`ApplySettings(max_concurrent_devices=1, command_timeout=30.0, save_timeout=300.0,
connection_start_interval=1.0, connection_retry_delay=5.0)` is frozen. Concurrency is
a positive integer; timeouts are finite positive seconds; pacing/retry are finite
nonnegative seconds. No read-only concurrency is implicitly inherited.

After obtaining explicit confirmation of that exact summary:

```python
# credentials: existing in-memory IP -> DeviceCredentials mapping.
# transport_config: existing TransportConfig; never put secrets in preparation.
spool = service.confirm(prepared['reference'],
                        summary_digest=prepared['summary_digest'], apply=True,
                        credentials=credentials, transport_config=transport_config)
export_results(spool.path, spool.path / 'api-execution-results.xlsx')
```

`confirm(reference, *, summary_digest, apply=False, credentials=None,
transport_config=None, inventory_path='data/inventory/inventory.json',
run_root='outputs/runs/configuration_execution',
backups_dir='outputs/backups/configuration') -> ResultSpool` consumes the reference
transactionally before connection. `apply is True` is mandatory. No actor label is
authentication. Digest mismatch, missing reference, corruption and replay raise
`PlanError` before device access. A run interruption consumes confirmation permanently
and preserves its `run_path` in the local database when allocation succeeded.
Per-device/row failures are durable outcomes, not exceptions that pause safe peers.
Infrastructure/persistence failures can raise; do not retry confirm blindly.
`ResultSpool.records()` streams sanitized final device outcomes, while the incremental
journal preserves actions from unfinished devices. `export_results(run_path, output)`
is offline, refuses an existing output and returns its Path. See the manual for sheets,
interruption semantics, logs, permissions and limitations.

## Switchport collectors and pure parsers

```python
from orbitflow.capabilities.switchport import SwitchportService
from orbitflow.vendors.cisco.switchport import parse_switchport_output as parse_cisco
from orbitflow.vendors.ubiquiti.switchport import parse_switchport_output as parse_edge

facts = parse_cisco('Switchport: Enabled\nAdministrative Mode: static access\n'
                   'Access Mode VLAN: 1033 (Customer)')
assert facts.facts['access_vlan'] == 1033
edge = parse_edge('General Mode PVID: 1\nGeneral Mode Untagged VLANs: 1\n'
                  'General Mode Tagged VLANs: \nProtected Port: True in Group 0:')
assert edge.facts['protection']['group'] == 0

# session/context/cli already established by shared transport and inventory:
observed = SwitchportService(timeout=10.0).collect(
    session, context, 'GigabitEthernet1/0/1', cli=cli)
payload = observed.to_dict()
```

`SwitchportService(*, timeout=10.0).collect(session, context, interface, *, cli, correlation=None)`
borrows the same live DeviceSession/DeviceCLI; it never reconnects or closes them.
Supported family/platform/profile pairs: C3750X/cisco_ios/c3750x_switching,
C3850/cisco_xe/c3850_switching, EdgeSwitch/ubiquiti_edgeswitch/edgeswitch (empty legacy
profile also accepted). It performs required shared paging/Cisco width setup,
then `show interfaces <interface> switchport` (Cisco) or
`show interfaces switchport <interface>` (EdgeSwitch). Invalid/unsupported targets,
rejected/unrecognized output and failed exchanges raise fixed `SwitchportCapabilityError`;
shared CLI exchange failures invalidate synchronization. Results are serializable
`SwitchportObservation(fields: dict, facts: dict, evidence: str)` with `.to_dict()`.

Pure `parse_switchport_output(text: str) -> SwitchportObservation` functions use no
session, XLSX, transport, logging handlers or execution state. Duplicate labels raise
ValueError; malformed/missing typed values are None. Recognized blank lists are `[]`,
ALL/NONE retain symbolic strings, explicit lists expand ranges inclusively and retain
VLAN 1. Wrapped lists and all original labels/values are preserved. Cisco facts:
enabled, administrative_mode, operational_mode, access_vlan, native_vlan, allowed_vlans.
EdgeSwitch facts: pvid, untagged_vlans, tagged_vlans, forbidden_vlans, optional name,
protection {enabled, group, raw}. Missing Name is None, group zero remains valid,
tagged/forbidden overlap remains independent without warnings/lookups. Pure parser
evidence is input text; the collector applies shared evidence sanitization.

Shared `VlanService.lookup(session, context, vlan_id, *, cli=...)` now retains
sanitized Cisco lookup evidence and complete names. EdgeSwitch results retain legacy
operational_status for planning compatibility and add accurate `vlan_type`, matched
`vlan_id`, `ports_complete`; ports retain interface/current/configured/tagging.
ID/name presence and port-table completeness are independent. Existing artifacts
without the optional additions remain valid. Failed/unavailable lookup is never absence.

## Standalone verification and save

`verify_row(session, context, cli, entry, before, *, timeout=30.0, correlation=None) -> dict` in
`orbitflow.configuration.execution` performs only read-only verification; it sends
no configuration or save commands. `entry` is a selected prepare-summary entry;
`before` is a normalized `configuration.v2.observation.snapshot(context, interfaces,
vlans)` from shared InterfaceService/VlanService on the same session immediately
before the row. Callers performing independent verification must supply that baseline
to prove preservation. Return status Verified/Failed/Unknown plus structured evidence,
warnings where relevant. Collector/transport failures can raise; the executor records
their fixed categories and Unknown/Not executed outcomes. It checks full trunk sets,
native/description/admin preservation and EdgeSwitch configured membership/tagging,
without conflating Current or operational Down. Scoped configuration evidence reuses
existing capability facts. Execution composes this verifier rather than owning it.

```python
from orbitflow.capabilities.save import save_configuration
result = save_configuration(session, context, cli=cli,
                            exec_prompt=original_exec_prompt, timeout=300.0)
```

Save is a separate **configuration-persistence action**; callers need explicit operator
intent. `save_configuration(session, context, *, cli, exec_prompt, timeout, correlation=None)` requires
an already synchronized original privileged EXEC prompt and an approved family/profile.
It returns status Saved/Unknown, sanitized response, answered (EdgeSwitch question),
error_category and explicit_error separately. It borrows resources; no retry, reconnect
or success-marker requirement. Bad preconditions raise ValueError/InteractiveCLIError;
incomplete exchanges return Unknown and invalidate the shared shell. The caller retains
the original learned prompt, not a guessed hostname. Shared `DeviceCLI.execution_mode`
and `DeviceCLI.save_configuration` implement synchronization internally; prefer the
capability wrapper for supported application use.

`ResultJournal(path, *, clean=sanitize_text)` in `orbitflow.result_spool` owns
synchronized fsynced JSONL append; `append(json_value)` sanitizes recursively and
`records()` streams complete lines for recovery. It does not retry failed writes or
retain full runs. Callers must never submit sensitive raw backup content. The executor
uses it for incremental progress alongside the existing central ResultSpool.

Validation commands and pending owner lab checks for Linux/Windows are in the
[canonical manual](../user_manual/configuration-execution.md#validation-and-remaining-limits).

Optional `correlation` mappings on `collect`, `save_configuration` and `verify_row`
(default None) select scalar `run_id`, `row_id`, `digest` metadata only. Example:
`correlation={'run_id': 'lab-117', 'row_id': 'port-3'}`. Resource IP, normalized
interface, collection command, stage, outcome and elapsed seconds are capability-owned.
Save is device-wide; execution supplies run/digest and verification row IDs. Shared
logs retain selected fields and safe exception types/frame locations without raw
responses or arbitrary exception messages.

Collectors require one Cisco `Name` / EdgeSwitch `Port` matching the normalized
requested interface. Missing, duplicate or mismatched headers raise
SwitchportCapabilityError without reconnecting or invalidating a synchronized shell.
Pure parsers still accept incomplete observations. EdgeSwitch VLAN lookup recognizes
Port and Interface headers and rejects malformed/truncated rows as incomplete.
Supplied command-not-found, incomplete-command and VLAN-range diagnostics reject
writes. Save still records Saved on original EXEC return, with explicit_error separate.
