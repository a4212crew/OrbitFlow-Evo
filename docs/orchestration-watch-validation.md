# Orchestration watch-mode validation

This file exists only to validate watch-mode task pickup and publication for
Issue #24. It introduces no runtime, network, controller, architecture, or
production behavior changes.

The controller/operator should confirm that:

1. The running `--watch` controller picks up the `codex-task` without restarting.
2. The task reaches `codex-review` with a PR and a passing full deterministic
   pytest test gate.
3. Watch mode remains running and returns to idle polling after success.
4. No auto-merge occurs.

These are validation criteria, not a record that the live lifecycle has passed.
Codex implements and tests this documentation change; publication and task-state
transitions remain controller responsibilities. No live-device testing is needed.
