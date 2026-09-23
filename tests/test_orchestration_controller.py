from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys

import pytest


_CONTROLLER_PATH = (
    Path(__file__).parents[1] / "scripts" / "orchestration" / "controller.py"
)
_SPEC = spec_from_file_location("orbitflow_orchestration_controller", _CONTROLLER_PATH)
assert _SPEC is not None and _SPEC.loader is not None
controller = module_from_spec(_SPEC)
sys.modules[_SPEC.name] = controller
_SPEC.loader.exec_module(controller)


def _task(mode="initial"):
    return controller.Task(
        mode=mode,
        issue={
            "number": 42,
            "title": "Portable orchestration",
            "body": "Implement the approved task.",
            "url": "https://example.test/issues/42",
        },
    )


def test_iteration_state_uses_highest_marker_and_latest_owner_review():
    comments = [
        {
            "author": {"login": "a4212crew"},
            "body": "<!-- orbitflow-codex-iteration:2 -->\nready",
        },
        {
            "author": {"login": "someone-else"},
            "body": "<!-- atlas-review -->\nignore this reviewer",
        },
        {
            "author": {"login": "a4212crew"},
            "body": "<!-- atlas-review -->\nfix portable paths",
        },
        {
            "author": {"login": "a4212crew"},
            "body": "<!-- orbitflow-codex-iteration:7 -->\nready",
        },
    ]

    state = controller.parse_iteration_state(comments, "a4212crew")

    assert state.iteration == 7
    assert state.atlas_review == "<!-- atlas-review -->\nfix portable paths"


def test_initial_iteration_rejects_existing_history():
    state = controller.IterationState(1, None)

    with pytest.raises(RuntimeError, match="already has Codex iteration history"):
        controller.determine_iteration(_task("initial"), state)


def test_revision_requires_owner_atlas_review():
    state = controller.IterationState(3, None)

    with pytest.raises(RuntimeError, match="no owner-authored atlas-review"):
        controller.determine_iteration(_task("revision"), state)


def test_revision_increments_iteration():
    state = controller.IterationState(3, "<!-- atlas-review -->\nfix it")

    assert controller.determine_iteration(_task("revision"), state) == 4


def test_prompt_contains_task_iteration_and_revision_feedback():
    task = _task("revision")
    prompt = controller.build_prompt(
        "PREAMBLE",
        task,
        4,
        "<!-- atlas-review -->\nfix only this",
    )

    assert "PREAMBLE" in prompt
    assert "Issue #42: Portable orchestration" in prompt
    assert "iteration 4 of a maximum 15" in prompt
    assert "<!-- atlas-review -->\nfix only this" in prompt
    assert "preserve unrelated working behavior" in prompt


def test_planned_worktree_is_sibling_of_repository(tmp_path):
    repo_root = tmp_path / "OrbitFlow-Evo"

    planned = controller.planned_worktree(42, repo_root)

    assert planned.branch == "codex/issue-42"
    assert planned.path == tmp_path / "OrbitFlow-Evo-worktrees" / "issue-42"


def test_dry_run_does_not_create_worktree_or_mutate_github(tmp_path, monkeypatch, capsys):
    repo_root = tmp_path / "OrbitFlow-Evo"
    preamble = repo_root / "scripts" / "orchestration"
    preamble.mkdir(parents=True)
    (preamble / "task-preamble.md").write_text("PREAMBLE", encoding="utf-8")

    monkeypatch.setattr(controller, "repository_root", lambda: repo_root)
    monkeypatch.setattr(controller, "verify_repository", lambda *_args: None)
    monkeypatch.setattr(
        controller,
        "get_iteration_state",
        lambda *_args: controller.IterationState(0, None),
    )

    def forbidden(*_args, **_kwargs):
        raise AssertionError("dry-run must not mutate repository or GitHub state")

    monkeypatch.setattr(controller, "ensure_worktree", forbidden)
    monkeypatch.setattr(controller, "set_issue_labels", forbidden)
    monkeypatch.setattr(controller, "add_issue_comment", forbidden)

    controller.process_task("a4212crew/OrbitFlow-Evo", _task(), dry_run=True)

    rendered = capsys.readouterr().out
    assert "DRY RUN" in rendered
    assert "No branch, worktree, labels, comments, commits, pushes, or PRs were changed." in rendered


def test_run_tests_failure_is_blocking(monkeypatch, tmp_path):
    class Completed:
        returncode = 1
        stdout = "one failed\n"
        stderr = ""

    monkeypatch.setattr(controller, "run_command", lambda *_args, **_kwargs: Completed())

    with pytest.raises(RuntimeError, match="Changes were not committed, pushed, or opened"):
        controller.run_tests(tmp_path)


def test_iteration_limit_dry_run_does_not_mutate(tmp_path, monkeypatch, capsys):
    repo_root = tmp_path / "OrbitFlow-Evo"
    (repo_root / "scripts" / "orchestration").mkdir(parents=True)

    monkeypatch.setattr(controller, "repository_root", lambda: repo_root)
    monkeypatch.setattr(controller, "verify_repository", lambda *_args: None)
    monkeypatch.setattr(
        controller,
        "get_iteration_state",
        lambda *_args: controller.IterationState(15, "<!-- atlas-review -->"),
    )

    def forbidden(*_args, **_kwargs):
        raise AssertionError("iteration-limit dry-run must not mutate GitHub")

    monkeypatch.setattr(controller, "handle_iteration_limit", forbidden)

    controller.process_task(
        "a4212crew/OrbitFlow-Evo", _task("revision"), dry_run=True
    )

    assert "would move to codex-replan-required" in capsys.readouterr().out
