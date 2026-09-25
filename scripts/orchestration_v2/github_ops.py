"""GitHub discovery and controller-owned review lifecycle for orchestration v2."""

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

STATE_LABELS = ('codex-task', 'codex-revise', 'codex-running', 'codex-pr', 'codex-review',
                'codex-approved', 'codex-failed', 'codex-replan-required')


def transition(repo: str, task: Task, state: str, cwd: Path) -> None:
    issue = json.loads(gh(['issue', 'view', str(task.number), '--repo', repo,
                          '--json', 'labels'], cwd=cwd))
    present = {label['name'] for label in issue['labels']}
    args = ['issue', 'edit', str(task.number), '--repo', repo, '--add-label', state]
    for label in STATE_LABELS:
        if label != state and label in present:
            args.extend(['--remove-label', label])
    gh(args, cwd=cwd)


def comment(repo: str, task: Task, body: str, cwd: Path) -> None:
    import tempfile
    with tempfile.TemporaryDirectory(prefix='orbitflow-comment-') as directory:
        path = Path(directory) / 'body.md'
        path.write_text(body, encoding='utf-8')
        gh(['issue', 'comment', str(task.number), '--repo', repo,
            '--body-file', str(path)], cwd=cwd)


def review_context(repo: str, task: Task, cwd: Path) -> tuple[int, str]:
    import re
    pages = json.loads(gh(['api', '--paginate', '--slurp',
                          f'repos/{repo}/issues/{task.number}/comments'], cwd=cwd))
    comments = [item for page in pages for item in page]
    owner = repo.split('/')[0].casefold()
    trusted = [c for c in comments if c.get('user', {}).get('login', '').casefold() == owner]
    count = max((int(n) for c in trusted for n in
                 re.findall(r'<!-- orbitflow-codex-iteration:(\d+) -->', c['body'])), default=0)
    reviews = [c for c in trusted if '<!-- atlas-review -->' in c['body']]
    review = max(reviews, key=lambda c: (c['created_at'], c['id']))['body'] if reviews else ''
    if task.mode == 'revision' and count < 15 and not review:
        raise OrchestrationError(FailureCategory.PREREQUISITE,
                                 'Revision requires an owner-authored <!-- atlas-review --> comment.')
    return count, review


def find_pr(repo: str, branch: str, cwd: Path) -> str:
    prs = json.loads(gh(['pr', 'list', '--repo', repo, '--head', branch,
                        '--base', 'main', '--state', 'open', '--json', 'url'], cwd=cwd))
    if len(prs) > 1:
        raise OrchestrationError(FailureCategory.CONTROLLER, 'Multiple open task PRs.')
    return prs[0]['url'] if prs else ''


def publish_pr(repo: str, task: Task, branch: str, cwd: Path, existing: str) -> str:
    import tempfile
    with tempfile.TemporaryDirectory(prefix='orbitflow-pr-') as directory:
        path = Path(directory) / 'body.md'
        path.write_text(f'Implements #{task.number}: {task.title}\n\n'
                        'Validation: full deterministic pytest suite passed.\n'
                        'Awaiting Atlas review and explicit user merge approval.\n', encoding='utf-8')
        if existing:
            gh(['pr', 'edit', existing, '--repo', repo, '--body-file', str(path)], cwd=cwd)
            return existing
        return gh(['pr', 'create', '--repo', repo, '--head', branch, '--base', 'main',
                   '--title', f'Issue #{task.number}: {task.title}', '--body-file', str(path)], cwd=cwd)
