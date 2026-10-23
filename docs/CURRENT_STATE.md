# CURRENT_STATE.md â€” OrbitFlow-Evo Current State

Use this file as the concise source of truth for what is implemented and validated today.


Keep this document short. Historical implementation detail belongs in `docs/devlog/YYYY-MM.md`.

## Offline Configuration Plans (Phases 1â€“2)

`orbitflow.configuration` and `scripts/configuration_plan.py` provide immutable
versioned Change Plans, canonical SHA-256 content digests, inventory snapshot
resolution, strict offline validation/preview and durable digest-bound
approve/reject/expire gates. Manual, spreadsheet, template and compliance
producers share a normalized JSON request; v1 has no source-specific importers.
The separate v2 workflow is described below. The v1 renderer supports VLAN creation on C3750X IOS
and C3850 IOS-XE profiles, including no-op and conflicting-state checks.
SQLite approval history is signed by a separate local key; operator-controlled
authority storage is required and actor labels are not authentication.
Deterministic tests cover the lifecycle, expiry, mutations, tampering, secret
rejection and socket-blocked CLI operation. No apply/live verification or device
changes are implemented. See `docs/architecture/configuration/offline-plans.md`.
The configuration-management skill is installed under `.agents/skills/`; it
distinguishes this v1 contract from the separate predefined execution workflow.

## Bulk Configuration Planning v2

Issue #117 adds separate confirmed predefined execution for C3750X, C3850 and
EdgeSwitch through `orbitflow.configuration.execution` and `execution_cli`.
Prepare validates immutable plan/review decisions without connecting; transactional
summary-bound confirmation prevents replay. Shared per-IP execution uses a separate
apply limit (default 1), fresh identity/state checks, protected backup, exact approved
commands, per-row verification and partial-change saving at device-task end.
New standalone switchport parsers/collectors preserve typed facts and independent
EdgeSwitch Current/Configured/Tagging evidence. Incremental fsynced events and shared
result spools support offline execution-workbook regeneration after interruption.
Issue #139 simplifies confirmed execution: fresh target identity/ownership and known
prerequisites remain checked; execution no longer replans or requires fresh command,
no-op, projected-state or trusted-baseline equality. Exact approved CLI still sends
when already correct. Stage splitting/shared observation, independent verification,
rejection/device isolation, protected backup and EXEC-only partial save remain.
Automated synthetic validation is separate from pending owner/live validation of
this revision. The controller's independent final test gate remains pending.
Issue #134 adds execution-only structural Cisco/EdgeSwitch prompt recognition,
including changing/abbreviated host presentation and arbitrary valid submodes.
Current echo and split-response protections remain required. Checked same-session
EXEC completion anchors exact save return; explicit errors remain separate.
Synthetic regressions cover the Linux C3750X incident and safety/read-only cases.
PR #135 follows the owner's superseding no-added-wait clarification: execution
returns immediately on the current exact echo and complete structural prompt.
Synthetic 260-command tests assert zero added waiting and no extra receives.
Earlier quiet-guard proposals are superseded. Inner sandbox failures remain distinct
from the separate controller gate, whose run report is unavailable to this worker.
Owner Linux C3750X, C3850 and EdgeSwitch live validation of #134 remains pending.
Owner C3750X/EdgeSwitch lab validation following PR #118 is reported; C3850
live validation remains outstanding. Other families,
Manual CLI apply, HTTP, automatic rollback and write replay/resume remain unsupported.
See [execution manual](user_manual/configuration-execution.md) and
[public APIs](operations/configuration-execution-api.md). Planning paragraphs below
describe the v2 planner boundary; apply is the separate explicitly confirmed service.

Issue #106 adds structured ingress conflict evidence and workbook explanations
with service-instance IDs, canonical interfaces, selectors and projected row
provenance. The overlap blocker and digest-bound review remain enforced.
ASR920 disjoint first services on a compatible existing parent are independently
reviewable; ME3600X initial parent conversion dependencies remain required.
Shutdown state is preserved. The nine-row ASR920 Gi0/0/8 regression covers SI
1012 and 2400–2407 with repeated BD 1237 and no false overlap warnings or
approval dependencies. The input workbook has one compact 22-template directory
with blue underlined links; detailed guidance remains in comments/docs.
Deterministic regression coverage only; no live apply.

ME3600X independent service instances with disjoint ingress no longer acquire
conflicts or approval dependencies solely from sharing a parent or another row's
safety blocker. Parent initialization and same-object approval gates remain.
Explicit IOS VLAN-name facts distinguish unnamed range declarations from real
name contradictions during configuration/operational reconciliation. Independent
ME3600X/ASR920 EVCs on an established parent produce no shared-parent overlap
warning. Intentional schema-owned child replacements retain the complete diff;
omitted-settings warnings identify dropped optional or unrepresented commands.
VLAN lookup output remains in immutable observations and conflict checks but is
excluded from ME3600X/ASR920 workbook evidence presentation. The representative
11-row scenario retains the row 13 incompatible-parent blocker. Owner read-only
ME3600X validation confirmed rows 3–12 consistent and row 13 blocked before these
presentation corrections; repeat live read-only validation remains pending.
That planning revision did not implement apply; the separate Issue #117 executor is described above.

Ordered planning permits a description alongside another interface operation on
all device families in either workbook order, with explicit compatible-overlap
warnings. Pending VLAN database prerequisites warn without making the plan
unresolved; dependency links remain digest-bound and deployment readiness still
requires prerequisite approval. Genuine conflicts, evidence/identity/ownership
blockers and Catalyst trunk conversion/explicit Add baseline gates remain.
JSON/XLSX and Pending/Approve/Reject regressions use deterministic fixtures only;
no live apply or hardware validation was performed.

Catalyst milestone 1 (Templates 1-8; retained in catalogue 2.3) now has shared operational
VLAN lookup with config fallback, ordered symbolic ALL/exclusion reconstruction,
physical-member access blocking, audited trunk aggregate resolution, exact
logical/physical descriptions and full sanitized interface evidence through `!`.
The single plan workbook retains invalid rows, field errors, conflict references,
resolved targets and separate warnings/blockers. Both Catalyst VLAN name schemas
reject spaces and interface inputs require full names. Deterministic validation
is implemented; owner-controlled live C3750X/C3850X validation and sign-off remain
pending. Catalogue 2.3 implements the approved Templates 9-16 with synthetic
validation: shared EVC ranges/QinQ, separate Push VLAN/symmetry, group zero,
operational detail/config reconciliation, complete parent/child evidence and
mandatory remove/recreate with omitted-child impact. ME/ASR parent and global
BD rules remain distinct. EdgeSwitch Add/Change and Remove preserve independent
participation, exclusion, tagging and PVID, including tagged PVID; absent global
VLAN is informational. Database create/rename/no-op and exact descriptions use
reliable evidence with labeled fallbacks. Workbook help, row isolation, ordered
projections/dependencies and digest-bound single decisions are covered. No live
hardware/firmware validation or device writes were performed. Owner read-only
validation remains required; Templates 17-22 received no new implementation.
Templates 10/12 now project request-scoped parent/child evidence without narrowing
full-device overlap validation. Oversized workbook fields use digest-bound immutable
JSON references; protected-reference tampering fails decision consumption. Synthetic
large-parent and mixed-validity workbook regressions cover export and row isolation.
Owner repeat live read-only validation remains pending.
The Issue #91 review revision distinguishes unverified versus lab-rejected EVC
rewrite blockers, preserves nested child endings, and exposes unique child
before/after/added/removed commands in JSON and the protected single workbook.
Deterministic workbook regressions cover ordered EdgeSwitch Remove/Add and
PVID-change/Remove with independent excluded/tagged facts. The linked complete
22-template [operator reference](operations/configuration-template-reference.md)
labels 17-22 provisional; no live validation or
new template approval is claimed.


