"""Read-only GitHub task discovery for orchestration v2 phases 1-3."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from models import FailureCategory, OrchestrationError, Task


def gh(args: list[str], *, cwd: Path) -> str:
    completed = subprocess.run(
        ["gh", *args],
        cwd=cwd,
        check=False,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise OrchestrationError(
            FailureCategory.CONTROLLER,
            f"gh {' '.join(args)} failed: {detail}",
        )
    return completed.stdout.strip()


def get_next_task(repo: str, repo_root: Path) -> Task | None:
    for label, mode in (("codex-revise", "revision"), ("codex-task", "initial")):
        payload = json.loads(
            gh(
                [
                    "issue",
                    "list",
                    "--repo",
                    repo,
                    "--label",
                    label,
                    "--state",
                    "open",
                    "--limit",
                    "1",
                    "--json",
                    "number,title,body,url",
                ],
                cwd=repo_root,
            )
        )
        if payload:
            issue = payload[0]
            return Task(
                mode=mode,
                number=int(issue["number"]),
                title=str(issue["title"]),
                body=str(issue.get("body") or ""),
                url=str(issue.get("url") or ""),
            )
    return None
