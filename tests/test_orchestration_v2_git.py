from pathlib import Path
import sys

import pytest

ORCH = Path(__file__).parents[1] / "scripts" / "orchestration_v2"
sys.path.insert(0, str(ORCH))

import git_ops  # noqa: E402
from models import FailureCategory, OrchestrationError  # noqa: E402


def test_planned_workspace_is_dedicated_sibling(tmp_path):
    repo_root = tmp_path / "OrbitFlow-Evo"

    workspace = git_ops.planned_workspace(42, repo_root)

    assert workspace.branch == "codex/issue-42"
    assert workspace.path == tmp_path / "OrbitFlow-Evo-worktrees" / "issue-42"


def test_initial_workspace_rejects_branch_conflict(monkeypatch, tmp_path):
    repo_root = tmp_path / "OrbitFlow-Evo"
    repo_root.mkdir()
    monkeypatch.setattr(git_ops, "local_branch_exists", lambda *_args: True)
    monkeypatch.setattr(git_ops, "remote_branch_exists", lambda *_args: False)
    monkeypatch.setattr(git_ops, "registered_worktree_paths", lambda *_args: set())

    with pytest.raises(OrchestrationError) as error:
        git_ops.validate_workspace("initial", 42, repo_root)

    assert error.value.category is FailureCategory.PREREQUISITE
    assert "local branch exists" in str(error.value)


def test_revision_requires_remote_branch(monkeypatch, tmp_path):
    repo_root = tmp_path / "OrbitFlow-Evo"
    repo_root.mkdir()
    monkeypatch.setattr(git_ops, "local_branch_exists", lambda *_args: False)
    monkeypatch.setattr(git_ops, "remote_branch_exists", lambda *_args: False)
    monkeypatch.setattr(git_ops, "registered_worktree_paths", lambda *_args: set())

    with pytest.raises(OrchestrationError, match="remote task branch"):
        git_ops.validate_workspace("revision", 42, repo_root)


def test_commit_uses_preflight_identity_and_pushes_exact_branch(monkeypatch, tmp_path):
    from types import SimpleNamespace
    from models import Workspace, PreflightReport, Task
    import temp_cleanup
    monkeypatch.setattr(temp_cleanup, 'cleanup_temp',
                        lambda *_: pytest.fail('Git staging must not depend on temporary cleanup'))
    calls = []
    def fake_git(args, **kwargs):
        calls.append(args)
        output = 'codex/issue-13' if args[0] == 'branch' else 'changed.py'
        return SimpleNamespace(stdout=output)
    monkeypatch.setattr(git_ops, 'git', fake_git)
    git_ops.commit_and_push(Workspace('codex/issue-13', tmp_path),
                            PreflightReport(tmp_path, 'Author', 'author@example.test', 'v', 'ChatGPT'),
                            Task('revision', 13, 'Title', '', ''), 2)
    assert calls[1] == ['add', '--all', '--', '.']
    assert calls[3][:4] == ['-c', 'user.name=Author', '-c', 'user.email=author@example.test']
    assert calls[4] == ['push', '--set-upstream', 'origin', 'HEAD:refs/heads/codex/issue-13']


def test_wrong_branch_cannot_stage(monkeypatch, tmp_path):
    from types import SimpleNamespace
    from models import Workspace
    calls = []
    def fake_git(args, **kwargs):
        calls.append(args)
        return SimpleNamespace(stdout='main')
    monkeypatch.setattr(git_ops, 'git', fake_git)
    with pytest.raises(OrchestrationError, match='branch changed'):
        git_ops.commit_and_push(Workspace('codex/issue-1', tmp_path), None, None, 1)
    assert len(calls) == 1
