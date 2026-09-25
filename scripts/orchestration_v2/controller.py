"""Serial Codex controller with optional safe queue watching."""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from codex_runner import build_prompt, ensure_repository_changes, run_codex, run_tests
from git_ops import prepare_workspace, validate_workspace, commit_and_push, git
from github_ops import get_next_task, review_context, transition, comment, find_pr, publish_pr
from models import MAX_ITERATIONS, FailureCategory, OrchestrationError
from preflight import run_preflight
from temp_cleanup import controller_temp

DEFAULT_REPO = "a4212crew/OrbitFlow-Evo"


def process_one(repo: str, *, dry_run: bool = False) -> bool:
    report = run_preflight(repo)
    task = get_next_task(repo, report.repo_root)
    if task is None:
        print("No codex-task or codex-revise issue is waiting.")
        return False

    try:
        count, review = review_context(repo, task, report.repo_root)
        if count >= MAX_ITERATIONS:
            if not dry_run:
                transition(repo, task, "codex-replan-required", report.repo_root)
                comment(repo, task, f"{MAX_ITERATIONS} iterations exhausted. Atlas and user must approve a new plan.", report.repo_root)
            print("Replan required; Codex was not invoked.")
            return True
        workspace = validate_workspace(task.mode, task.number, report.repo_root)
        existing = find_pr(repo, workspace.branch, report.repo_root)
        if task.mode == "revision" and not existing:
            raise OrchestrationError(FailureCategory.PREREQUISITE, "Revision requires the existing open task PR.")
        if dry_run:
            print(f"DRY RUN: {workspace.branch}; no mutations or Codex execution.")
            return True
        transition(repo, task, "codex-running", report.repo_root)
        workspace = prepare_workspace(task.mode, task.number, report.repo_root)
        preamble_path = workspace.path / "scripts" / "orchestration_v2" / "task-preamble.md"
        prompt = build_prompt(preamble_path.read_text(encoding="utf-8"), task, review if task.mode == "revision" else "")
        starting_head = git(["rev-parse", "HEAD"], cwd=workspace.path).stdout.strip()
        with controller_temp(workspace.path, "output") as directory:
            run_codex(prompt, workspace.path, Path(directory) / "output.txt")
        if git(["rev-parse", "HEAD"], cwd=workspace.path).stdout.strip() != starting_head:
            raise OrchestrationError(FailureCategory.CODEX, "Worker changed HEAD; controller-only commit boundary violated.")
        ensure_repository_changes(workspace.path)
        run_tests(workspace.path)
        commit_and_push(workspace, report, task, count + 1)
        pr = publish_pr(repo, task, workspace.branch, report.repo_root, existing)
        transition(repo, task, "codex-pr", report.repo_root)
        comment(repo, task, f"<!-- orbitflow-codex-iteration:{count + 1} -->\n"
                f"Full deterministic pytest suite passed. Ready for Atlas review: {pr}", report.repo_root)
        transition(repo, task, "codex-review", report.repo_root)
        print(f"Iteration {count + 1} ready for review: {pr}")
        return True
    except Exception as exc:
        error = exc if isinstance(exc, OrchestrationError) else OrchestrationError(FailureCategory.CONTROLLER, str(exc))
        if not dry_run:
            try:
                transition(repo, task, "codex-failed", report.repo_root)
                comment(repo, task, f"{error.category.value}: {error}", report.repo_root)
            except Exception as reporting_error:
                raise OrchestrationError(error.category, f"{error}; failure reporting also failed: {reporting_error}. "
                                         "Stop queue processing and inspect the issue manually.") from exc
        raise error from exc


def poll_seconds(value: str) -> int:
    seconds = int(value)
    if seconds < 5:
        raise argparse.ArgumentTypeError("--poll-seconds must be at least 5")
    return seconds


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--poll-seconds", type=poll_seconds, default=15)
    args = parser.parse_args()

    try:
        while True:
            process_one(args.repo, dry_run=args.dry_run)
            if not args.watch:
                break
            time.sleep(args.poll_seconds)
    except KeyboardInterrupt:
        print("Controller stopped by operator.")
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
