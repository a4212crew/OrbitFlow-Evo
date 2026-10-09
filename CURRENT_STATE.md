# CURRENT_STATE.md — OrbitFlow-Evo Current State

Use this file as the concise source of truth for what is implemented and validated today.


Keep this document short. Historical implementation detail belongs in `docs/devlog/YYYY-MM.md`.

## Offline Configuration Plans (Phases 1–2)

`orbitflow.configuration` and `scripts/configuration_plan.py` provide immutable
versioned Change Plans, canonical SHA-256 content digests, inventory snapshot
resolution, strict offline validation/preview and durable digest-bound
approve/reject/expire gates. Manual, spreadsheet, template and compliance
producers share a normalized JSON request; source-specific importers/generators
remain future work. The initial renderer supports VLAN creation on C3750X IOS
and C3850 IOS-XE profiles, including no-op and conflicting-state checks.
SQLite approval history is signed by a separate local key; operator-controlled
authority storage is required and actor labels are not authentication.
Deterministic tests cover the lifecycle, expiry, mutations, tampering, secret
rejection and socket-blocked CLI operation. No apply/live verification or device
changes are implemented. See `docs/architecture/configuration/offline-plans.md`.
The configuration-management skill is staged alongside that document pending
controller installation into the session-protected `.agents/skills/` directory.

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
- EdgeSwitch hostname extraction structurally accepts parenthesized exec prompts ending in `#` or `>`, including optional nested annotations of arbitrary text, normalizes to the base hostname, rejects malformed parentheses, and retains simple `hostname#` / `hostname>` support (deterministically tested);
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
- `src/orbitflow/transport/` — shared and OS-specific transport;
- `src/orbitflow/vendors/cisco/` — Cisco IOS/IOS-XE CLI behaviour;
- `src/orbitflow/vendors/huawei/` and `src/orbitflow/vendors/ubiquiti/` — vendor interface collection/parsing;
- `src/orbitflow/capabilities/` and `src/orbitflow/models.py` — reusable interface/VLAN capabilities and normalized records;
- `src/orbitflow/inventory/` — identification, reconciliation, and latest JSON snapshot storage;
- `scripts/live_validate_interfaces.py` — single-device interface integration validation;
- `scripts/live_validate_vlans.py` — single-device VLAN integration validation harness;
- `tests/` — deterministic mocked/unit tests;
- `.agents/skills/` — task/vendor-specific implementation guidance.

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

## Codex Orchestration — OrbitFlow-Evo

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

Issue #79 adds a separate M01–M07 methodology projection through the existing
family AuditResolver, preserving service/child identities, local/global EVC
bindings, XR attachments, Huawei VSI and EdgeSwitch ownership. Opt-in
`--methodology-report` collects and retains review records, then exports a separate
streamed Excel workbook with evidence, findings and explicit review outcomes.
Compliance-only runs skip methodology resolution. Projection failures are stored
separately and exported as review-needed failures; compliance findings, health,
ordinary errors, device failure counts and normal reports remain unchanged.
Unknown forwarding syntax retains bounded, sanitized statement evidence and source
context in the methodology workbook/Details. A disclosure vocabulary redacts
arbitrary operands; unsafe/oversized statements and evidence beyond the capture
limit have explicit omission markers. XR routed/BVI and pseudowire attachments
are separate service context, not M04 Ethernet L2 transport; empty parent
interfaces and out-of-scope switchport controls no longer create noisy review rows.
These revisions have synthetic regression coverage only. Configuration-facts
digests cover the sanitized projection, not raw backups or live freshness.
Compliance outputs remain unchanged: 180 representative pre/post result hashes
matched and 281 existing audit/compliance/report regressions passed. Focused
methodology/workbook and VLAN observation tests pass. Validation is synthetic;
no real backup corpus or live devices were used. Review import, template
selection, apply and Change Plan v1 changes remain out of scope.

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
