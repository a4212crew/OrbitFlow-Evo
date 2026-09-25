from pathlib import Path
import sys

ORCH = Path(__file__).parents[1] / "scripts" / "orchestration_v2"
sys.path.insert(0, str(ORCH))

import controller  # noqa: E402
from models import PreflightReport, Task, Workspace  # noqa: E402


def test_dry_run_is_non_mutating(monkeypatch, tmp_path, capsys):
    repo_root = tmp_path / "OrbitFlow-Evo"
    repo_root.mkdir()
    report = PreflightReport(
        repo_root=repo_root,
        git_name="Atlas",
        git_email="atlas@example.test",
        codex_version="codex-cli test",
        codex_auth_status="Logged in using ChatGPT",
    )
    task = Task("initial", 42, "Smoke test", "Edit docs only.", "https://example.test/42")
    workspace = Workspace("codex/issue-42", tmp_path / "OrbitFlow-Evo-worktrees" / "issue-42")

    monkeypatch.setattr(controller, "run_preflight", lambda _repo: report)
    monkeypatch.setattr(controller, "get_next_task", lambda *_args: task)
    monkeypatch.setattr(controller, "validate_workspace", lambda *_args: workspace)

    def forbidden(*_args, **_kwargs):
        raise AssertionError("dry-run must not mutate or invoke Codex")

    monkeypatch.setattr(controller, "prepare_workspace", forbidden)
    monkeypatch.setattr(controller, "run_codex", forbidden)
    monkeypatch.setattr(controller, "run_tests", forbidden)

    assert controller.process_one("a4212crew/OrbitFlow-Evo", dry_run=True) is True

    rendered = capsys.readouterr().out
    assert "DRY RUN" in rendered
    assert "codex/issue-42" in rendered


def test_normal_phase3_stops_after_tests(monkeypatch, tmp_path, capsys):
    repo_root = tmp_path / "OrbitFlow-Evo"
    worktree = tmp_path / "OrbitFlow-Evo-worktrees" / "issue-42"
    preamble_dir = worktree / "scripts" / "orchestration_v2"
    preamble_dir.mkdir(parents=True)
    (preamble_dir / "task-preamble.md").write_text("PREAMBLE", encoding="utf-8")
    report = PreflightReport(repo_root, "Atlas", "atlas@example.test", "codex-cli test", "Logged in using ChatGPT")
    task = Task("initial", 42, "Smoke test", "Edit docs only.", "https://example.test/42")
    workspace = Workspace("codex/issue-42", worktree)
    calls = []

    monkeypatch.setattr(controller, "run_preflight", lambda _repo: report)
    monkeypatch.setattr(controller, "get_next_task", lambda *_args: task)
    monkeypatch.setattr(controller, "validate_workspace", lambda *_args: workspace)
    monkeypatch.setattr(controller, "prepare_workspace", lambda *_args: workspace)
    monkeypatch.setattr(controller, "run_codex", lambda *_args: calls.append("codex"))
    monkeypatch.setattr(controller, "ensure_repository_changes", lambda *_args: calls.append("changes"))
    monkeypatch.setattr(controller, "run_tests", lambda *_args: calls.append("tests"))

    assert controller.process_one("a4212crew/OrbitFlow-Evo") is True

    assert calls == ["codex", "changes", "tests"]
    assert "remain UNCOMMITTED" in capsys.readouterr().out
