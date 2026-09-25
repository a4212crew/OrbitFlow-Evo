import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).parents[1] / 'scripts' / 'orchestration_v2'))
import github_ops
import temp_cleanup
from models import Task, OrchestrationError


@pytest.mark.parametrize('revision_available', [True, False])
def test_discovery_prioritizes_revision_and_excludes_blocked_states(monkeypatch, tmp_path, revision_available):
    calls = []
    def gh(args, **kwargs):
        label = args[args.index('--label') + 1]
        calls.append(label)
        query = args[args.index('--search') + 1]
        for state in ('codex-review', 'codex-approved', 'codex-failed',
                      'codex-replan-required', 'codex-running', 'codex-pr'):
            assert f'-label:{state}' in query.split()
        if label == 'codex-revise' and not revision_available:
            return '[]'
        return json.dumps([{'number': 1, 'title': 'Task', 'body': 'Contract', 'url': ''}])
    monkeypatch.setattr(github_ops, 'gh', gh)
    task = github_ops.get_next_task('owner/repo', tmp_path)
    assert task.mode == ('revision' if revision_available else 'initial')
    assert calls == (['codex-revise'] if revision_available else ['codex-revise', 'codex-task'])


@pytest.mark.parametrize('count', [10, 11])
def test_exhausted_plan_does_not_require_another_review(monkeypatch, tmp_path, count):
    pages = [[{'user': {'login': 'owner'}, 'body': f'<!-- orbitflow-codex-iteration:{count} -->'}]]
    monkeypatch.setattr(github_ops, 'gh', lambda *a, **kw: json.dumps(pages))
    assert github_ops.review_context('owner/repo', Task('revision', 1, '', '', ''), tmp_path) == (count, '')


def test_review_uses_latest_owner_comment_and_paginated_iterations(monkeypatch, tmp_path):
    def entry(author, body, number):
        return {'user': {'login': author}, 'body': body, 'created_at': str(number), 'id': number}
    pages = [[entry('owner', '<!-- orbitflow-codex-iteration:2 -->', 1),
              entry('owner', '<!-- atlas-review --> older', 2)],
             [entry('OWNER', '<!-- atlas-review --> latest', 3),
              entry('outsider', '<!-- atlas-review --> untrusted <!-- orbitflow-codex-iteration:10 -->', 4)]]
    monkeypatch.setattr(github_ops, 'gh', lambda *args, **kwargs: json.dumps(pages))
    count, review = github_ops.review_context('owner/repo', Task('revision', 1, '', '', ''), tmp_path)
    assert count == 2 and review.endswith('latest')


def test_revision_without_owner_review_fails(monkeypatch, tmp_path):
    monkeypatch.setattr(github_ops, 'gh', lambda *args, **kwargs: '[[]]')
    with pytest.raises(OrchestrationError, match='owner-authored'):
        github_ops.review_context('owner/repo', Task('revision', 1, '', '', ''), tmp_path)


@pytest.mark.parametrize('present', [[], ['codex-task'], ['codex-revise'],
                                    ['codex-pr'], list(github_ops.STATE_LABELS)])
@pytest.mark.parametrize('state', ['codex-running', 'codex-pr', 'codex-review', 'codex-failed'])
def test_transition_removes_only_present_state_labels(monkeypatch, tmp_path, present, state):
    calls = []
    labels = set(present) | {'unrelated'}
    def gh(args, **kwargs):
        calls.append(args)
        if args[:2] == ['issue', 'view']:
            return json.dumps({'labels': [{'name': name} for name in labels]})
        assert args[:2] == ['issue', 'edit']
        for index, arg in enumerate(args):
            if arg == '--remove-label':
                labels.remove(args[index + 1])  # Fails if an absent label is removed.
        labels.add(args[args.index('--add-label') + 1])
        return ''
    monkeypatch.setattr(github_ops, 'gh', gh)
    github_ops.transition('owner/repo', Task('initial', 1, '', '', ''), state, tmp_path)
    assert len(calls) == 2
    assert labels == {'unrelated', state}


