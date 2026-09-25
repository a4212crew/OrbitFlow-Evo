from pathlib import Path
import sys
import pytest

ORCH = Path(__file__).parents[1] / "scripts" / "orchestration_v2"
sys.path.insert(0, str(ORCH))

import controller  # noqa: E402
from models import FailureCategory, OrchestrationError, PreflightReport, Task, Workspace  # noqa: E402


def test_dry_run_is_non_mutating(monkeypatch, tmp_path, capsys):
    repo_root = tmp_path / "OrbitFlow-Evo"
    repo_root.mkdir()
    report = PreflightReport(
        repo_root=repo_root,
        git_name="Atlas",
        git_email="atlas@example.test",
        codex_version="codex-cli test",
        codex_auth_status="Logged in using ChatGPT",
    )
    task = Task("initial", 42, "Smoke test", "Edit docs only.", "https://example.test/42")
    workspace = Workspace("codex/issue-42", tmp_path / "OrbitFlow-Evo-worktrees" / "issue-42")

    monkeypatch.setattr(controller, "run_preflight", lambda _repo: report)
    monkeypatch.setattr(controller, "get_next_task", lambda *_args: task)
    monkeypatch.setattr(controller, "validate_workspace", lambda *_args: workspace)
    monkeypatch.setattr(controller, "review_context", lambda *_args: (0, ""))
    monkeypatch.setattr(controller, "find_pr", lambda *_args: "")

    def forbidden(*_args, **_kwargs):
        raise AssertionError("dry-run must not mutate or invoke Codex")

    monkeypatch.setattr(controller, "controller_temp", forbidden)
    monkeypatch.setattr(controller, "prepare_workspace", forbidden)
    monkeypatch.setattr(controller, "run_codex", forbidden)
    monkeypatch.setattr(controller, "run_tests", forbidden)

    assert controller.process_one("a4212crew/OrbitFlow-Evo", dry_run=True) is True

    rendered = capsys.readouterr().out
    assert "DRY RUN" in rendered
    assert "codex/issue-42" in rendered


@pytest.mark.parametrize('failure_stage', [None, 'codex', 'tests', 'commit/push', 'pr', 'codex-pr', 'marker', 'codex-review'])
@pytest.mark.parametrize('watch', [False, True])
def test_lifecycle_after_tests(monkeypatch, tmp_path, capsys, failure_stage, watch):
    repo_root = tmp_path / "OrbitFlow-Evo"
    worktree = tmp_path / "OrbitFlow-Evo-worktrees" / "issue-42"
    preamble_dir = worktree / "scripts" / "orchestration_v2"
    preamble_dir.mkdir(parents=True)
    (preamble_dir / "task-preamble.md").write_text("PREAMBLE", encoding="utf-8")
    report = PreflightReport(repo_root, "Atlas", "atlas@example.test", "codex-cli test", "Logged in using ChatGPT")
    task = Task("initial", 42, "Smoke test", "Edit docs only.", "https://example.test/42")
    workspace = Workspace("codex/issue-42", worktree)
    calls = []

    monkeypatch.setattr(controller, "run_preflight", lambda _repo: report)
    monkeypatch.setattr(controller, "get_next_task", lambda *_args: task)
    monkeypatch.setattr(controller, "validate_workspace", lambda *_args: workspace)
    monkeypatch.setattr(controller, "review_context", lambda *_args: (0, ""))
    monkeypatch.setattr(controller, "find_pr", lambda *_args: "")
    monkeypatch.setattr(controller, "prepare_workspace", lambda *_args: workspace)
    monkeypatch.setattr(controller, "run_codex", lambda *_args: record("codex"))
    monkeypatch.setattr(controller, "ensure_repository_changes", lambda *_args: calls.append("changes"))
    monkeypatch.setattr(controller, "run_tests", lambda *_args: record("tests"))

    def record(event):
        calls.append(event)
        if event == failure_stage:
            raise OrchestrationError(FailureCategory.CONTROLLER, 'simulated publishing failure')
    monkeypatch.setattr(controller, "transition", lambda *args: record(args[2]))
    monkeypatch.setattr(controller, "comment", lambda *args: record(
        "marker" if 'orbitflow-codex-iteration:' in args[2] else "failure comment"))
    monkeypatch.setattr(controller, "commit_and_push", lambda *_args: record("commit/push"))
    monkeypatch.setattr(controller, "publish_pr", lambda *_args: record("pr") or "url")

    lifecycle = ["codex-running", "codex", "changes", "tests", "commit/push", "pr", "codex-pr", "marker", "codex-review"]
    if watch:
        monkeypatch.setattr(sys, 'argv', ['controller', '--watch'])
        def sleep(seconds):
            assert not failure_stage, 'failure must not return to polling'
            assert calls[-1] == 'codex-review'
            if calls.count('codex-review') == 2:
                raise KeyboardInterrupt
        monkeypatch.setattr(controller.time, 'sleep', sleep)
        if failure_stage:
            with pytest.raises(SystemExit) as error:
                controller.main()
            assert error.value.code == 1
            assert calls == lifecycle[:lifecycle.index(failure_stage) + 1] + ['codex-failed', 'failure comment']
        else:
            controller.main()
            assert calls == lifecycle * 2
        return
    if failure_stage:
        with pytest.raises(OrchestrationError, match='simulated publishing failure'):
            controller.process_one("a4212crew/OrbitFlow-Evo")
        assert calls == lifecycle[:lifecycle.index(failure_stage) + 1] + ['codex-failed', 'failure comment']
        return
    assert controller.process_one("a4212crew/OrbitFlow-Evo") is True

    assert calls == lifecycle
    assert "ready for review" in capsys.readouterr().out