Bulk planning v2 now emits flushed per-device read-only collection progress and
sanitized rotating configuration module logs. Description-only requests retain
recognized existing VLAN membership/tagging defects as non-blocking warnings;
material evidence/identity/ownership conflicts and service-change blockers remain.
Validated with deterministic fixtures only; no live smoke testing in this revision.

The shared Cisco EVC detail parser now recognizes hardware Associated Interface
identity and exact per-ID/per-port negative replies, including short input names.
Operational ethertype annotations, QinQ/ranges, descriptions, push/pop and BD
microblocks reuse shared facts while original evidence remains intact. A valid
instance without BD evidence is present with incomplete forwarding; v2 blocks it
and displays the limitation. CLI failures remain error, never absence. Supplied
ASR920/ME3600X response shapes are deterministically covered; owner repeat live
read-only validation of dispatch, response and planner artifacts is still required.

`orbitflow.configuration.v2` adds a separate 22-template catalogue, deterministic
vendor proposals and input/plan XLSX adapters. The plan workbook is the single
Pending/Approve/Reject surface; no separate v2 review command or signing store remains.
V2 default artifacts use outputs/reports/configuration/<local-timestamp>_<target>/plan.json
and plan.xlsx, with atomic collision suffixes; full plan digests remain authoritative.
Explicit destinations and legacy digest-path loading remain supported.
Templates 1–16 output sheets now omit seven internal detail columns; immutable JSON
retains them, while Templates 17–22 keep their output layout. EdgeSwitch port/description
pairs sequence in either sheet order without an approval dependency solely for overlap;
port evidence excludes global VLAN output. ASR920 evidence explicitly distinguishes
reliable per-target absence from lookup failure. Missing ME3600X BD VLAN alone warns,
retaining the ID for future pre-apply checks without auto-creation. These revisions
are deterministically tested; hardware/firmware validation remains operator-controlled.
Digest-pinned decision consumption validates protected cells and returns unauthenticated
in-memory intent without mutating the plan or authorizing execution.
The 21 predefined templates use shared per-device execution/session,
inventory, InterfaceService, VlanService and family audit relationships for
read-only evidence. Manual CLI is literal/offline-only and never connects.
Catalogue 2.3 supersedes earlier EVC/EdgeSwitch inputs: regenerate old v2
workbooks and plans. Legacy service_instance/pop_tags, VLAN Port mode/vlans/
replace_untagged and Replace are rejected. Existing NCS540 catalogue behavior
is unchanged and remains outside this approval expansion.
NCS540 descriptions preserve observed L2transport/L3 declarations with clean
interface inputs; evidenced ASR920 BDI declarations support logical targets.
Review XLSX evidence is request-scoped with source/line references; internal
device-wide facts remain available for consistency checks. Shared devices.xlsx
loading supports distinct per-IP credentials and isolated missing/duplicate
failures. Operators can select shared sequential execution with a limit of 1.
Manual Scope is metadata; literal CLI supplies its own hierarchy.
V1 plan/approval behavior is unchanged. Audit defaults retain existing policy
bounds; an explicit planning projection uses platform numeric bounds and NE05E
single-tag VSI relationships without changing compliance outputs.

Same-device sheet/row order, original inputs, source provenance, observations,
dependencies, no-ops and impact/conflict findings are digest-bound. Workbook
decisions remain separate unauthenticated intent pinned to that source digest. Decision consumption rejects other edits and re-evaluates prerequisites
and evidence age. Unresolved evidence/ownership/conflicting overlaps and unknown Manual CLI
effects cannot become deployment-ready. Collection uses recoverable shared
spools; bounded single-workbook limits are documented. Planning supplies no execution
authorization; the separate Issue #117 service above requires confirmation. Deterministic tests cover all 22 templates,
workbook integrity lifecycle, collection reuse and v1 regressions. No live smoke
test has been run. Commands and limits:
`docs/operations/bulk-configuration-planning.md`.

## Project

OrbitFlow-Evo is a multi-vendor ISP network automation platform designed to scale toward approximately 1,500 network devices.

Core rules and skill routing are defined in `AGENTS.md`.

## Architectural Direction

OrbitFlow is being developed as a reusable network-equipment capability platform and future OSS layer.

The intended dependency flow is:

```text
External OSS/BSS / REST API / GUI / schedulers
        -> Integration layer
        -> Application / workflow layer
        -> Reusable device capability layer
        -> Vendor-specific implementation
        -> DeviceSession / transport
        -> Network equipment
```

Key rules:
- separate target input from observed device identity;
- resolve management IP + credentials into a reusable DeviceContext where supported;
- treat stored inventory as latest-known observed context, not a CMDB/source of truth;
- implement each network-device capability once;
- vendor-specific command/parsing logic remains isolated;
- normalize CLI output into reusable structured models;
- workflows compose capabilities for audit, troubleshooting, provisioning, remediation, service assurance, and similar functions;
- REST/API consumers must call the same application/capability interfaces as internal workflows;
- separate observe -> analyze -> plan -> apply -> verify -> record;
- do not make raw CLI execution the primary external OSS interface.

Detailed model: `docs/architecture/device-capability-oss-model.md`.

## Current Architecture

### Shared Device Execution

`orbitflow.execution.execute_devices` provides bounded per-device workers,
dynamic refill, isolated safe outcomes, copied logging context, synchronized
progress, and input-ordered aggregation. `orbitflow.toml` configures
`execution.max_concurrent_devices` (default 5); limit 1 runs sequentially.
Inventory refresh/export and Interface/VLAN reporting both use this layer.
Workers own their resolver/context/session/CLI and per-device capabilities;
Interface and VLAN collection remain sequential within one device. Workbook
writers run on the caller after device cleanup.

`orbitflow.result_spool.ResultSpool` persists sanitized per-target envelopes and
normalized task payloads in unique run directories. Both output workflows use
caller-owned completion sinks, disk-backed input ordering, and write-only Excel
consumption; complete report/attempt row sets are no longer retained in memory.
Inventory exports capture a run snapshot without replacing canonical inventory.
Public report/inventory spool consumers retry output without device connections.
Successful consumption removes temporary runs; failed/interrupted runs remain,
with exclusive OS leases and explicit age-cutoff stale cleanup. Partial recovery
is opt-in and remains retained. See `docs/architecture/result-spool.md`.
Completed-spool removal retries transient permission denials with bounded delays;
exhaustion warns without failing successful output and retains a cleanup-only
manifest for subsequent removal.
Manifest atomic replacement now uses four bounded permission attempts without
replaying appends. Persistence failures stop collection, preserve the original
error even if interruption marking fails, and retain canonical JSONL for explicit
partial recovery with reconciled counts. Compliance summaries use persisted
records. Spool-backed CLIs record sanitised run-level exception chains/code
locations outside device logger scopes. Deterministic fault-injection coverage
is implemented; operator confirmed successful 686-target live validation and PR #68
was merged as Issue #67.
Deterministic scale coverage includes 1,500 targets at concurrency 5; live network
scale validation remains operator-controlled.


Inventory store instances share a resolved-path transaction lock, preventing
lost reconciliations and failure updates within one process. Inventory facts
follow transaction order; exported attempts and run-status aggregation retain
input order. Paramiko routing is reference-counted across overlapping connection
scopes and restored after the last exits; rotating writers are shared by log
path. Raw dependency diagnostics remain omitted and unattributed; caught errors
retain device metadata. Cross-process inventory/log writers and shared export
destinations remain unsupported. Deterministic tests cover concurrency and both
workflows; no live concurrency validation has been performed.

