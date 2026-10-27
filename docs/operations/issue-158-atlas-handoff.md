# Atlas protected-skill handoff — Issue #158

In `.agents/skills/configuration-management/SKILL.md`, under “Manual Configuration — Issue #156”, replace the bullets beginning “Open a fresh shell per row” and “Automatic save is successful-row-only” with:

- Group canonical IP rows in original workbook order, including noncontiguous rows. Own one DeviceSession and one exact live DeviceCLI shell per device group; identify, establish privilege/paging and take a protected backup once before writes. Never close/reopen the shell between rows.
- Start each row from confirmed privileged EXEC, enter supported global config, send literal bounded prompt-free blocks, then explicitly synchronize to confirmed EXEC after every block. Journal Commands completed / awaiting device save immediately. Save automatically exactly once after all device rows succeed and return to EXEC; only confirmed save yields Completed/Saved. Any invalid row, setup/write/boundary/recording failure stops same-device writes and prevents new automatic save. Preserve Unknown after save transmission, prior block evidence and confirmed save despite cleanup failure; expose unsafe cleanup. Explicit engineer persistence is independent. Never replay/reconnect/resume after writes. Predefined partial-save policy is unchanged.

Earlier fresh-row owner acceptance is historical; grouped-session hardware validation remains owner-operated and pending. No transport retry default changes.

Apply the same exact two replacement bullets under “Manual Configuration — Issue #156”
in `.agents/skills/interactive-operations-console/SKILL.md`, which repeats that contract.
No `.agents` files were modified by Codex.

Controller-only proposed Issue/PR title: **Manual configuration: grouped live device shell, EXEC row boundaries and final save**.
Final PR description should describe one owned connection/shell per canonical IP,
ordered row blocks with verified EXEC boundaries, durable partial command evidence,
one final automatic save and historical recovery compatibility. Include final worker
test evidence, sandbox limitations, pending Windows/grouped owner lab checks and
this protected-skill handoff. Codex does not change the Issue or PR.

In `.agents/skills/device-execution/SKILL.md`, supersede any prior Issue #158
per-row lifecycle handoff with this paragraph after the Core Contract diagram:

> Manual Configuration (Issue #158) retains one worker per canonical IP and owns
> one DeviceContext, DeviceSession/transport chain and one exact live CLI shell
> for the whole ordered row group. Prepare identity/privilege/paging and protected
> backup once, synchronize global-config/EXEC boundaries per row and save once
> after the last successful EXEC return. Never close/reopen shells between rows.
> Stop that device and prevent new automatic save on any invalid row, setup,
> command, boundary or mandatory-recording failure; retain prior block evidence.
> Cleanup attempts every owned resource once at device end. Other workflows
> retain their existing lifecycle and save policy.


Atlas applied the superseding grouped-session corrections to all three skills on
this PR before owner-authorized merge. The instructions above remain as historical
handoff provenance. No executable changes were made by Atlas.
