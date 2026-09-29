"""Local Codex execution and deterministic test gate for orchestration v2."""

from __future__ import annotations

import os
import sys
import subprocess
from pathlib import Path

from temp_cleanup import controller_temp

from models import FailureCategory, OrchestrationError, Task


def build_prompt(preamble: str, task: Task, review: str = "") -> str:
    return "\n".join(
        [
            preamble.rstrip(),
            "",
            "# GitHub Task",
            f"Issue #{task.number}: {task.title}",
            "",
            task.body,
            "",
            "# Requested revision only" if review else "",
            review,
            "# Controller boundary",
            "Implement and test only. Do not commit, push, create/update PRs, change GitHub labels, or merge.",
        ]
    )


def run_codex(prompt: str, worktree: Path, output_path: Path) -> None:
    with controller_temp(worktree, "codex") as temp_dir:
        _run_codex(prompt, worktree, output_path, temp_dir)


def _run_codex(prompt: str, worktree: Path, output_path: Path, temp_dir: Path) -> None:
    env = os.environ.copy()
    env.pop("OPENAI_API_KEY", None)
    env["TEMP"] = str(temp_dir)
    env["TMP"] = str(temp_dir)
    env["TMPDIR"] = str(temp_dir)

    with output_path.open("w", encoding="utf-8") as output:
        process = subprocess.Popen(
            ["codex", "exec", "--sandbox", "workspace-write", prompt],
            cwd=worktree,
            env=env,
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
        )
        assert process.stdout is not None
        for line in process.stdout:
            print(line, end="")
            output.write(line)
        return_code = process.wait()
    if return_code != 0:
        raise OrchestrationError(
            FailureCategory.CODEX,
            f"Codex exited with code {return_code}. If included ChatGPT-plan usage is unavailable or exhausted, stop here; do not switch billing paths.",
        )


def ensure_repository_changes(worktree: Path) -> None:
    completed = subprocess.run(
        ["git", "status", "--porcelain"],
        cwd=worktree,
        check=False,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )
    if completed.returncode != 0:
        raise OrchestrationError(
            FailureCategory.CONTROLLER,
            f"Unable to inspect Codex changes: {(completed.stderr or completed.stdout).strip()}",
        )
    if not completed.stdout.strip():
        raise OrchestrationError(
            FailureCategory.CODEX,
            "Codex completed without repository changes.",
        )


def run_tests(worktree: Path) -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = "src"
    with controller_temp(worktree, "pytest") as temp_dir:
        for key in ("TEMP", "TMP", "TMPDIR"):
            env[key] = str(temp_dir)
        _run_tests(worktree, env, temp_dir)


def _run_tests(worktree: Path, env: dict[str, str], temp_dir: Path) -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "pytest", "-q", "--basetemp", str(temp_dir / "pytest")],
        cwd=worktree,
        env=env,
        check=False,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )
    if completed.stdout:
        print(completed.stdout, end="")
    if completed.stderr:
        print(completed.stderr, end="")
    if completed.returncode != 0:
        raise OrchestrationError(
            FailureCategory.TEST,
            f"Deterministic tests failed with exit code {completed.returncode}. Changes remain uncommitted in the task worktree.",
        )
