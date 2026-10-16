# Issue #114 / PR #115 controller handoff

Status: incomplete. The current sandbox rejects writes to `.agents`; the skill
update below is **not applied**. The implementation engineer is prohibited from
editing PR descriptions. The authorized controller/owner must apply the skill
patch and replace the incorrect full-suite-pass claim in PR #115. Do not merge.

## Copy-ready PR description

Issue #114 / PR #115 revision

Cisco session behavior is unchanged in this revision. The proposed Cisco skill update documents session-only width 511, shared-shell caching, temporary shells, explicit rejection/timeout failure, strict synchronization, and pending owner validation. Applying that update remains blocked here because `.agents` is read-only; controller handoff patch: the skill patch below (apply_patch format).

Validation:
- Linux targeted tests: **151 passed**.
- Prior full-suite result: **2399 passed, 25 failed**, not a full-suite pass. Controller temporary-directory Git-marker guards rejected the sandbox temp roots.
- Revision full-suite result: **2421 passed, 25 failed** in 78.01s. All 25 failures are controller tests affected by the external-temp Git-marker guard. Full-suite green remains unverified. This is prior-run evidence recorded in `docs/devlog/2026-10.md`, not a new full-suite run.
- No safety guards weakened. No native Windows or new live-device tests performed.

Copy-ready Linux commands (repository root):
```bash
python -m pytest -q tests/test_cisco_terminal_width.py tests/test_cisco_ios_cli.py tests/test_shared_cli.py tests/test_cli_lifecycle.py
python -m pytest -q
```

Copy-ready Windows PowerShell commands (repository root):
```powershell
python -m pytest -q tests/test_cisco_terminal_width.py tests/test_cisco_ios_cli.py tests/test_shared_cli.py tests/test_cli_lifecycle.py
python -m pytest -q
```

Run the full suite in an environment whose OS temporary directory is writable and outside Git ancestry; preserve controller safety guards. The current sandbox has `/tmp/.git`, and `/var/tmp` is outside its writable roots.

Owner read-only verification remains required on ME3600X, ASR920, C3750X, C3850 and NCS540 using `docs/user_manual/live-validation.md#cisco-terminal-width-issue-114`. Manual ME3600X/ASR920 width success does not validate automatic setup. NCS540/C3750X/C3850 width acceptance is still pending; original wrapped echo bytes were not captured.

Documentation: appended `docs/devlog/2026-10.md`; Cisco skill patch pending controller application. Existing operator/API/current-state claims remain unchanged. No unrelated PR #113 edits or Git/GitHub lifecycle actions performed.

## Skill patch for the authorized controller

Apply in the Issue #114 worktree using an environment authorized to write
`.agents/skills/cisco-network-cli/SKILL.md`, then review the resulting Git diff.
This proposal is not evidence that the skill update has landed.

```diff
*** Begin Patch
*** Update File: .agents/skills/cisco-network-cli/SKILL.md
@@
-IOS/IOS-XE baseline paging disable:
+IOS/IOS-XE/IOS-XR session setup uses EXEC commands:
@@
 terminal length 0
+terminal width 511
 ```
 
-Prompt detection should remain dynamic rather than hostname-specific.
+These settings affect only the interactive session; they do not apply or save
+device configuration. Temporary `CiscoIOSCLI` and `CiscoXRCLI` shells require
+both commands during construction. Borrowed `DeviceCLI` adapter and
+configuration-capture paths request width through `configure(...,
+setup_commands=("terminal width 511",))`; accepted width setup is cached per
+shell across repeated adapter configuration and service lookups. Short inventory
+identity probes retain their existing initialization; the selected Cisco adapter
+requires width before subsequent capability operations.
+
+Width rejection raises `InteractiveCLIError` and blocks shared-shell reuse;
+timeout raises `InteractiveCLITimeout` and invalidates synchronization. Temporary
+shell setup rejection/timeout raises `CiscoIOSCLIError`/`CiscoIOSCLITimeout` and
+closes the owned channel. Parent transport ownership is preserved. Diagnostics
+identify the failed setup command without copying raw device output. Workflows
+may wrap the failure or report unavailable evidence; never continue commands on
+the failed shell or silently ignore rejection. Preserve canonical identities.
+
+Keep strict command-echo/prompt synchronization and dynamic prompt detection.
+Do not relax echo checks or invent wrapped-echo parsing. Synthetic wrapped-echo
+fixtures demonstrate a possible timeout mechanism; original device echo bytes
+were not captured, so wrapping remains a root-cause hypothesis.
+
+The independently checked IOS-XR EXEC reference documents session-only
+`terminal width` with range 0–512, supporting 511 syntactically. This is not
+NCS540 release-specific acceptance evidence. Owner manual read-only width tests
+succeeded on ME3600X (IOS) and ASR920 (IOS-XE); automatic setup still requires
+owner live validation on all five requested families. NCS540 (IOS-XR), C3750X
+(IOS), and C3850 (IOS-XE) width acceptance remains pending. See the
+[operator verification and Linux/Windows test commands](../../../docs/user_manual/live-validation.md#cisco-terminal-width-issue-114).
*** End Patch
```
