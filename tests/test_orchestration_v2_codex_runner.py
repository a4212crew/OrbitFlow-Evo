from pathlib import Path
import os
import sys

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
    assert captured["env"]["TEMP"] == str(worktree / ".codex-tmp")
    assert not (worktree / ".codex-tmp").exists()
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
