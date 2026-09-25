from pathlib import Path
import sys

import pytest

ORCH = Path(__file__).parents[1] / "scripts" / "orchestration_v2"
sys.path.insert(0, str(ORCH))

import preflight  # noqa: E402
from models import FailureCategory, OrchestrationError  # noqa: E402


class Completed:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def test_codex_auth_requires_chatgpt_and_rejects_api_key(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENAI_API_KEY", "should-not-be-used")

    with pytest.raises(OrchestrationError) as error:
        preflight.verify_codex_auth(tmp_path)

    assert error.value.category is FailureCategory.PREREQUISITE
    assert "OPENAI_API_KEY is set" in str(error.value)


def test_codex_auth_accepts_explicit_chatgpt_status(monkeypatch, tmp_path):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    def fake_run(args, **_kwargs):
        if args == ["codex", "--version"]:
            return Completed(stdout="codex-cli 1.2.3\n")
        if args == ["codex", "login", "status"]:
            return Completed(stdout="Logged in using ChatGPT\n")
        raise AssertionError(args)

    monkeypatch.setattr(preflight, "run_command", fake_run)

    version, status = preflight.verify_codex_auth(tmp_path)

    assert version == "codex-cli 1.2.3"
    assert status == "Logged in using ChatGPT"


def test_codex_auth_fails_closed_when_method_is_ambiguous(monkeypatch, tmp_path):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    def fake_run(args, **_kwargs):
        if args == ["codex", "--version"]:
            return Completed(stdout="codex-cli 1.2.3\n")
        return Completed(stdout="Logged in\n")

    monkeypatch.setattr(preflight, "run_command", fake_run)

    with pytest.raises(OrchestrationError, match="cannot verify ChatGPT-account"):
        preflight.verify_codex_auth(tmp_path)


def test_run_preflight_checks_all_tools_and_auth(monkeypatch, tmp_path):
    executable_checks = []
    monkeypatch.setattr(preflight, "ensure_executable", executable_checks.append)
    monkeypatch.setattr(preflight, "repository_root", lambda: tmp_path)
    monkeypatch.setattr(preflight, "verify_git_identity", lambda _root: ("Atlas", "atlas@example.test"))
    monkeypatch.setattr(preflight, "verify_repository", lambda *_args: None)
    monkeypatch.setattr(
        preflight,
        "verify_codex_auth",
        lambda _root: ("codex-cli test", "Logged in using ChatGPT"),
    )
    monkeypatch.setattr(preflight, "run_command", lambda *_args, **_kwargs: Completed())

    report = preflight.run_preflight("a4212crew/OrbitFlow-Evo")

    assert executable_checks == ["git", "gh", "codex"]
    assert report.repo_root == tmp_path
    assert report.git_name == "Atlas"
    assert report.codex_auth_status == "Logged in using ChatGPT"
