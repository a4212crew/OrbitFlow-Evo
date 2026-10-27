# Issue #158 protected skill Markdown handoff

The `.agents/` skills are read-only in the implementation environment. Atlas must
apply the following exact Markdown changes; Codex has not modified those files.

In `.agents/skills/configuration-management/SKILL.md` and
`.agents/skills/interactive-operations-console/SKILL.md`, replace:

> Open a fresh shell per row, reuse shared transport/identity/enable/paging/backup,

with:

> Issue #158 supersedes the historical per-IP connection reuse policy. Each valid
> executable Manual Configuration row owns a fresh DeviceSession through existing
> connect_device and a fresh shell, identity, enable/paging and protected backup.
> Close the shell and every dependent transport resource before the next row.
> Keep one worker per IP, workbook order, shared connection pacing, one receive-only
> device capture and success-only automatic save; never retry/replay writes.

The following existing line, “enter global configuration mode”, continues the
replacement paragraph. In `.agents/skills/device-execution/SKILL.md`, append after
the Core Contract diagram:

> Manual Configuration (Issue #158) retains one worker per IP but owns a fresh
> DeviceContext, DeviceSession/transport chain and CLI lifecycle for each valid
> executable row, closing all row resources before the next row. Other workflows
> retain their existing lifecycle.

This is the approved correction; source/tests establish implementation and
deterministic validation. Live hardware compatibility remains owner-validated.
