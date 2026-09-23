"""Cross-platform GitHub-Issue-driven local Codex controller for OrbitFlow-Evo."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


DEFAULT_REPO = "a4212crew/OrbitFlow-Evo"
MAX_ITERATIONS = 15
MIN_POLL_SECONDS = 5
OUTPUT_LIMIT = 6000
ITERATION_MARKER = "<!-- orbitflow-codex-iteration:"
ATLAS_REVIEW_MARKER = "<!-- atlas-review -->"


@dataclass(frozen=True)
class Task:
    mode: str
    issue: dict[str, Any]


@dataclass(frozen=True)
class IterationState:
    iteration: int
    atlas_review: str | None


@dataclass(frozen=True)
class Worktree:
    branch: str
    path: Path


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
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=True,
        check=False,
    )
    if check and completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise RuntimeError(f"{' '.join(args)} failed: {detail}")
    return completed


def gh(args: Iterable[str]) -> str:
    completed = run_command(["gh", *args])
    return completed.stdout.strip()


def git(args: Iterable[str], cwd: Path) -> str:
    completed = run_command(["git", *args], cwd=cwd)
    return completed.stdout.strip()


def ensure_executable(name: str) -> None:
    if shutil.which(name) is None:
        raise RuntimeError(f"{name} was not found on PATH.")


def set_issue_labels(
    repo: str,
    issue_number: int,
    *,
    add: Iterable[str] = (),
    remove: Iterable[str] = (),
) -> None:
    args = ["issue", "edit", str(issue_number), "--repo", repo]
    for label in remove:
        args.extend(["--remove-label", label])
    for label in add:
        args.extend(["--add-label", label])
    gh(args)


def add_issue_comment(repo: str, issue_number: int, body: str) -> None:
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            suffix=".md",
            prefix=f"orbitflow-codex-comment-{issue_number}-",
            delete=False,
        ) as handle:
            handle.write(body)
            temp_path = Path(handle.name)
        gh(
            [
                "issue",
                "comment",
                str(issue_number),
                "--repo",
                repo,
                "--body-file",
                str(temp_path),
            ]
        )
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def parse_iteration_state(
    comments: Iterable[dict[str, Any]], owner: str
) -> IterationState:
    max_iteration = 0
    latest_atlas_review: str | None = None
    for comment in comments:
        body = str(comment.get("body", ""))
        search_from = 0
        while True:
            start = body.find(ITERATION_MARKER, search_from)
            if start < 0:
                break
            number_start = start + len(ITERATION_MARKER)
            number_end = body.find(" -->", number_start)
            if number_end < 0:
                break
            try:
                max_iteration = max(
                    max_iteration, int(body[number_start:number_end].strip())
                )
            except ValueError:
                pass
            search_from = number_end + 4

        author = comment.get("author") or {}
        if author.get("login") == owner and ATLAS_REVIEW_MARKER in body:
            latest_atlas_review = body

    return IterationState(max_iteration, latest_atlas_review)


def get_iteration_state(repo: str, issue_number: int) -> IterationState:
    payload = json.loads(
        gh(
            [
                "issue",
                "view",
                str(issue_number),
                "--repo",
                repo,
                "--json",
                "comments",
            ]
        )
    )
    owner = repo.split("/", 1)[0]
    return parse_iteration_state(payload.get("comments", []), owner)


def get_next_task(repo: str) -> Task | None:
    for label, mode in (("codex-revise", "revision"), ("codex-task", "initial")):
        issues = json.loads(
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
                ]
            )
        )
        if issues:
            return Task(mode=mode, issue=issues[0])
    return None


def repository_root() -> Path:
    completed = run_command(["git", "rev-parse", "--show-toplevel"], check=False)
    if completed.returncode != 0:
        raise RuntimeError(
            "Run the controller from inside the OrbitFlow-Evo repository."
        )
    return Path(completed.stdout.strip()).resolve()


def verify_repository(repo: str, repo_root: Path) -> None:
    completed = run_command(
        ["gh", "repo", "view", "--json", "nameWithOwner"],
        cwd=repo_root,
    )
    actual = json.loads(completed.stdout)["nameWithOwner"]
    if actual != repo:
        raise RuntimeError(
            f"Repository identity mismatch. Expected '{repo}', got '{actual}'."
        )
    dirty = git(["status", "--porcelain"], repo_root)
    if dirty:
        raise RuntimeError(
            "Main checkout is dirty. Commit, stash, or discard local changes before running Codex."
            + os.linesep
            + "Dirty paths:"
            + os.linesep
            + dirty
        )


def remote_branch_exists(repo_root: Path, branch: str) -> bool:
    completed = run_command(
        ["git", "ls-remote", "--heads", "origin", branch],
        cwd=repo_root,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(f"Unable to check remote branch '{branch}'.")
    return bool(completed.stdout.strip())


def local_branch_exists(repo_root: Path, branch: str) -> bool:
    return bool(git(["branch", "--list", branch], repo_root))


def planned_worktree(issue_number: int, repo_root: Path) -> Worktree:
    return Worktree(
        branch=f"codex/issue-{issue_number}",
        path=repo_root.parent / "OrbitFlow-Evo-worktrees" / f"issue-{issue_number}",
    )


def ensure_worktree(
    issue_number: int,
    mode: str,
    repo_root: Path,
) -> Worktree:
    worktree = planned_worktree(issue_number, repo_root)
    worktree.path.parent.mkdir(parents=True, exist_ok=True)
    git(["fetch", "origin", "--prune"], repo_root)

    if mode == "initial":
        if remote_branch_exists(repo_root, worktree.branch):
            raise RuntimeError(
                f"Task branch '{worktree.branch}' already exists. "
                "Refusing duplicate initial execution."
            )
        if worktree.path.exists():
            raise RuntimeError(
                f"Worktree path '{worktree.path}' already exists. "
                "Clean it up before retrying."
            )
        git(
            [
                "worktree",
                "add",
                "-b",
                worktree.branch,
                str(worktree.path),
                "origin/main",
            ],
            repo_root,
        )
        return worktree

    if not remote_branch_exists(repo_root, worktree.branch):
        raise RuntimeError(
            f"Revision requested but remote task branch '{worktree.branch}' does not exist."
        )

    git(["fetch", "origin", worktree.branch], repo_root)
    if not worktree.path.exists():
        if local_branch_exists(repo_root, worktree.branch):
            git(["worktree", "add", str(worktree.path), worktree.branch], repo_root)
        else:
            git(
                [
                    "worktree",
                    "add",
                    "-b",
                    worktree.branch,
                    str(worktree.path),
                    f"origin/{worktree.branch}",
                ],
                repo_root,
            )

    git(["reset", "--hard", f"origin/{worktree.branch}"], worktree.path)
    git(["clean", "-fd"], worktree.path)
    return worktree


def determine_iteration(
    task: Task, state: IterationState
) -> int:
    issue_number = int(task.issue["number"])
    if task.mode == "revision":
        if state.iteration >= MAX_ITERATIONS:
            raise RuntimeError("iteration-limit-reached")
        if not state.atlas_review or not state.atlas_review.strip():
            raise RuntimeError(
                "Revision requested but no owner-authored atlas-review marker comment was found."
            )
        return state.iteration + 1

    if state.iteration > 0:
        raise RuntimeError(
            f"Issue #{issue_number} already has Codex iteration history; "
            "refusing a second initial run."
        )
    return 1


def build_prompt(
    preamble: str,
    task: Task,
    iteration: int,
    atlas_review: str | None,
) -> str:
    issue = task.issue
    parts = [
        preamble.rstrip(),
        "",
        "# GitHub Task",
        f"Issue #{issue['number']}: {issue['title']}",
        "",
        str(issue.get("body") or ""),
        "",
        "# Iteration",
        (
            f"This is implementation/review iteration {iteration} of a maximum "
            f"{MAX_ITERATIONS} under the current approved plan."
        ),
    ]
    if task.mode == "revision":
        parts.extend(
            [
                "",
                "# Atlas Review Corrections",
                atlas_review or "",
                "",
                (
                    "Address the Atlas review findings only and preserve "
                    "unrelated working behavior."
                ),
            ]
        )
    return os.linesep.join(parts)


def run_codex(prompt: str, worktree: Path, output_path: Path) -> None:
    temp_dir = worktree / ".codex-tmp"
    temp_dir.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
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
            raise RuntimeError(f"Codex exited with code {return_code}.")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def run_tests(worktree: Path) -> None:
    env = os.environ.copy()
    env["PYTHONPATH"] = "src"
    completed = run_command(
        ["python", "-m", "pytest", "-q"],
        cwd=worktree,
        env=env,
        check=False,
    )
    if completed.stdout:
        print(completed.stdout, end="")
    if completed.stderr:
        print(completed.stderr, end="")
    if completed.returncode != 0:
        raise RuntimeError(
            f"Automated tests failed with exit code {completed.returncode}. "
            "Changes were not committed, pushed, or opened as a PR."
        )


def create_pull_request(
    repo: str, task: Task, worktree: Worktree, iteration: int
) -> str:
    issue = task.issue
    body = (
        f"Implements OrbitFlow-Evo issue #{issue['number']}.{os.linesep}{os.linesep}"
        "Generated by the local ChatGPT-authenticated Codex CLI orchestration."
        f"{os.linesep}{os.linesep}"
        f"Iteration: {iteration}/{MAX_ITERATIONS}{os.linesep}"
        f"Automated tests: passed{os.linesep}{os.linesep}"
        "Atlas review and explicit human merge approval are required."
    )
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            suffix=".md",
            prefix=f"orbitflow-codex-pr-{issue['number']}-",
            delete=False,
        ) as handle:
            handle.write(body)
            temp_path = Path(handle.name)
        return gh(
            [
                "pr",
                "create",
                "--repo",
                repo,
                "--head",
                worktree.branch,
                "--base",
                "main",
                "--title",
                f"Codex: #{issue['number']} {issue['title']}",
                "--body-file",
                str(temp_path),
            ]
        ).strip()
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)


def existing_pull_request(repo: str, branch: str) -> str:
    payload = json.loads(
        gh(["pr", "view", branch, "--repo", repo, "--json", "url"])
    )
    return payload["url"]


def truncated_output(path: Path) -> str:
    if not path.exists():
        return ""
    content = path.read_text(encoding="utf-8")
    if len(content) <= OUTPUT_LIMIT:
        return content.rstrip()
    return (
        "[output truncated to last 6000 characters]"
        + os.linesep
        + content[-OUTPUT_LIMIT:].rstrip()
    )


def handle_iteration_limit(repo: str, issue_number: int) -> None:
    set_issue_labels(
        repo,
        issue_number,
        add=("codex-replan-required",),
        remove=("codex-revise", "codex-running", "codex-review"),
    )
    add_issue_comment(
        repo,
        issue_number,
        (
            "The current implementation plan has reached the 15-iteration limit. "
            "Automated Codex revision is stopped. Atlas and the user must revisit "
            "and approve the implementation plan before a new cycle begins."
        ),
    )
    print(f"Issue #{issue_number} reached the 15-iteration limit.")


def process_task(
    repo: str,
    task: Task,
    *,
    dry_run: bool = False,
) -> None:
    issue_number = int(task.issue["number"])
    repo_root = repository_root()
    verify_repository(repo, repo_root)
    state = get_iteration_state(repo, issue_number)

    if task.mode == "revision" and state.iteration >= MAX_ITERATIONS:
        if dry_run:
            print(
                f"DRY RUN: issue #{issue_number} would move to "
                "codex-replan-required."
            )
            return
        handle_iteration_limit(repo, issue_number)
        return

    iteration = determine_iteration(task, state)
    planned = planned_worktree(issue_number, repo_root)

    preamble_source = (
        repo_root / "scripts" / "orchestration" / "task-preamble.md"
        if dry_run
        else None
    )
    if dry_run:
        preamble = preamble_source.read_text(encoding="utf-8")
        prompt = build_prompt(preamble, task, iteration, state.atlas_review)
        print()
        print(
            f"DRY RUN: issue #{issue_number}, mode={task.mode}, "
            f"iteration={iteration}"
        )
        print(f"Branch: {planned.branch}")
        print(f"Worktree: {planned.path}")
        print("No branch, worktree, labels, comments, commits, pushes, or PRs were changed.")
        print("--------------------------------")
        print(prompt)
        print("--------------------------------")
        return

    worktree = ensure_worktree(issue_number, task.mode, repo_root)
    preamble_path = worktree.path / "scripts" / "orchestration" / "task-preamble.md"
    preamble = preamble_path.read_text(encoding="utf-8")
    prompt = build_prompt(preamble, task, iteration, state.atlas_review)

    set_issue_labels(
        repo,
        issue_number,
        add=("codex-running",),
        remove=("codex-task", "codex-revise", "codex-review", "codex-failed"),
    )

    output_path = Path(tempfile.gettempdir()) / f"orbitflow-codex-output-{issue_number}.txt"
    output_path.unlink(missing_ok=True)
    try:
        print(
            f"Starting local Codex CLI for issue #{issue_number} "
            f"(iteration {iteration}/{MAX_ITERATIONS})..."
        )
        run_codex(prompt, worktree.path, output_path)

        if not git(["status", "--porcelain"], worktree.path):
            raise RuntimeError("Codex completed without repository changes.")

        run_tests(worktree.path)

        git(["add", "-A"], worktree.path)
        git(
            [
                "commit",
                "-m",
                f"Codex: issue #{issue_number} iteration {iteration}",
            ],
            worktree.path,
        )
        git(
            ["push", "--set-upstream", "origin", worktree.branch],
            worktree.path,
        )

        if task.mode == "initial":
            pr_url = create_pull_request(repo, task, worktree, iteration)
        else:
            pr_url = existing_pull_request(repo, worktree.branch)

        comment = (
            f"<!-- orbitflow-codex-iteration:{iteration} -->{os.linesep}"
            f"Codex iteration {iteration}/{MAX_ITERATIONS} is ready for Atlas review."
            f"{os.linesep}{os.linesep}"
            f"PR: {pr_url}{os.linesep}"
            f"Automated tests: passed{os.linesep}{os.linesep}"
            f"Codex output:{os.linesep}{truncated_output(output_path)}"
        )
        add_issue_comment(repo, issue_number, comment)
        set_issue_labels(
            repo,
            issue_number,
            add=("codex-review", "codex-pr"),
            remove=("codex-running", "codex-failed"),
        )
        print(f"Issue #{issue_number} moved to codex-review.")
        print(f"PR: {pr_url}")
    finally:
        output_path.unlink(missing_ok=True)


def process_one(repo: str, *, dry_run: bool = False) -> bool:
    task = get_next_task(repo)
    if task is None:
        print("No codex-task or codex-revise issue is waiting.")
        return False

    try:
        process_task(repo, task, dry_run=dry_run)
    except Exception as exc:
        if dry_run:
            raise
        issue_number = int(task.issue["number"])
        print(f"Local Codex orchestration failed: {exc}")
        try:
            set_issue_labels(
                repo,
                issue_number,
                add=("codex-failed",),
                remove=("codex-task", "codex-revise", "codex-running"),
            )
            add_issue_comment(
                repo,
                issue_number,
                f"Local Codex orchestration failed: {exc}",
            )
        except Exception as update_exc:
            print(f"Warning: failed to update GitHub failure state: {update_exc}")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", default=DEFAULT_REPO)
    parser.add_argument("--watch", action="store_true")
    parser.add_argument("--poll-seconds", type=int, default=20)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.poll_seconds < MIN_POLL_SECONDS:
        raise SystemExit(
            f"--poll-seconds must be at least {MIN_POLL_SECONDS}."
        )

    ensure_executable("git")
    ensure_executable("gh")
    ensure_executable("codex")

    while True:
        processed = process_one(args.repo, dry_run=args.dry_run)
        if not args.watch:
            break
        if not processed:
            time.sleep(args.poll_seconds)


if __name__ == "__main__":
    main()