### Device Inventory / Identification

The device inventory/identification MVP is implemented. `DeviceInventoryResolver`
accepts an existing `DeviceSession` plus management IP, reuses that session, and
returns normalized `DeviceContext` stable facts.

Current behaviour:
- deterministic detection of Cisco IOS, IOS-XE, IOS-XR, Huawei VRP, and Ubiquiti EdgeSwitch;
- EdgeSwitch hostname extraction structurally accepts parenthesized exec prompts ending in `#` or `>`, including angle-wrapped hostnames such as `(<LAB-ES24>) >` and optional nested annotations of arbitrary text, normalizes to the base hostname, rejects malformed delimiters, and retains simple `hostname#` / `hostname>` support. Full-banner and fragmented-receive regressions cover identity, enable safety, continued observation/compliance and configuration capture; hardware read-only verification remains pending;
- family/profile selection for ASR920, C3850, C3750X, ME3600X, NCS540, NE05E, and EdgeSwitch;
- ME3600X remains `cisco_ios` while retaining an EVC-capable profile;
- serial-first physical identity reconciliation across management-IP changes;
- likely replacement/reassignment and hostname-collision event reporting, with no unsafe merge when serial evidence is absent;
- atomic latest JSON snapshots containing stable facts only and no credentials; Windows access-denied/sharing-lock replacement failures receive three short retries (0.3 seconds total), with best-effort temp cleanup and persistent failures still surfaced;
- failed attempts preserve the last successful facts while updating sanitized attempt status and error metadata;
- explicit controlled platform override support;
- returned context is suitable for capability and workflow consumers without duplicating detection logic.

`orbitflow.inventory_refresh.refresh_inventory_from_excel` refreshes only the
current Excel targets through the shared loader/resolver/store and exports all
latest inventory identities. Workbook rows distinguish refreshed, failed with
previous facts retained, and not requested identities; a separate attempts sheet
includes unresolved failures. Connection/input failures preserve existing facts.
Historical snapshots and production scheduling remain future work.

`scripts/device_inventory_refresh.py` provides the operator command with the
existing Excel/Teleport argument contract and configured shared execution.
It defaults to canonical `data/inventory/inventory.json`, unique timestamped
workbooks under `outputs/reports/inventory/`, recoverable spools under
`outputs/runs/inventory_refresh/`, and shared module logs under `outputs/logs/`.
It reuses the refresh/export workflow without changing reconciliation or vendor
support. Deterministic command tests cover path overrides, distinct exports,
isolated failures, retained facts, spool recovery, and credential exclusion.
Legacy command defaults are unchanged; no live command validation was performed.

Documentation baseline:
- `.agents/skills/device-inventory/SKILL.md`
- `.agents/skills/excel-inventory/SKILL.md`
- `docs/architecture/device-capability-oss-model.md`

### Transport

All network-device access uses the shared OrbitFlow transport layer.

**Windows**
- Validated Teleport local-port-forward model using `tsh ssh -N -L`.
- Tunnel startup retries local-forward connections within `connect_timeout`.
- The first connected local-forward socket is retained and passed directly to
  Paramiko; OrbitFlow does not read or consume the device's SSH banner.
- Live validated successfully.

**Linux / Ubuntu**
- Validated `tsh proxy ssh` + Teleport private key/certificate + Paramiko `direct-tcpip` model.
- A second Paramiko session connects to the target device through the bastion channel.
- Live validated successfully.

Both target-device paths first use normal Paramiko authentication. If password
authentication is rejected, the shared target authenticator retries with
keyboard-interactive authentication using the same `DeviceCredentials.password`.
It responds only to prompts explicitly identified as password prompts. This
fallback does not affect Teleport/bastion authentication.

Higher-level workflows must use `connect_device(...)` / `DeviceSession` and must not recreate OS-specific transport.

### SSH Host-Key Behaviour

Current deployment defaults:
- `verify_bastion_host_key=False`
- `verify_device_host_key=False`

Permissive mode uses Paramiko `AutoAddPolicy` without persisting learned keys.

Strict verification remains configurable for future use. Custom Teleport CA verification is not implemented.

### Interactive CLI and Device Capabilities

Implemented reusable `CiscoIOSCLI` above `DeviceSession`.

Current behaviour:
- dynamic prompt detection for prompts ending in `#` or `>`;
- automatic `terminal length 0`;
- timeout-aware prompt reads using monotonic deadlines;
- command-echo synchronization to prevent stale prompts from completing a newly sent command;
- command echo removal;
- ANSI/control-sequence cleanup;
- trailing prompt removal;
- prompt changes tracked dynamically.

Windows live-device validation passed against Cisco ASR920 `NSW-STLEON-21CANB-BAS1` running IOS XE 17.06.07. The validation confirmed correct prompt detection, paging disablement, complete `show version` output, clean output handling, stale-prompt fix, and clean session teardown.

Implemented one reusable `InterfaceService` and normalized `InterfaceRecord` for
Cisco IOS, IOS-XE, IOS-XR, Huawei VRP / NE05E, and Ubiquiti EdgeSwitch. Each
platform has an isolated command/parser adapter, uses `DeviceSession`, disables
paging with the approved platform command, and returns a clear error for a
rejected setup or collection command. Empty command output produces an empty
collection; unrecognized non-empty output is a parser failure. The capability
does not guess fallback commands after a rejection. Huawei accepts both the
status-bearing and description-only forms of `display interface description`;
for the description-only form it uses the approved `display interface brief`
fallback and joins status by Huawei-canonical interface name (`Eth`/`Ethernet`,
`GE`/`GigabitEthernet`, `Loop`/`LoopBack`, and `Tun`/`Tunnel`), while preserving
the description-side name and subinterface suffix in normalized output. Known VRP
brief legends and protocol
suffixes such as `up(s)` are accepted; PHY remains authoritative for normalized
status. The
IOS-XR parser accepts
the platform's timestamp line before the interface table while remaining strict
about other unexpected content. `device_name` is optional:
vendor adapters extract it from their already-detected CLI prompt, while an
explicit caller-supplied name remains a compatibility override.
EdgeSwitch uses only `terminal length 0` and `show interfaces status all`; its
parser accepts both verified six-column and seven-column (`Media Type`) headers
with layout-specific fixed boundaries. Deterministic InterfaceService regressions
cover Unicode description whitespace (including the captured port `0/4` U+00A0
case), character/UTF-8 byte-counted padding, blank names, `Auto D`, and short
`3/x` rows. Port names and descriptions are preserved; Up/Down is authoritative
and unavailable admin state stays empty. Unknown/incomplete headers, malformed
rows and rejected commands remain failures without raw row text in parser errors.
Issue #70 is ready for operator live validation on the six previously failing
devices; remediation has not been live validated. `10.121.9.3` still needs its
actual CLI output checked because its layout was not captured. Evidence:
`docs/operations/edgeswitch-interface-status-observations-2026-10-08.md`.
VLAN resolver/configuration-health behavior is described in the audit section below.

Implemented reusable read-only `VlanService` for Cisco IOS, IOS-XE, IOS-XR,
Huawei VRP, and Ubiquiti EdgeSwitch. It uses each platform's approved full
running-configuration command through the existing prompt-aware session layer.
The normalized snapshot separates interface VLAN references from VLAN,
bridge-domain, and service identities. Vendor adapters preserve classic
switchport/database, IOS-XE EVC, IOS-XR subinterface/L2VPN, Huawei
VLAN/Vlanif/dot1q/VSI, and EdgeSwitch participation/PVID/tagging semantics.
IOS-XE and IOS-XR bridge domains and Huawei VSIs are normalized as equivalent
service objects without treating their identity as a VLAN ID. IOS-XE EVC
bridge-domain modifiers such as split-horizon settings are excluded from that
identity. IOS-XR L2VPN
bindings preserve hierarchy and routed BVI membership, including interface
descriptions from bound interface blocks that have no encapsulation statement,
without deriving VLAN IDs from interface names. Huawei termination
observations retain both control VID and dot1q termination VID facts.
Observation performs no consistency or compliance decisions.

