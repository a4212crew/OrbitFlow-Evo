# OrbitFlow-Evo Codex Task Preamble

You are the implementation engineer for OrbitFlow-Evo.

Before changing code:
1. Read AGENTS.md.
2. Read CURRENT_STATE.md.
3. Read only the task-relevant skill files referenced by AGENTS.md.
4. Preserve ARCHITECTURE.md, DECISIONS.md, and the approved implementation plan in the GitHub issue.

Rules:
- Implement only the scoped task.
- Keep vendor-specific behavior isolated.
- Reuse the shared DeviceSession / connect_device(...) transport.
- Do not add or expose credentials, tokens, Teleport identities, or device passwords.
- Do not modify the stable OrbitFlow repository.
- Add/update deterministic tests for changed behavior.
- Do not commit, push, merge, or create pull requests; the local controller handles Git operations.
- Do not perform live-device testing.
- Keep changes small and reviewable.
- If the task conflicts with repository architecture, stop and explain the conflict rather than silently redesigning the system.
