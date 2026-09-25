"""Local Codex execution and deterministic test gate for orchestration v2."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from models import FailureCategory, OrchestrationError, Task


def build_prompt(preamble: str, task: Task) -> str:
    return "\n".join(
        [
            preamble.rstrip(),
            "",
            "# GitHub Task",
            f"Issue #{task.number}: {task.title}",
            "",
            task.body,
            "",
            "# Controller boundary",
            "Implement and test only. Do not commit, push, create/update PRs, change GitHub labels, or merge.",
        ]
    )


def run_codex(prompt: str, worktree: Path, output_path: Path) -> None:
    temp_dir = worktree / ".codex-tmp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env.pop("OPENAI_API_KEY", None)
    env["TEMP"] = str(temp_dir)
    env["TMP"] = str(temp_dir)
    env["TMPDIR"] = str(temp_dir)

    try:
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
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


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
    completed = subprocess.run(
        ["python", "-m", "pytest", "-q"],
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