`scripts/live_validate_interfaces.py` provides a deliberately limited
single-device integration entry point for live validation of this existing
capability. It accepts caller-supplied credentials and `TransportConfig`, resolves
inventory first, then prints normalized records using the same established session.

Both services accept `collect(session, context)` with a resolved `DeviceContext`;
legacy `device_ip`/`platform`/optional `device_name` keyword calls remain supported.
Context supplies observed identity, and VLAN selection uses Cisco EVC profile,
family, or flags without changing the OS/platform (including ME3600X on IOS).
Both validation runners accept `platform=None` for automatic detection, or an
explicit resolver override, and an optional `inventory_path` (default:
`data/live_validation/inventory.json`). Inventory and capability collection reuse
one connection. Vendor parsers, commands, and normalized output models are unchanged.

`scripts/live_validate_vlans.py` provides the equivalent single-device,
operator-prompted integration harness for `VlanService`. Its current target and
non-secret Teleport routing defaults are grouped at the top of the script; a
direct invocation prompts only for the device password. It prints normalized
VLAN/service objects and interface observations for manual comparison; its
existence does not constitute live validation of the VLAN capability.

## Repository Structure

Current major implementation areas:
- `src/orbitflow/transport/` â€” shared and OS-specific transport;
- `src/orbitflow/vendors/cisco/` â€” Cisco IOS/IOS-XE CLI behaviour;
- `src/orbitflow/vendors/huawei/` and `src/orbitflow/vendors/ubiquiti/` â€” vendor interface collection/parsing;
- `src/orbitflow/capabilities/` and `src/orbitflow/models.py` â€” reusable interface/VLAN capabilities and normalized records;
- `src/orbitflow/inventory/` â€” identification, reconciliation, and latest JSON snapshot storage;
- `scripts/live_validate_interfaces.py` â€” single-device interface integration validation;
- `scripts/live_validate_vlans.py` â€” single-device VLAN integration validation harness;
- `tests/` â€” deterministic mocked/unit tests;
- `.agents/skills/` â€” task/vendor-specific implementation guidance.

## Validation Baseline

- Windows transport: live validated.
- Linux transport: live validated.
- Cisco IOS/IOS-XE interactive CLI on Windows: live validated.
- Current automated test suite includes transport and Cisco CLI regression coverage.
- Device inventory tests cover all five platform identifiers and seven required families, override/ambiguity handling, reconciliation, failure retention, and secret exclusion.
- Interface capability tests cover all five platform identifiers with deterministic fake sessions.
- Interface capability has now been live validated on Cisco IOS, Cisco IOS-XE, Cisco IOS-XR, Huawei VRP, and Ubiquiti EdgeSwitch.
- VLAN observation has deterministic parser and command-selection coverage for
  all five platform identifiers and is now live validated across all five
  supported platforms: Cisco IOS, Cisco IOS-XE, Cisco IOS-XR, Huawei VRP, and
  Ubiquiti EdgeSwitch. Cisco IOS VLAN observation is live validated
  on the 3750X-class device `R-GEEL-MERCER-BCS1` at `172.25.20.2`, covering VLAN
  database discovery and names, access ports and non-default access VLANs, trunk
  mode, native VLANs, explicit trunk allowed VLAN lists, absent allowed-list
  behavior, VLAN list/range expansion, and interface descriptions. Validation
  also confirms the observation/policy boundary: the observer retains VLANs
  referenced on an interface even when they are absent from the observed VLAN
  database, without making a compliance decision. Cisco IOS-XE VLAN observation
  is live validated on the ME3600X at `10.251.10.50`, covering VLAN database
  entries and names,
  access VLANs, trunk allowed VLAN lists (including explicit `none`), VLAN range
  expansion, EVC dot1q and untagged encapsulations, multiple service instances
  per interface, and bridge-domain discovery/binding. Validation also confirms
  that bridge-domain modifiers are excluded from service identity and that VLAN
  IDs are not inferred from service-instance or bridge-domain identifiers.
  `mode=unknown` is expected when an access VLAN is configured without an
  explicit `switchport mode access` statement. Huawei VRP VLAN observation is
  live validated on NE05E device `R-WIND-168HIGH-RTR1` at `10.251.0.17`,
  covering the `vlan batch` VLAN database, `Vlanif`, `port default vlan`,
  `port trunk allow-pass vlan`, tagged trunk VLANs, `vlan-type dot1q`, `dot1q
  termination`, `control-vid`, and `l2 binding vsi` constructs. Validation
  confirms that VSI identity remains separate from VLAN identity and that VLAN
  identity is not inferred from VSI names. The live device used matching
  control VID and termination VLAN values; differing values remain covered by
  regression tests rather than this live validation. Ubiquiti EdgeSwitch VLAN
  observation is live validated on `R-ELST-TMARK-BAS8` at `10.125.13.138`,
  covering the VLAN database and VLAN ranges, VLAN names, `vlan pvid`, `vlan
  participation include`, `vlan participation exclude`, and `vlan tagging`.
  The validation confirmed tagged and untagged/PVID normalization across both
  physical and LAG interfaces, while preserving the observation/policy
  separation. Live validation records only the constructs exercised on the
  validation devices; other supported syntax remains covered only by
  deterministic regression tests where previously noted.

## Codex Orchestration â€” OrbitFlow-Evo

A local ChatGPT/Atlas-to-Codex orchestration foundation is implemented in OrbitFlow-Evo.

Current behavior and approved operating model:
- GitHub Issues act as scoped task records and orchestration state;
- Atlas owns architecture, task scope, orchestration coordination, and PR review; Codex is the default implementation engineer for normal feature work;
- direct Atlas coding is reserved for narrowly scoped orchestration/bootstrap repair when the Codex path itself is broken or unavailable;
- the operator workstation runs the cross-platform Python controller at `scripts/orchestration_v2/controller.py`;
- one-task execution (`python scripts/orchestration_v2/controller.py`) is the default operator mode; optional safe `--watch` polling is supported;
- Codex executes locally through the Codex CLI authenticated with the user's ChatGPT account;
- the intended path has no `OPENAI_API_KEY` dependency, no automatic API-billing fallback, and no automatic paid-credit use;
- each task uses an isolated `codex/issue-<number>` Git branch and dedicated Git worktree;
- `--dry-run` is non-mutating and does not create branches/worktrees or change GitHub state;
- the controller runs the deterministic pytest suite as a hard gate;
- failed tests stop the workflow before commit, push, or PR creation/update;
- after tests pass, the controller commits/pushes the task branch, opens or updates the PR, and returns the issue to `codex-review`;
- Atlas-requested corrections use a marked review comment plus `codex-revise` and update the same task branch/PR;
- issue comments track implementation/review iteration state;
- automated revision stops after iteration 10 and moves the task to `codex-replan-required`;
- no workflow auto-merges to `main`; merge still requires explicit user approval;
- Codex receives no Teleport or network-device credentials, and live validation remains local/operator-controlled;
- orchestration code and tests are required to remain portable across Windows and Linux.

Setup requires authenticated GitHub CLI and ChatGPT-authenticated Codex CLI, configured Git author identity, and the orchestration labels listed in `docs/architecture/codex-orchestration.md`. Preflight runs inside the v2 controller; there is no separate bootstrap script.

