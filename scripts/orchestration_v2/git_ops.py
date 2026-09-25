"""Git branch/worktree mechanics for orchestration v2."""

from __future__ import annotations

import subprocess
from pathlib import Path

from models import FailureCategory, OrchestrationError, Workspace


def git(args: list[str], *, cwd: Path, check: bool = True) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=False,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )
    if check and completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise OrchestrationError(
            FailureCategory.CONTROLLER,
            f"git {' '.join(args)} failed: {detail}",
        )
    return completed


def planned_workspace(issue_number: int, repo_root: Path) -> Workspace:
    return Workspace(
        branch=f"codex/issue-{issue_number}",
        path=repo_root.parent / "OrbitFlow-Evo-worktrees" / f"issue-{issue_number}",
    )


def local_branch_exists(branch: str, repo_root: Path) -> bool:
    result = git(
        ["show-ref", "--verify", "--quiet", f"refs/heads/{branch}"],
        cwd=repo_root,
        check=False,
    )
    return result.returncode == 0


def remote_branch_exists(branch: str, repo_root: Path) -> bool:
    result = git(
        ["ls-remote", "--exit-code", "--heads", "origin", branch],
        cwd=repo_root,
        check=False,
    )
    if result.returncode not in (0, 2):
        raise OrchestrationError(
            FailureCategory.CONTROLLER,
            f"Unable to check remote branch '{branch}'.",
        )
    return result.returncode == 0


def registered_worktree_paths(repo_root: Path) -> set[Path]:
    output = git(["worktree", "list", "--porcelain"], cwd=repo_root).stdout
    paths: set[Path] = set()
    for line in output.splitlines():
        if line.startswith("worktree "):
            paths.add(Path(line.removeprefix("worktree ")).resolve())
    return paths


def validate_workspace(task_mode: str, issue_number: int, repo_root: Path) -> Workspace:
    workspace = planned_workspace(issue_number, repo_root)
    local_exists = local_branch_exists(workspace.branch, repo_root)
    remote_exists = remote_branch_exists(workspace.branch, repo_root)
    registered = workspace.path.resolve() in registered_worktree_paths(repo_root)

    if task_mode == "initial":
        conflicts = []
        if local_exists:
            conflicts.append("local branch exists")
        if remote_exists:
            conflicts.append("remote branch exists")
        if workspace.path.exists():
            conflicts.append("worktree path exists")
        if registered:
            conflicts.append("worktree is already registered")
        if conflicts:
            raise OrchestrationError(
                FailureCategory.PREREQUISITE,
                f"Conflicting task workspace for issue #{issue_number}: {', '.join(conflicts)}.",
            )
        return workspace

    if not remote_exists:
        raise OrchestrationError(
            FailureCategory.PREREQUISITE,
            f"Revision requested but remote task branch '{workspace.branch}' does not exist.",
        )
    if workspace.path.exists() and not registered:
        raise OrchestrationError(
            FailureCategory.PREREQUISITE,
            f"Revision worktree path '{workspace.path}' exists but is not a registered Git worktree.",
        )
    return workspace


def prepare_workspace(task_mode: str, issue_number: int, repo_root: Path) -> Workspace:
    workspace = validate_workspace(task_mode, issue_number, repo_root)
    git(["fetch", "origin", "--prune"], cwd=repo_root)

    if task_mode == "initial":
        workspace.path.parent.mkdir(parents=True, exist_ok=True)
        git(
            [
                "worktree",
                "add",
                "-b",
                workspace.branch,
                str(workspace.path),
                "origin/main",
            ],
            cwd=repo_root,
        )
        return workspace

    registered = workspace.path.resolve() in registered_worktree_paths(repo_root)
    if not registered:
        workspace.path.parent.mkdir(parents=True, exist_ok=True)
        if local_branch_exists(workspace.branch, repo_root):
            git(["worktree", "add", str(workspace.path), workspace.branch], cwd=repo_root)
        else:
            git(
                [
                    "worktree",
                    "add",
                    "-b",
                    workspace.branch,
                    str(workspace.path),
                    f"origin/{workspace.branch}",
                ],
                cwd=repo_root,
            )

    dirty = git(["status", "--porcelain"], cwd=workspace.path).stdout.strip()
    if dirty:
        raise OrchestrationError(
            FailureCategory.PREREQUISITE,
            "Revision worktree contains uncommitted changes. Resolve them before running another Codex revision.\n"
            f"Dirty paths:\n{dirty}",
        )
    return workspace
