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


def test_prompt_includes_explicit_required_context_manifest():
    task = Task(
        "initial",
        43,
        "Reporting change",
        "## Required repository context\n"
        "- `.agents/skills/device-reporting/SKILL.md`\n"
        "- `.agents/skills/runtime-logging/SKILL.md`\n\n"
        "## Notes\n"
        "Do not load `.agents/skills/codex-orchestration/SKILL.md` for this feature task.",
        "https://example.test/43",
    )

    prompt = codex_runner.build_prompt("PREAMBLE", task)

    manifest = prompt.split("# GitHub Task", 1)[0]
    assert "# Required repository context" in manifest
    assert "- `AGENTS.md`" in manifest
    assert "- `.agents/skills/device-reporting/SKILL.md`" in manifest
    assert "- `.agents/skills/runtime-logging/SKILL.md`" in manifest
    assert "- `.agents/skills/codex-orchestration/SKILL.md`" not in manifest


def test_required_context_deduplicates_paths_and_has_safe_fallback():
    declared = Task(
        "initial",
        44,
        "Inventory",
        "Use `.agents/skills/device-inventory/SKILL.md` and again "
        "`.agents/skills/device-inventory/SKILL.md`.",
        "",
    )
    assert codex_runner.required_context(declared) == [
        "AGENTS.md",
        ".agents/skills/device-inventory/SKILL.md",
    ]

    fallback = Task("initial", 45, "Docs", "Change one documentation line.", "")
    prompt = codex_runner.build_prompt("PREAMBLE", fallback)
    assert codex_runner.required_context(fallback) == ["AGENTS.md"]
    assert "use the AGENTS.md routing table to select only the directly relevant skill(s)" in prompt


def test_revision_prompt_keeps_context_manifest_before_task_and_review():
    task = Task(
        "revision",
        46,
        "Logging",
        "Follow `.agents/skills/runtime-logging/SKILL.md`.",
        "",
    )
    prompt = codex_runner.build_prompt("PREAMBLE", task, "Fix only the requested logger behavior.")

    assert prompt.index("# Required repository context") < prompt.index("# GitHub Task")
    assert prompt.index("# GitHub Task") < prompt.index("# Requested revision only")
    assert "Fix only the requested logger behavior." in prompt


def test_required_context_section_wins_over_incidental_skill_references():
    task = Task(
        "initial",
        47,
        "Reporting",
        "Required repository context:\n"
        "- `.agents/skills/device-reporting/SKILL.md`\n\n"
        "## Notes\n"
        "The orchestration skill `.agents/skills/codex-orchestration/SKILL.md` is not needed.",
        "",
    )
    assert codex_runner.required_context(task) == [
        "AGENTS.md",
        ".agents/skills/device-reporting/SKILL.md",
    ]