Validation status: orchestration v2 passed full end-to-end validation, as confirmed by the approved Issue #18 task contract. The user approved retirement of the legacy implementation, which has now been removed.

Detailed model: `docs/architecture/codex-orchestration.md`.

### Operational orchestration v2

`scripts/orchestration_v2/` is the sole operational orchestration implementation and retains its existing directory name.

Implemented phases:
- complete controller-time preflight for Git, Git identity, GitHub CLI authentication, repository identity, clean control checkout, Codex installation, and fail-closed ChatGPT-account authentication checks;
- explicit rejection of an active `OPENAI_API_KEY` path;
- one-task GitHub Issue discovery, `codex/issue-<number>` branch planning, dedicated sibling worktree validation/creation, and non-mutating dry-run;
- local `codex exec --sandbox workspace-write` execution with controller-owned temporary storage outside Git worktrees;
- repository-change detection and a blocking full pytest gate;
- typed failure categories for prerequisite, controller/orchestration, Codex execution, and test failures.

The controller implements controller-owned staging, commit with the preflighted identity, branch push, PR creation/update, the `codex-pr` transition after PR publication, and the `codex-review` transition after successful iteration comments, all after the full pytest gate. State transitions remove only currently attached orchestration labels. Revisions use the latest owner-authored marked review and the same branch/worktree/open PR. A request after 10 successful iterations moves to `codex-replan-required` without invoking Codex. Selected-task failures remove queue labels and retain their typed category; reporting failures surface explicitly. Optional safe watch mode is supported; there is no auto-merge.

Codex and controller pytest temporary files use unique task/purpose-isolated `orbitflow-` directories under the OS temporary directory. Codex receives the external path through `TEMP`, `TMP`, and `TMPDIR`; controller pytest also receives an external `--basetemp`. Cleanup uses bounded retries without administrator privileges or ACL resets, refuses reparse points, and reports retained paths as stderr warnings without blocking Git operations or masking worker/test failures. Full end-to-end validation is complete. After retirement, the full deterministic pytest suite passes (206 tests). The legacy implementation and its implementation-specific tests were retired in Issue #18; Issue #22 adds safe watch polling and the 10-iteration gate; deterministic validation passes (237 tests). Live watch validation was not performed.

## Batch Interface/VLAN Reporting

Production defaults use `data/inventory/inventory.json`, workbooks under
`outputs/reports/interface_vlan/`, recoverable spools under
`outputs/runs/interface_vlan_report/`, and logs under `outputs/logs/`.
CLI and programmatic path overrides remain supported; legacy files are untouched.
Programmatic `run_report()` calls with `spool_root=None` (including omission)
keep recoverable spools under `<reports_dir>/runs/`; the CLI supplies the production spool default explicitly.

`scripts/device_interface_vlan_report.py` composes the shared Excel target loader,
inventory resolver, InterfaceService, and VlanService in a bounded concurrent
read-only batch. Inventory and both capabilities reuse one established session per target.
The workbook is written once at the end with Interfaces, VLAN_Database, and
Run_Errors sheets; failures are isolated by device/stage, and successful partial
observations are retained. Canonical interface joins preserve logical interfaces
and aligned service detail without deriving VLAN IDs from service identities.
Reporting uses the shared logging foundation and sanitized literal Excel text.
Console progress is flushed before each device stage and workbook generation,
with device position/total, sanitized target identity, caught failure categories,
per-device completion status, and the final report path. Scoped transport logging
also routes existing Paramiko child handlers to safe file diagnostics, preserving
concise connection failure categories and restoring logger configuration afterward.
Deterministic tests cover these contracts and a simulated 1,500-device batch.
VLAN capability profiles now expose normalized port type, untagged VLAN, outer
tagged VLANs (`ALL`/`NONE`/explicit/blank), forwarding domains, and exact service
mappings. EVC services aggregate per interface with supporting service details.
Reports use only InterfaceService identities; unmatched IOS-XR L2VPN references
cannot create normal interface rows. No validation-findings subsystem is added.
`VLAN_Database` preserves VLAN/bridge-domain/VSI object type, object ID, domain
ID, and configured name or ID fallback. Huawei VSI objects require declarations;
ASR920 context selects the EVC bridge-domain database model. Legacy detail fields
remain available to capability consumers, but reporting uses normalized fields.
Interface/VLAN export compacts consecutive numeric VLAN/domain lists and exact
identity mappings losslessly, including expanded rows from retained legacy
spools. Synthetic IOS allowed 2-4094/native 445 and offline 699-outcome/seven-failure
recovery are covered by deterministic tests; remaining oversized fields fail
with a content-free cell location and preserve atomic output/spool recovery.
Owner spool recovery and Windows validation for Issue #142 remain pending.
No live reporting validation has been performed.

## Known Limitations

- Current SSH host-key defaults are permissive and therefore do not provide MITM protection.
- Inventory refresh/export has deterministic coverage only; no live refresh/export validation was performed. Historical snapshot retention remains unimplemented; inventory stores latest state only.
- Live-device testing is integration validation and does not replace deterministic unit tests.

## Current Development Focus

The observed-context layer supports approved Excel refresh and full inventory export. Future production scheduling can reuse it without moving live interface/VLAN state into inventory.

Relevant skill: `.agents/skills/device-inventory/SKILL.md`.


## Device Configuration Backup

Production defaults use `data/inventory/inventory.json`, unique backup run folders
under `outputs/backups/configuration/`, and logs under `outputs/logs/`.
The shared logging default also uses `outputs/logs/`; explicit roots still work.
Per-run backup ignore protection and all capture/security behavior are preserved.

`scripts/device_configuration_backup.py` captures current configuration for the existing Excel/list targets on Cisco IOS, IOS-XE, IOS-XR, Huawei VRP, and Ubiquiti EdgeSwitch. It reuses shared target loading, inventory identity, bounded execution, transport, and one DeviceCLI per device. Captures go directly to a unique UTC-dated folder with sanitized `<hostname>-<platform>.txt` names and collision suffixes. Sensitive text never enters logs or result spools; custom run folders carry Git-ignore protection. Failures are isolated by target and resources close on all paths. Deterministic coverage includes command selection, content preservation, cleanup, filename collisions, secret exclusion, and batch failure isolation. Live backup validation remains operator-controlled and has not been performed.
Configuration capture regression coverage now includes configuration lines exactly matching the learned exec prompt at SSH receive boundaries. Newline-terminated matches remain body text; unterminated matches require one second of receive quiescence. A longer pause at an unterminated embedded prompt remains ambiguous; no live-device validation was performed.
Each configuration backup run includes `failed_devices.xlsx`, streamed through the executor outcome consumer with one sanitized row per failed target. Resolved hostname, management IP, hardware model (family fallback), and normalized platform are retained when available; pre-resolution failures preserve the input IP without invented identity. Fixed exception-type reasons distinguish authentication, timeout, connection/transport, unsupported capture, rejected/empty output, and write failures, with stage-level fallbacks; exception text and configuration content are excluded. Deterministic tests cover mixed outcomes, all failure stages, literal Excel cells, and secret exclusion; no live validation was performed.

Shared device access accepts optional Excel `Secret` / list `secret` credentials.
IOS/IOS-XE and EdgeSwitch user EXEC sessions perform one private enable exchange
and structurally verify the same base hostname and privileged `#` before
setup/observation, allowing supported prompt spacing and EdgeSwitch annotation
changes during enable. The bounded enable state machine tolerates fragmented
command echoes and repeated same-host user EXEC prompts before and after the
single secret submission. It rejects changed identity, malformed complete
prompts, explicit rejection, repeated password challenges, timeout, and channel
close without exposing exchange text. Deterministic regressions cover both CLI
paths and IOS/IOS-XE/EdgeSwitch; operator-controlled live retesting is pending.
Already privileged
sessions and Huawei/IOS-XR prompt paths retain their existing behavior. Missing
and failed enable authentication have fixed safe failure reasons. Credential
representations omit passwords/keys/secrets; enable echoes are discarded and
known supplied passwords/secrets are removed from backup captures. Inventory
facts and retained result spools exclude enable credentials.