@pytest.mark.parametrize('category', list(FailureCategory))
def test_failure_does_not_publish(monkeypatch, tmp_path, category):
    report = PreflightReport(tmp_path, 'A', 'a@example.test', 'v', 'ChatGPT')
    task = Task('initial', 1, 'Title', 'Body', '')
    monkeypatch.setattr(controller, 'run_preflight', lambda *_: report)
    monkeypatch.setattr(controller, 'get_next_task', lambda *_: task)
    monkeypatch.setattr(controller, 'review_context', lambda *_: (0, ''))
    monkeypatch.setattr(controller, 'validate_workspace', lambda *_: Workspace('codex/issue-1', tmp_path))
    monkeypatch.setattr(controller, 'find_pr', lambda *_: '')
    states = []
    monkeypatch.setattr(controller, 'transition', lambda *args: states.append(args[2]))
    monkeypatch.setattr(controller, 'comment', lambda *_: None)
    def fail(*_):
        raise OrchestrationError(category, 'simulated failure')
    monkeypatch.setattr(controller, 'prepare_workspace', fail)
    monkeypatch.setattr(controller, 'commit_and_push', lambda *_: pytest.fail('must not publish'))
    with pytest.raises(OrchestrationError) as error:
        controller.process_one('owner/repo')
    assert error.value.category == category
    assert states[-1] == 'codex-failed'


def test_iteration_10_stops_before_workspace_or_worker(monkeypatch, tmp_path):
    monkeypatch.setattr(controller, 'run_preflight', lambda *_: PreflightReport(tmp_path, 'A', 'a@b', 'v', 'ChatGPT'))
    monkeypatch.setattr(controller, 'get_next_task', lambda *_: Task('revision', 1, 'T', 'B', ''))
    monkeypatch.setattr(controller, 'review_context', lambda *_: (10, 'correction'))
    monkeypatch.setattr(controller, 'validate_workspace', lambda *_: pytest.fail('no workspace at limit'))
    states = []
    monkeypatch.setattr(controller, 'transition', lambda *args: states.append(args[2]))
    monkeypatch.setattr(controller, 'comment', lambda *_: None)
    assert controller.process_one('owner/repo')
    assert states == ['codex-replan-required']


@pytest.mark.parametrize('test_failure', [False, True])
def test_revision_reuses_workspace_pr_and_full_test_gate(monkeypatch, tmp_path, test_failure):
    preamble = tmp_path / 'scripts' / 'orchestration_v2' / 'task-preamble.md'
    preamble.parent.mkdir(parents=True)
    preamble.write_text('preamble')
    task = Task('revision', 13, 'Smoke', 'original contract', '')
    workspace = Workspace('codex/issue-13', tmp_path)
    monkeypatch.setattr(controller, 'run_preflight', lambda *_: PreflightReport(tmp_path, 'A', 'a@b', 'v', 'ChatGPT'))
    monkeypatch.setattr(controller, 'get_next_task', lambda *_: task)
    monkeypatch.setattr(controller, 'review_context', lambda *_: (9, 'only fix requested line'))
    monkeypatch.setattr(controller, 'validate_workspace', lambda *_: workspace)
    monkeypatch.setattr(controller, 'prepare_workspace', lambda *_: workspace)
    monkeypatch.setattr(controller, 'find_pr', lambda *_: 'existing-pr')
    events = []
    monkeypatch.setattr(controller, 'transition', lambda *args: events.append(args[2]))
    monkeypatch.setattr(controller, 'comment', lambda *args: events.append(args[2]))
    def worker(prompt, path, output):
        assert 'only fix requested line' in prompt
        assert path == workspace.path
        events.append('worker')
    monkeypatch.setattr(controller, 'run_codex', worker)
    monkeypatch.setattr(controller, 'ensure_repository_changes', lambda *_: None)
    def tests(path):
        events.append('full pytest')
        if test_failure:
            raise OrchestrationError(FailureCategory.TEST, 'failed')
    monkeypatch.setattr(controller, 'run_tests', tests)
    def commit(ws, report, selected, iteration):
        assert ws == workspace and selected == task and iteration == 10
        events.append('commit/push')
    monkeypatch.setattr(controller, 'commit_and_push', commit)
    def pr(repo, selected, branch, cwd, existing):
        assert existing == 'existing-pr' and branch == workspace.branch
        events.append('pr update')
        return existing
    monkeypatch.setattr(controller, 'publish_pr', pr)
    if test_failure:
        with pytest.raises(OrchestrationError):
            controller.process_one('owner/repo')
        assert 'commit/push' not in events and 'pr update' not in events
        assert not any('orbitflow-codex-iteration:' in e for e in events)
        assert 'codex-failed' in events
    else:
        controller.process_one('owner/repo')
        assert events[:5] == ['codex-running', 'worker', 'full pytest', 'commit/push', 'pr update']
        assert events[5] == 'codex-pr'
        assert 'orbitflow-codex-iteration:10' in events[6]
        assert events[7:] == ['codex-review']