def test_state_taxonomy_includes_pr():
    assert 'codex-pr' in github_ops.STATE_LABELS


@pytest.mark.parametrize('existing', ['', 'existing-pr'])
def test_pr_create_or_update_uses_body_file(monkeypatch, tmp_path, existing):
    calls = []
    def gh(args, **kwargs):
        calls.append(args)
        assert 'full deterministic pytest suite passed' in Path(args[args.index('--body-file') + 1]).read_text()
        return 'new-pr'
    monkeypatch.setattr(github_ops, 'gh', gh)
    result = github_ops.publish_pr('owner/repo', Task('initial', 1, 'Title', '', ''), 'codex/issue-1', tmp_path, existing)
    assert calls[0][:2] == ['pr', 'edit' if existing else 'create']
    assert result == (existing or 'new-pr')


def test_cleanup_removes_only_temp_tree(tmp_path):
    target = tmp_path / 'orbitflow-issue-14-test'
    target.mkdir()
    (target / 'artifact').write_text('temporary')
    preserved = tmp_path / 'keep'
    preserved.write_text('keep')
    temp_cleanup.cleanup_temp(target)
    assert not target.exists() and preserved.read_text() == 'keep'


def test_cleanup_failure_is_not_hidden(monkeypatch, tmp_path):
    target = tmp_path / 'orbitflow-issue-14-test'
    target.mkdir()
    monkeypatch.setattr(Path, 'rmdir', lambda *_: (_ for _ in ()).throw(OSError('locked')))
    monkeypatch.setattr(temp_cleanup.time, 'sleep', lambda *_: None)
    with pytest.raises(OrchestrationError, match='cleanup failed'):
        temp_cleanup.cleanup_temp(target)


def test_cleanup_refuses_reparse_point(monkeypatch, tmp_path):
    from types import SimpleNamespace
    target = tmp_path / 'orbitflow-issue-14-test'
    target.mkdir()
    original = Path.lstat
    monkeypatch.setattr(Path, 'lstat', lambda path: SimpleNamespace(st_mode=0, st_file_attributes=0x400)
                        if path == target else original(path))
    monkeypatch.setattr(temp_cleanup.time, 'sleep', lambda *_: None)
    with pytest.raises(OrchestrationError, match='reparse point'):
        temp_cleanup.cleanup_temp(target)


def test_cleanup_retries_transient_lock(monkeypatch, tmp_path):
    target = tmp_path / 'orbitflow-issue-14-test'
    target.mkdir()
    original = Path.rmdir
    attempts = []
    def locked_once(path):
        attempts.append(path)
        if len(attempts) == 1:
            raise OSError('sharing violation')
        original(path)
    monkeypatch.setattr(Path, 'rmdir', locked_once)
    monkeypatch.setattr(temp_cleanup.time, 'sleep', lambda *_: None)
    temp_cleanup.cleanup_temp(target)
    assert len(attempts) == 2 and not target.exists()


@pytest.mark.parametrize('inside', [True, False])
def test_temp_rejects_git_local_os_temp(monkeypatch, tmp_path, inside):
    worktree = tmp_path / 'worktree'
    worktree.mkdir()
    root = worktree / 'temp' if inside else tmp_path / 'other-checkout' / 'temp'
    root.mkdir(parents=True)
    if not inside:
        (root.parent / '.git').mkdir()
    monkeypatch.setattr(temp_cleanup.tempfile, 'gettempdir', lambda: str(root))
    with pytest.raises(OrchestrationError, match='outside Git worktrees'):
        with temp_cleanup.controller_temp(worktree, 'test'):
            pytest.fail('must reject before execution')
    assert list(root.iterdir()) == []


def test_temp_is_unique_per_task_and_execution(tmp_path):
    with temp_cleanup.controller_temp(tmp_path / 'issue-14', 'test') as first:
        with temp_cleanup.controller_temp(tmp_path / 'issue-14', 'test') as second:
            assert first != second
            assert first.name.startswith('orbitflow-issue-14-test-')
            assert first.parent == Path(temp_cleanup.tempfile.gettempdir()).resolve()
    assert not first.exists() and not second.exists()
