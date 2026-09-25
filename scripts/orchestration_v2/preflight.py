"""Complete read-only preflight for the replacement Codex controller."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from models import FailureCategory, OrchestrationError, PreflightReport


def run_command(
    args: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    completed = subprocess.run(
        args,
        cwd=cwd,
        env=env,
        check=False,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )
    if check and completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise OrchestrationError(
            FailureCategory.PREREQUISITE,
            f"{' '.join(args)} failed: {detail}",
        )
    return completed


def ensure_executable(name: str) -> None:
    if shutil.which(name) is None:
        raise OrchestrationError(
            FailureCategory.PREREQUISITE,
            f"{name} was not found on PATH.",
        )


def repository_root() -> Path:
    completed = run_command(
        ["git", "rev-parse", "--show-toplevel"],
        check=False,
    )
    if completed.returncode != 0:
        raise OrchestrationError(
            FailureCategory.PREREQUISITE,
            "Run the controller from inside the OrbitFlow-Evo repository.",
        )
    return Path(completed.stdout.strip()).resolve()


def verify_git_identity(repo_root: Path) -> tuple[str, str]:
    values: dict[str, str] = {}
    for key in ("user.name", "user.email"):
        completed = run_command(
            ["git", "config", "--get", key],
            cwd=repo_root,
            check=False,
        )
        values[key] = completed.stdout.strip() if completed.returncode == 0 else ""
    if not values["user.name"] or not values["user.email"]:
        raise OrchestrationError(
            FailureCategory.PREREQUISITE,
            "Git author identity is not configured. Configure user.name and user.email.",
        )
    return values["user.name"], values["user.email"]


def verify_repository(repo: str, repo_root: Path) -> None:
    completed = run_command(
        ["gh", "repo", "view", "--json", "nameWithOwner"],
        cwd=repo_root,
    )
    actual = json.loads(completed.stdout)["nameWithOwner"]
    if actual != repo:
        raise OrchestrationError(
            FailureCategory.PREREQUISITE,
            f"Repository identity mismatch. Expected '{repo}', got '{actual}'.",
        )

    dirty = run_command(
        ["git", "status", "--porcelain"],
        cwd=repo_root,
    ).stdout.strip()
    if dirty:
        raise OrchestrationError(
            FailureCategory.PREREQUISITE,
            "Control checkout is dirty. Commit, stash, or discard local changes first.\n"
            f"Dirty paths:\n{dirty}",
        )


def verify_codex_auth(repo_root: Path) -> tuple[str, str]:
    if os.environ.get("OPENAI_API_KEY", "").strip():
        raise OrchestrationError(
            FailureCategory.PREREQUISITE,
            "OPENAI_API_KEY is set. OrbitFlow-Evo Codex orchestration must use ChatGPT-account authentication only.",
        )

    version = run_command(["codex", "--version"], cwd=repo_root).stdout.strip()
    status = run_command(
        ["codex", "login", "status"],
        cwd=repo_root,
        check=False,
    )
    combined = "\n".join(part for part in (status.stdout, status.stderr) if part).strip()
    lowered = combined.lower()
    if status.returncode != 0:
        raise OrchestrationError(
            FailureCategory.PREREQUISITE,
            "Codex authentication check failed. Run 'codex login' with your ChatGPT account and retry. "
            f"Status output: {combined or '(none)'}",
        )
    if "api key" in lowered or "apikey" in lowered:
        raise OrchestrationError(
            FailureCategory.PREREQUISITE,
            "Codex reports API-key authentication. ChatGPT-account authentication is required.",
        )
    if "chatgpt" not in lowered:
        raise OrchestrationError(
            FailureCategory.PREREQUISITE,
            "Codex login is present but the controller cannot verify ChatGPT-account authentication from "
            f"'codex login status'. Status output: {combined or '(none)'}. Stop rather than guessing the billing path.",
        )
    return version, combined


def run_preflight(repo: str) -> PreflightReport:
    for executable in ("git", "gh", "codex"):
        ensure_executable(executable)

    repo_root = repository_root()
    git_name, git_email = verify_git_identity(repo_root)
    run_command(["gh", "auth", "status"], cwd=repo_root)
    verify_repository(repo, repo_root)
    codex_version, codex_auth_status = verify_codex_auth(repo_root)

    return PreflightReport(
        repo_root=repo_root,
        git_name=git_name,
        git_email=git_email,
        codex_version=codex_version,
        codex_auth_status=codex_auth_status,
    )