Shared transport start admission is paced per execution run by
`execution.connection_start_interval` (default 1.0 seconds; 0 disables pacing),
independently of `max_concurrent_devices`. One retry is allowed only for typed
transient connection-start failures, with fresh resources after successful
cleanup and a fixed `execution.connection_retry_delay` (default 5.0 seconds),
then normal start pacing. The default active-device limit is 5. These pressure
reductions are deterministically tested; operator-controlled live retesting is
pending. Authentication, privilege, command, parser, unsupported-platform, and
unclassified SSH failures are not retried. Both OS transport architectures are
preserved. Deterministic tests cover enable flows, annotation structure,
concurrency/pacing, retry limits, cleanup and credential exclusion. These access
changes have not been live-device validated.

The bounded connection retry also recognizes Paramiko's lost-session exception
at initial remote-server-key retrieval, using the raising site and rejecting any
recorded authentication, host-key, or unclassified protocol failure. Arbitrary
SSHException messages remain non-retryable. Deterministic Windows regressions
cover recovery/exhaustion, cleanup before retry, and the retained Teleport socket
path; this resilience revision has not been live-device validated.

Shared and standalone Cisco prompt learning now validates supported prompt
structure before accepting a final receive line, rejecting MOTD/banner separators
and decorative text. Deterministic regressions cover combined and fragmented
banner/prompt receives, inventory and command synchronization, Cisco location
prefixes, Huawei views, nested EdgeSwitch annotations, enable flow, and cleanup.
The prompt correction awaits operator-controlled live retesting.


## VLAN Configuration Audit

Issue #79 adds a separate M01â€“M08 methodology projection through the existing
family AuditResolver, preserving service/child identities, local/global EVC
bindings, XR attachments, Huawei VSI and EdgeSwitch ownership. Opt-in
`--methodology-report` collects and retains review records, then exports a separate
streamed Excel workbook with evidence, findings and explicit review outcomes.
Compliance-only runs skip methodology resolution. Projection failures are stored
separately and exported as review-needed failures; compliance findings, health,
ordinary errors, device failure counts and normal reports remain unchanged.
Issue #83 preserves safe forwarding CLI verbatim, including unfamiliar syntax and
identifiers, with source filenames/one-based lines and explicit unsafe-disclosure
omission reasons. Vendor credential constructs and ambiguous free-form/opaque
payloads fail closed; the word allowlist and 256-statement cutoff are removed.
Methodology export adds readable Evidence Details and keyed continuation references
for oversized main-sheet fields, streamed JSON fragments and numbered continuation
sheets at Excel's row limit. Shared spool recovery and the approved main columns
remain unchanged. Memory is bounded by the largest target outcome, not the run;
old capture omissions require re-observation. Classification/policy semantics
remain unchanged; validation is deterministic and synthetic only. XR routed/BVI and pseudowire attachments
are separate service context, not M04 Ethernet L2 transport; empty parent
interfaces and out-of-scope switchport controls no longer create noisy review rows.
These revisions have synthetic regression coverage only. Configuration-facts
digests cover the sanitized projection, not raw backups or live freshness.
The Issue #79 revision observes service-scoped Cisco tag rewrites (POP 1/2,
strict PUSH/TRANSLATE forms) as separate methodology attributes with sanitized
source evidence. Model/release support remains unassessed. Malformed syntax,
unsupported scope and conflicting profiles require review. ME3600X empty trunks
(`allowed vlan none`) can coexist with distinct M03 EVC records without a false
mixed-construct finding. Operator-provided ME3600X/NCS540 excerpts are covered
by deterministic tests; existing missing-parent findings remain visible.
Revision validation: 285 audit/compliance/report regressions and 134 focused
methodology/observation/validation tests passed; all 1,723 captured pre/post
compliance result hashes matched (compared as a multiset for concurrent runs).
The NE05E revision adds M08 `vlan_tagged_subinterface` for explicit
`vlan-type dot1q` on logical subinterfaces, preserving exact identities, tags and
source evidence in the existing methodology workbook mapping. Encapsulation
alone leaves role `not_determined` without requiring review; genuine conflicts
and missing parents remain reviewable. No L2/VSI/database membership or template
eligibility is inferred. Case/whitespace variants are review-only facts excluded
from compliance; existing canonical invalid-tag errors remain unchanged.
Operator-supplied NE05E examples have deterministic offline coverage only.
Compliance outputs remain unchanged: 180 representative pre/post result hashes
matched and 281 existing audit/compliance/report regressions passed. Focused
methodology/workbook and VLAN observation tests pass. Validation is synthetic;
no real backup corpus or live devices were used. Review import, template
selection, apply and Change Plan v1 changes remain out of scope.

Issue #81 adds independent standards classification, severity, normalized finding
codes and default `not_reviewed` engineer decisions to the methodology workbook.
The seven approved patterns distinguish informational exclusion/database cases,
known non-standard switchport styles/residual settings, standard ME3600X EVC
prerequisites, confirmed member/LAG differences and interfaces without L2 service.
Unknown/incomplete syntax, EVC overlap and ambiguous relationships remain reviewable.
Member/LAG comparisons retain one-sided configured fields as unknown with
`LAG_MEMBER_CONFIGURATION_UNRESOLVED` and evidence-backed explanations; omitted
counterparts do not imply equal/default values or partial inheritance. Entirely
unconfigured members retain supported aggregate inheritance. Confirmed explicit
differences still take precedence as wrong configuration.
Only Interface, Service Instance and Evidence Source leave the main sheet; full
identity/evidence remains in Details. Safe CLI retains original indentation and
source lines; disclosure remains fail-closed. Deterministic synthetic fixtures
include complete compliance-output hashes captured from the pre-Issue #81 baseline.
Audit health, policy and pass/fail remain unchanged; no live-device validation or
durable engineer approval is claimed.

Issue #85 refines methodology-only pseudowire context, validated XR routed BVI
and untagged attachments, and local/global EVC bindings including split-horizon
modifiers. Real interface identity, exact evidence and unresolved references
remain visible; equivalent local/global bindings are standard. Compliance
semantics and Pattern 9 are unchanged, with frozen baseline-equivalence tests.
PR #86 revision scopes EVC service-specific methodology findings to their own
service-instance IDs, so valid ASR920 bindings remain standard beside unresolved
siblings. Interface-wide findings and parent-level compliance remain unchanged.
Synthetic validation is implemented; operator live report validation remains
required before completion/merge approval. See
`docs/operations/methodology-patterns-8-12.md` for the command and expected outcomes.

Issue #65 now implements the saved-configuration audit boundary:
VlanService/vendor observation -> preserved configuration facts/evidence ->
family-specific AuditResolver -> common external policy -> JSON spool/Excel.

Resolvers cover ME3600X, ASR920, Catalyst 3750X/3850, Huawei VRP (NE05/NE05E),
NCS540 and EdgeSwitch. They validate service bindings, database membership,
parent/child consolidation, canonical identity matching and aggregate ownership.
EdgeSwitch audit resolves member `addport 3/N` and `addport lag N` references
to configured `interface lag N` ownership, with inheritance/conflict coverage;
unsupported or absent aggregate references remain explicit review findings.
NCS540 numeric VLANs require valid BD -> existing l2transport subinterface ->
explicit dot1q mappings; the earlier named-service baseline is removed.

