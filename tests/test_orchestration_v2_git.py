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
