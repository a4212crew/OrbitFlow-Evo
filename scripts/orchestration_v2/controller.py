"""One-task replacement-candidate Codex controller, phases 1-3."""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

from codex_runner import build_prompt, ensure_repository_changes, run_codex, run_tests
from git_ops import prepare_workspace, validate_workspace
from github_ops import get_next_task
from models import FailureCategory, OrchestrationError
from preflight import run_preflight

DEFAULT_REPO = "a4212crew/OrbitFlow-Evo"


def process_one(repo: str, *, dry_run: bool = False) -> bool:
    report = run_preflight(repo)
    task = get_next_task(repo, report.repo_root)
    if task is None:
        print("No codex-task or codex-revise issue is waiting.")
        return False

    workspace = validate_workspace(task.mode, task.number, report.repo_root)
    print(f"Preflight passed for {repo}.")
    print(f"Git author: {report.git_name} <{report.git_email}>")
    print(f"Codex CLI: {report.codex_version}")
    print(f"Task: issue #{task.number} ({task.mode}) - {task.title}")
    print(f"Branch: {workspace.branch}")
    print(f"Worktree: {workspace.path}")

    if dry_run:
        print("DRY RUN: no worktree, Codex process, labels, commits, pushes, or PRs were changed.")
        return True

    workspace = prepare_workspace(task.mode, task.number, report.repo_root)
    preamble_path = workspace.path / "scripts" / "orchestration_v2" / "task-preamble.md"
    prompt = build_prompt(preamble_path.read_text(encoding="utf-8"), task)
    output_path = Path(tempfile.gettempdir()) / f"orbitflow-codex-v2-{task.number}.txt"
    output_path.unlink(missing_ok=True)
    try:
        run_codex(prompt, workspace.path, output_path)
        ensure_repository_changes(workspace.path)
        run_tests(workspace.path)
    finally:
        output_path.unlink(missing_ok=True)

    print()
    print("Phase 3 complete: Codex produced changes and deterministic tests passed.")
    print(f"Changes remain UNCOMMITTED in: {workspace.path}")
    print("Commit/push/PR/GitHub state progression is intentionally deferred to Phase 4.")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    try:
        process_one(args.repo, dry_run=args.dry_run)
    except OrchestrationError as exc:
        print(f"{exc.category.value}: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    except Exception as exc:
        print(
            f"{FailureCategory.CONTROLLER.value}: {exc}",
            file=sys.stderr,
        )
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
