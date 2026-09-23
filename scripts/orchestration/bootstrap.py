"""Cross-platform bootstrap for OrbitFlow-Evo local Codex orchestration."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from dataclasses import dataclass


DEFAULT_REPO = "a4212crew/OrbitFlow-Evo"


@dataclass(frozen=True)
class LabelSpec:
    name: str
    color: str
    description: str


LABELS = (
    LabelSpec("codex-task", "1D76DB", "Task approved for Codex implementation"),
    LabelSpec("codex-running", "FBCA04", "Codex implementation is running locally"),
    LabelSpec("codex-review", "5319E7", "Waiting for Atlas review"),
    LabelSpec("codex-revise", "D93F0B", "Atlas requested another Codex revision"),
    LabelSpec("codex-approved", "0E8A16", "Atlas review passed"),
    LabelSpec("codex-pr", "8250DF", "Task has an open Codex pull request"),
    LabelSpec("codex-failed", "B60205", "Codex controller failed"),
    LabelSpec(
        "codex-replan-required",
        "B60205",
        "15-iteration limit reached; implementation plan must be revisited",
    ),
)


def run_command(args: list[str]) -> str:
    completed = subprocess.run(
        args,
        check=False,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise RuntimeError(f"{' '.join(args)} failed: {detail}")
    return completed.stdout.strip()


def ensure_executable(name: str) -> None:
    if shutil.which(name) is None:
        raise RuntimeError(f"{name} was not found on PATH.")


def verify_git_identity() -> tuple[str, str]:
    values = []
    for key in ("user.name", "user.email"):
        try:
            values.append(run_command(["git", "config", "--get", key]).strip())
        except RuntimeError:
            values.append("")

    if not all(values):
        raise RuntimeError(
            "Git author identity is not configured. "
            "Set user.name and user.email before running the Codex controller."
        )
    return values[0], values[1]


def bootstrap(repo: str = DEFAULT_REPO) -> None:
    print("Validating OrbitFlow-Evo local Codex prerequisites...")

    ensure_executable("git")
    ensure_executable("gh")
    ensure_executable("codex")

    git_name, git_email = verify_git_identity()
    run_command(["gh", "auth", "status"])
    codex_version = run_command(["codex", "--version"])

    repo_json = run_command(["gh", "repo", "view", repo, "--json", "nameWithOwner"])
    actual_repo = json.loads(repo_json)["nameWithOwner"]
    if actual_repo != repo:
        raise RuntimeError(
            f"Repository identity mismatch. Expected '{repo}' but GitHub returned '{actual_repo}'."
        )

    for label in LABELS:
        run_command(
            [
                "gh",
                "label",
                "create",
                label.name,
                "--repo",
                repo,
                "--color",
                label.color,
                "--description",
                label.description,
                "--force",
            ]
        )

    print()
    print("Bootstrap complete.")
    print(f"Repository: {repo}")
    print("GitHub CLI: authenticated")
    print(f"Git author: {git_name} <{git_email}>")
    print(f"Codex CLI: {codex_version}")
    print()
    print("Codex authentication must use your ChatGPT account.")
    print("If needed, run: codex login")
    print()
    print("No OPENAI_API_KEY is required by this orchestration.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=DEFAULT_REPO)
    args = parser.parse_args()
    bootstrap(args.repo)


if __name__ == "__main__":
    main()
