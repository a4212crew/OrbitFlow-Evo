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

def test_verify_repository_reports_dirty_paths(monkeypatch, tmp_path):
    class Completed:
        stdout = '{"nameWithOwner":"a4212crew/OrbitFlow-Evo"}'

    monkeypatch.setattr(controller, "run_command", lambda *_args, **_kwargs: Completed())
    monkeypatch.setattr(controller, "verify_git_identity", lambda *_args: None)
    monkeypatch.setattr(
        controller,
        "git",
        lambda *_args, **_kwargs: " M README.md\n?? local-note.txt",
    )

    with pytest.raises(RuntimeError) as error:
        controller.verify_repository("a4212crew/OrbitFlow-Evo", tmp_path)

    message = str(error.value)
    assert "Dirty paths:" in message
    assert "README.md" in message
    assert "local-note.txt" in message


def test_process_one_failure_removes_queue_labels(monkeypatch):
    task = _task("initial")
    label_calls = []
    comments = []

    monkeypatch.setattr(controller, "get_next_task", lambda _repo: task)
    monkeypatch.setattr(
        controller,
        "process_task",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("boom")),
    )
    monkeypatch.setattr(
        controller,
        "set_issue_labels",
        lambda repo, issue_number, **kwargs: label_calls.append(
            (repo, issue_number, kwargs)
        ),
    )
    monkeypatch.setattr(
        controller,
        "add_issue_comment",
        lambda repo, issue_number, body: comments.append(
            (repo, issue_number, body)
        ),
    )

    assert controller.process_one("a4212crew/OrbitFlow-Evo") is True

    assert label_calls == [
        (
            "a4212crew/OrbitFlow-Evo",
            42,
            {
                "add": ("codex-failed",),
                "remove": ("codex-task", "codex-revise", "codex-running"),
            },
        )
    ]
    assert comments[0][1] == 42
    assert "boom" in comments[0][2]

def test_run_codex_uses_workspace_write_and_worktree_temp(monkeypatch, tmp_path):
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    output_path = tmp_path / "codex-output.txt"
    captured = {}

    class FakeStdout:
        def __iter__(self):
            return iter(["done\n"])

    class FakeProcess:
        stdout = FakeStdout()

        def wait(self):
            return 0

    def fake_popen(args, **kwargs):
        captured["args"] = args
        captured["cwd"] = kwargs["cwd"]
        captured["env"] = kwargs["env"]
        return FakeProcess()

    monkeypatch.setattr(controller.subprocess, "Popen", fake_popen)

    controller.run_codex("test prompt", worktree, output_path)

    assert captured["args"] == [
        "codex",
        "exec",
        "--sandbox",
        "workspace-write",
        "test prompt",
    ]
    assert captured["cwd"] == worktree
    assert captured["env"]["TEMP"] == str(worktree / ".codex-tmp")
    assert captured["env"]["TMP"] == str(worktree / ".codex-tmp")
    assert captured["env"]["TMPDIR"] == str(worktree / ".codex-tmp")
    assert not (worktree / ".codex-tmp").exists()
    assert output_path.read_text(encoding="utf-8") == "done\n"


def test_run_codex_cleans_temp_dir_on_failure(monkeypatch, tmp_path):
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    output_path = tmp_path / "codex-output.txt"

    class FakeStdout:
        def __iter__(self):
            return iter(())

    class FakeProcess:
        stdout = FakeStdout()

        def wait(self):
            return 9

    monkeypatch.setattr(
        controller.subprocess,
        "Popen",
        lambda *_args, **_kwargs: FakeProcess(),
    )

    with pytest.raises(RuntimeError, match="Codex exited with code 9"):
        controller.run_codex("test prompt", worktree, output_path)

    assert not (worktree / ".codex-tmp").exists()

def test_verify_git_identity_rejects_missing_email(monkeypatch, tmp_path):
    class Completed:
        def __init__(self, returncode, stdout):
            self.returncode = returncode
            self.stdout = stdout

    def fake_run(args, **_kwargs):
        if args[-1] == "user.name":
            return Completed(0, "a4212crew\n")
        return Completed(1, "")

    monkeypatch.setattr(controller, "run_command", fake_run)

    with pytest.raises(RuntimeError, match="Git author identity is not configured"):
        controller.verify_git_identity(tmp_path)


def test_verify_git_identity_accepts_resolved_name_and_email(monkeypatch, tmp_path):
    class Completed:
        returncode = 0

        def __init__(self, stdout):
            self.stdout = stdout

    values = {
        "user.name": "a4212crew\n",
        "user.email": "dev@example.test\n",
    }
    monkeypatch.setattr(
        controller,
        "run_command",
        lambda args, **_kwargs: Completed(values[args[-1]]),
    )

    controller.verify_git_identity(tmp_path)