Schema-v2 JSON policy requires database VLANs 445,545,2400-2444,2449,4001.
Trunk/EVC/Hybrid interfaces matching 445 AND 545 AND (2449 OR 4001) require
2400-2444,2449,4001. Access/nonmatching interfaces are not applicable.
Configuration findings remain independent of compliance, and uncertain families
or unavailable configuration evidence explicitly return unable to assess.

The existing read-only CLI, shared per-device execution/session/capabilities,
centralized spool and report recovery remain in use. Structured findings retain
source labels/filenames, one-based line evidence, configured/observed identities,
shutdown, mappings, exact missing VLANs and configuration ownership. Sensitive
and unrelated configuration statements are excluded from the observation
projection. No remediation generation/apply is implemented.

Deterministic coverage includes every documented family, policy validation,
relationship failures, secret exclusion, failed-device isolation and 1,500-device
spool/report recovery. Operator ASR920 live validation exposed inline bridge-domain
modifiers; the saved-configuration parser now accepts `split-horizon group <N>`
while preserving the original excerpt/line and rejecting unsupported trailing text.
Deterministic regressions cover the full required range and ME3600X database
separation. Interface results retain observed admin/oper state separately from
configured shutdown, with dedicated Excel columns and visible exact missing VLANs.
This revision awaits operator-controlled live retesting.
Authoritative semantics: `.agents/skills/vlan-configuration-audit/SKILL.md`.

The Issue #65 reporting revision excludes InterfaceService-only identities from
audit rows/children and marks configured interfaces without L2 service configuration
not applicable. EdgeSwitch valid audit membership includes participating tagged
VLANs plus a participating non-tagged PVID; participation-only VLANs remain evidence.
Excel separates Interface Results, Database Results, Run Errors and Details, with
readable preserved configuration excerpts/source/compact line references and exact
Missing VLANs. Structured evidence remains available in JSON and Details. These
revision behaviors are deterministically tested; no new live validation was run.

The live-validation revision infers Access from C3750X/C3850/ME3600X access-VLAN
configuration without explicit mode unless switching intent conflicts. EdgeSwitch
physical/LAG rows with empty valid audit membership are not applicable; unresolved
aggregate references still require review. Configured BDI/pseudowire/service-only
rows remain retained. Database evidence now contains contributing declarations and
validated family-specific relationships, preserving source indentation and line
references through spool recovery and Excel export. Detailed structured mappings
remain available. Deterministic coverage includes all supported families; this
revision has not been live-device tested.

C3750X/C3850/ME3600X conventional trunk audit replays allowed-VLAN replace,
add, remove, none, all and except operations in source order. All retains family
validation; except uses the validated device database minus exclusions. Existing
family database intersection, access inference and aggregate ownership remain.
Ordered excerpts survive JSON spool/Excel recovery; malformed operations require
review. This revision has deterministic coverage; live retesting is pending.

Issue #72 separates normalized `configuration_health` from VLAN compliance
`status`, with an appended Excel column and conservative legacy-spool fallback.
C3750X/ME3600X explicit switchport mode preserves trustworthy compliance facts
despite conflicting access/trunk statements, while retaining wrong-configuration
findings. Unresolved mode remains unable to assess. NE05E valid VSI-bound dot1q
children consolidate into existing parents without requiring parent trunk mode;
missing parents, explicit access conflicts and invalid VSI bindings remain
visible. Synthetic regressions include 13 Cisco conflicts, five NE05E parents,
one unresolved Cisco case and invalid relationships. No live testing was run.

## Cisco CLI width synchronization (Issue #114)

Cisco temporary shells and borrowed shared CLI adapter/configuration-capture
paths require session-only `terminal width 511`; shared acceptance is cached.
Rejection blocks the shell and timeout invalidates synchronization. Strict echo
checks and normalized identities remain intact. Synthetic tests cover wrapped
and stale echoes, setup failures and full-interface ME3600X/ASR920 EVC lookups.
Owner manual width tests succeeded on ME3600X/ASR920; automatic setup still needs
live validation. NCS540/C3750X/C3850 width acceptance is pending. IOS-XR EXEC
syntax is documented independently; no NCS540 live claim is made. See
[verification instructions](user_manual/live-validation.md#cisco-terminal-width-issue-114).

Issue #117 review corrections support real EdgeSwitch Interface VLAN headers with
strict table completeness, require matching standalone switchport target headers,
verify the approved C3750X dot1q change while preserving unrelated settings, and
recognize supplied command-not-found/range rejections. C3850 omits the selector.
Save remains prompt-based with errors separate. Optional capability correlation
retains run/row/digest, target/command, elapsed timing and safe failure diagnostics;
see the [API reference](operations/configuration-execution-api.md). Owner lab validation remains pending.


Issue #117 cumulative owner revision (2026-10-17): execution now uses a concise reusable
operator summary without weakening digest-bound confirmation; protected backups default
to the execution run's `backups/` with relative references (explicit external override
remains supported). Reports group original template rows with fresh pre-row evidence,
actual attempted commands, readable post evidence and independent apply/verification/save
outcomes. Older missing pre-row evidence is Not captured. Short Catalyst access responses
permit only reliable explicit exact-port configuration fallback, with source/warnings;
pure parser unknowns and contradictory operational facts are preserved. See the
[execution manual](user_manual/configuration-execution.md). No completed configuration was replayed; owner lab validation
and merge remain pending.

Issue #117 iteration 3: execution summaries group findings by source sheet/row ranges
without nested evidence; template reports expose individual input columns, compact
checks and linked complete detail, and preserve manifest run identity after relocation.
Presentation alone suppresses tagged/membership overlap warnings. Optional structured
progress drives immediate flushed CLI stages and five-second waiting updates without
accessing channels or replaying writes; Python API calls remain quiet by default.
Fallback field/source and journal warning messages survive shared safe log formatting.
Owner live/lab validation and protected skill reconciliation remain pending.

Issue #117 recovery validation on 2026-10-17: executor regressions pass (133);
Windows controller gate currently reports 2,577 passed and two inventory/reporting
failures under its deeply nested temporary root. Extended-length spelling did not
resolve relative workbook creation. See the monthly devlog/revision handoff for
separate short-temp full-suite evidence; do not treat it as a passed controller gate.
Owner lab validation and protected-skill reconciliation remain pending.

Separate shorter-temp full suite: 2,579 passed in 184.13s (Windows); both failing
controller-path tests pass there. The nested-temp controller gate remains failed.


Issue #119 presentation follow-up: confirmation renders totals and numbered devices
with selected-row counts, a warning/blocker detail pointer and one execution policy
line. CLI progress retains stage/source/command index and actionable outcomes while
omitting commands, counters and durations; structured subscribers retain full timing
and correlation. One final actual device/row outcome summary includes execution elapsed
time before report generation. Execution/verification behavior and replay gates remain
unchanged. Owner C3750X/EdgeSwitch lab validation following merged PR #118 is reported;
C3850 live validation remains outstanding. Historical run/gate results above are retained.
No live device testing was performed by Codex for this follow-up.

## Interactive Operations Console (Issue #123)

`python -m orbitflow.menu` provides configuration template/planning/confirmed execution, stored execution review/recovery, inventory, interface/VLAN reporting, compliance/methodology/recovery, backup and environment settings. Strict non-secret profile schema, atomic setup, Teleport routing/expiry checks, exclusive daily template naming and nonpersistent per-run concurrency 1-5 are implemented. Shared services and executor safety are unchanged. Legacy root settings remain a fallback behind shared profile pacing for default callers. Windows full-suite validation passed 2,629 tests, with 34 focused console tests also passing; Linux and owner-operated live validation remain pending. See the [manual](user_manual/interactive-operations-console.md).

