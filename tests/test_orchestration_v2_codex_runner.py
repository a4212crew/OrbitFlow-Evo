from pathlib import Path
import os
import sys
import tempfile

import pytest

ORCH = Path(__file__).parents[1] / "scripts" / "orchestration_v2"
sys.path.insert(0, str(ORCH))

import codex_runner  # noqa: E402
from models import FailureCategory, OrchestrationError, Task  # noqa: E402


def test_prompt_keeps_git_github_mechanics_out_of_codex():
    task = Task("initial", 42, "Smoke test", "Change one documentation line.", "https://example.test/42")

    prompt = codex_runner.build_prompt("PREAMBLE", task)

    assert "Issue #42: Smoke test" in prompt
    assert "Do not commit, push" in prompt
    assert "Change one documentation line." in prompt


def test_run_codex_uses_workspace_write_and_strips_api_key(monkeypatch, tmp_path):
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    output_path = tmp_path / "codex-output.txt"
    captured = {}
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-reach-codex")

    class FakeStdout:
        def __iter__(self):
            return iter(["done\n"])

    class FakeProcess:
        stdout = FakeStdout()

        def wait(self):
            return 0

    def fake_popen(args, **kwargs):
        captured["args"] = args
        captured["env"] = kwargs["env"]
        captured["cwd"] = kwargs["cwd"]
        return FakeProcess()

    monkeypatch.setattr(codex_runner.subprocess, "Popen", fake_popen)

    codex_runner.run_codex("prompt", worktree, output_path)

    assert captured["args"] == ["codex", "exec", "--sandbox", "workspace-write", "prompt"]
    assert captured["cwd"] == worktree
    assert "OPENAI_API_KEY" not in captured["env"]
    temp = Path(captured["env"]["TEMP"])
    assert temp.parent == Path(tempfile.gettempdir()).resolve()
    assert worktree not in temp.parents
    assert captured["env"]["TMP"] == captured["env"]["TMPDIR"] == str(temp)
    assert not temp.exists()
    assert list(worktree.iterdir()) == []
    assert output_path.read_text(encoding="utf-8") == "done\n"


def test_run_tests_classifies_failure(monkeypatch, tmp_path):
    class Completed:
        returncode = 1
        stdout = "1 failed\n"
        stderr = ""

    monkeypatch.setattr(codex_runner.subprocess, "run", lambda *_args, **_kwargs: Completed())

    with pytest.raises(OrchestrationError) as error:
        codex_runner.run_tests(tmp_path)

    assert error.value.category is FailureCategory.TEST
    assert "remain uncommitted" in str(error.value)


@pytest.mark.parametrize("returncode", [0, 1])
def test_pytest_uses_external_basetemp_and_cleans_on_exit(monkeypatch, tmp_path, returncode):
    from types import SimpleNamespace
    captured = {}
    def run(args, **kwargs):
        temp = Path(kwargs['env']['TEMP'])
        assert temp.is_dir() and tmp_path not in temp.parents
        assert kwargs['env']['TMP'] == kwargs['env']['TMPDIR'] == str(temp)
        assert Path(args[args.index('--basetemp') + 1]) == temp / 'pytest'
        (temp / 'artifact').write_text('temporary')
        captured['temp'] = temp
        return SimpleNamespace(returncode=returncode, stdout='', stderr='')
    monkeypatch.setattr(codex_runner.subprocess, 'run', run)
    if returncode:
        with pytest.raises(OrchestrationError):
            codex_runner.run_tests(tmp_path)
    else:
        codex_runner.run_tests(tmp_path)
    assert not captured['temp'].exists()
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize('fails', [False, True])
def test_cleanup_warning_does_not_mask_test_result(monkeypatch, tmp_path, capsys, fails):
    import temp_cleanup
    original = temp_cleanup.cleanup_temp
    retained = []
    def fail_cleanup(path):
        retained.append(path)
        raise OrchestrationError(FailureCategory.CONTROLLER, f'cleanup failed at {path}: denied')
    def tests(*args):
        if fails:
            raise OrchestrationError(FailureCategory.TEST, 'test failure')
    monkeypatch.setattr(temp_cleanup, 'cleanup_temp', fail_cleanup)
    monkeypatch.setattr(codex_runner, '_run_tests', tests)
    try:
        if fails:
            with pytest.raises(OrchestrationError) as error:
                codex_runner.run_tests(tmp_path)
            assert error.value.category is FailureCategory.TEST
        else:
            codex_runner.run_tests(tmp_path)
        assert str(retained[0]) in capsys.readouterr().err
        assert list(tmp_path.iterdir()) == []
    finally:
        for path in retained:
            original(path)


def test_codex_launch_failure_cleans_external_temp(monkeypatch, tmp_path):
    captured = []
    def fail(args, **kwargs):
        captured.append(Path(kwargs['env']['TEMP']))
        raise OSError('launch failed')
    monkeypatch.setattr(codex_runner.subprocess, 'Popen', fail)
    with pytest.raises(OSError, match='launch failed'):
        codex_runner.run_codex('prompt', tmp_path, tmp_path / 'output.txt')
    assert not captured[0].exists()