@pytest.fixture(autouse=True)
def fake_head(monkeypatch):
    from types import SimpleNamespace
    monkeypatch.setattr(controller, 'git', lambda *args, **kwargs: SimpleNamespace(stdout='head'))


@pytest.mark.parametrize('options, interval', [([], 15), (['--poll-seconds', '5'], 5)])
@pytest.mark.parametrize('dry_run', [False, True])
def test_watch_idle_and_repeat_processing(monkeypatch, options, interval, dry_run, capsys):
    monkeypatch.setattr(sys, 'argv', ['controller', '--watch', *options,
                                    *(['--dry-run'] if dry_run else [])])
    results = iter([False, True, True, False])
    events = []
    def process(repo, **kwargs):
        assert kwargs == {'dry_run': dry_run}
        events.append(next(results))
    def sleep(seconds):
        assert seconds == interval
        if len(events) == 4:
            raise KeyboardInterrupt
    monkeypatch.setattr(controller, 'process_one', process)
    monkeypatch.setattr(controller.time, 'sleep', sleep)
    controller.main()
    assert events == [False, True, True, False]
    assert 'stopped by operator' in capsys.readouterr().out


@pytest.mark.parametrize('error', [OrchestrationError(c, 'failure') for c in FailureCategory]
                         + [RuntimeError('unexpected failure')])
def test_watch_stops_on_failure_without_retry(monkeypatch, error):
    monkeypatch.setattr(sys, 'argv', ['controller', '--watch'])
    calls = []
    def fail(*args, **kwargs):
        calls.append(1)
        raise error
    monkeypatch.setattr(controller, 'process_one', fail)
    monkeypatch.setattr(controller.time, 'sleep', lambda *_: pytest.fail('must not retry'))
    with pytest.raises(SystemExit) as result:
        controller.main()
    assert result.value.code == 1 and calls == [1]


@pytest.mark.parametrize('value', ['4', '0', '-1', 'abc', '5.5'])
def test_poll_interval_rejects_invalid_values(monkeypatch, value):
    monkeypatch.setattr(sys, 'argv', ['controller', '--watch', '--poll-seconds', value])
    monkeypatch.setattr(controller, 'process_one', lambda *_: pytest.fail('invalid arguments'))
    with pytest.raises(SystemExit) as result:
        controller.main()
    assert result.value.code == 2


def test_interrupt_during_processing_is_clean(monkeypatch, capsys):
    monkeypatch.setattr(sys, 'argv', ['controller', '--watch'])
    def interrupt(*args, **kwargs):
        raise KeyboardInterrupt
    monkeypatch.setattr(controller, 'process_one', interrupt)
    controller.main()
    assert 'stopped by operator' in capsys.readouterr().out


def test_one_shot_does_not_poll(monkeypatch):
    monkeypatch.setattr(sys, 'argv', ['controller'])
    calls = []
    monkeypatch.setattr(controller, 'process_one', lambda *a, **kw: calls.append(kw))
    monkeypatch.setattr(controller.time, 'sleep', lambda *_: pytest.fail('one shot'))
    controller.main()
    assert calls == [{'dry_run': False}]


def test_global_preflight_failure_stops_before_selection(monkeypatch):
    def fail(*_):
        raise OrchestrationError(FailureCategory.PREREQUISITE, 'preflight failed')
    monkeypatch.setattr(controller, 'run_preflight', fail)
    monkeypatch.setattr(controller, 'get_next_task', lambda *_: pytest.fail('no selection'))
    with pytest.raises(OrchestrationError, match='preflight failed'):
        controller.process_one('owner/repo')