Issue #123 / PR #124 revision implements pacing re-prompts with atomic cancellation, fixed actionable sanitized console failures, all/subset loaded device row selection with canonical IP mapping and selected-row/address confirmation through existing services, bounded invalid-report notices with continued offline listing, and digest derivation from validated immutable JSON for unchanged workbook verification. Inventory refresh adds optional validated `target_positions`; direct CLI defaults and executor safety remain unchanged. Real planner/review and report-spool adapters are covered deterministically; Linux and owner live validation remain pending. Revision test results are recorded in the October devlog.

Issue #123 / PR #124 owner revision: session validation accepts `profile_url` and legacy `proxy_url`, requiring both to match when present; expiry/cluster checks remain strict. Planning offers newest-first numbered `.xlsx` selection with explicit-path fallback. Device selection displays counts for all-selection and at most ten safe row/address identities for explicit subsets. Executor safety is unchanged. Deterministic Windows validation is recorded in the October devlog; Linux and owner live validation remain pending.

PR #124 console UX revision adds menu separators, fixed-label persisted observation progress, elapsed phase notices, offline preparation/report-export indicators and newest-first valid immutable-plan selection. Console-only summary shortening preserves direct CLI text and all executor/workbook protections. Operational evidence remains visible where required; no preflight optimization or device timing measurement was performed. Windows revision test results are recorded in the October devlog; Linux and additional owner UX validation remain pending.

PR #124 final progress presentation revision uses one flushed TTY line, durable per-device counts for planning observation and confirmed execution, and indeterminate activity for other long console phases and read-only services without structured durable-outcome callbacks. Non-TTY output is bounded to five-second updates plus phase boundaries; errors/cancellation terminate the line. No executor or direct CLI changes. Regression evidence is in the October devlog; Linux and owner live validation remain pending.

PR #124 owner final revision restores confirmed-execution per-target/row stage and wait visibility using existing events, with allowlisted output and measured device counts. Read-only bars remain compact; execution semantics and direct APIs are unchanged. Windows focused validation passed 314 tests; Linux and owner live validation remain pending.


## Execution profiling and ordered template stages (Issue #125)

All eleven executable C3750X/C3850/EdgeSwitch predefined templates use correlated
monotonic stage/command timings in shared bounded configuration logs. Ordered
contiguous stages share fresh full baseline/pre/post observations across independent
targets. Source/resolved target overlaps, dependencies and template changes split
stages; noncontiguous templates never regroup. VLAN Database postchecks use shared
fresh lookups. Fresh identity/privilege, protected backup, immutable commands/projected
result checks, full relevant preservation/operational verification, journal/recovery,
confirmation/replay and independent save remain.

A bounded device-owned baseline compares fresh relevant target facts between stages
and advances only verified changes. No stale-only cache or scoped vendor parser is
used. Verification establishes stage final state on independent targets, not
unobserved intermediate effects or continuous whole-device external drift detection.
Unrelated out-of-scope changes are not globally compared. Standalone collectors,
public signatures, report columns, concurrency and unsupported-family/EVC/Manual CLI
execution restrictions remain unchanged.

Synthetic real-collector schedules for ten independent rows reduce full config reads
22 to 3 for interface templates, 12 to 2 for VLAN Database including baseline/backup;
semantic all-template execution and safety regressions are deterministic fixtures.
Detailed count/timing methodology and Windows/Linux commands are in the
[manual](user_manual/configuration-execution.md#ordered-template-stages-owner-approved-revision).
Owner's 2026-10-18 C3750X/EdgeSwitch timings describe the prior revision, not new live
gains. Owner stage-execution validation on all three families and Linux remain pending.

## MAC Address Lookup (Issue #130)

Independent MAC and XR bridge-domain services/pure parsers, observed-parent resolution, normalized forwarding composition, two-action console integration and direct CLI/API report recovery are implemented. Shared scheduling, session reuse, bounded normalized spool and literal-safe seven-column Excel output are reused. Focused offline sample/console validation passes; full-suite result is recorded in the October devlog. No live-device validation was performed; Issue #132 Linux offline results are recorded below. Huawei/EdgeSwitch invocation remains unconfirmed; missing/ambiguous service mappings remain explicit, never VLAN matches. Existing service-profile VLAN-1 omissions and Excel limits remain. Atlas completed MAC/bridge-domain skill routing on this PR branch; see [handoff](operations/mac-lookup-atlas-skill-handoff.md). Owner live validation and merge remain pending.

Issue #130 review revision: XR MAC VLAN proofs now require exact operational and
configured group/domain agreement; bridge summaries preserve reported total/up
counts and reject malformed attachment sections. Known empty VFI/Access VFI
sections are accepted; nonempty VFI content remains explicitly unsupported. Search
output correlates each match with its own identity and physical/type details. Deterministic validation
is recorded in the October devlog; owner live validation remains pending.


Issue #132: MAC enrichment now reuses family-validated port classifications for
ME3600X/ASR920/EdgeSwitch, retains explicit ME3600X/ASR920 numeric VLAN scope,
resolves EdgeSwitch MAC 3/N destinations to lag N only with one exact independent
observed/configured aggregate identity (absent/ambiguous stays unresolved), and
keeps management 5/1 nonphysical. Explicit EdgeSwitch trunk intent preserves empty
membership and cannot create a compliance trigger. XR MAC-only untagged fallback
requires exact operational/configured BG/BD agreement and one distinct explicit
peer dot1q VLAN; shared XR observations are unchanged. Offline regression evidence
is recorded in the October devlog: review revision focused validation passed 480
tests; latest full suite is not clean (2,958 passed, 25 controller temp-guard failures).
A clean external-temp rerun is blocked by sandbox filesystem permissions; operator
live and Windows validation are pending.

Issue #132 / PR #133 owner description revision supersedes the previous six-column
MAC main-sheet promise: the existing six columns remain in order with Interface
Description appended seventh. Exact resolved parent/aggregate owner descriptions
come from independent interface/VLAN observations; conflicts and unverified or
nonphysical destinations stay blank. Supporting sheets and other reports are
unchanged. Offline recovery supports old six-value rows with a blank description.
Deterministic description/export regressions pass; operator live and Windows
validation remain pending.


Issue #132 / PR #133 review corrections: the policy-free shared classification
projection now classifies configured XR ACs by explicit encapsulation and one exact
BG/BD binding: untagged is access, dot1q is trunk. Existing parents combine child
roles (access/trunk/hybrid); invalid or conflicting child evidence is review/Unknown,
and routed interfaces retain routed classification. Exact AC type takes precedence
over the parent type for a MAC on that AC. This does not change numeric compliance
membership, shared VLAN observation or BridgeDomainService. No peer VLAN association
is used to claim tagged ingress.

IOS/IOS-XE parsing accepts the exact repeated `Nile Mac Address Entries` banner
and repeated column headers while preserving each row's VLAN/BD scope; other invalid
rows still fail. The main sheet's existing `Physical Interface name` column shows
the resolved physical/logical owner when proven, otherwise the normalized original
attachment (including remote tuples, Drop and unresolved LAG/IP-like destinations).
This fallback is display only: Details physical identity stays blank when unresolved,
raw attachment is retained, and descriptions still require exact owner evidence.
Seven-column output and historical six-column spool recovery remain supported.

Owner Linux worktree verification for Issue #139/PR #140 (head `481e712c` before Atlas documentation-only additions) passed 591 focused tests in 14.56s and the complete deterministic suite of 3,087 tests in 117.23s (2026-10-20 Australia/Melbourne). This resolves the earlier Codex sandbox-only temp-root test failures for the owner Linux environment; Windows tests and new owner/live-device validation for Issue #139 remain unverified. The reviewed PR is not itself evidence of live device behavior.
