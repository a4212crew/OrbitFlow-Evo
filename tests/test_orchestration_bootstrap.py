from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
import sys


_BOOTSTRAP_PATH = (
    Path(__file__).parents[1] / "scripts" / "orchestration" / "bootstrap.py"
)
_SPEC = spec_from_file_location("orbitflow_orchestration_bootstrap", _BOOTSTRAP_PATH)
assert _SPEC is not None and _SPEC.loader is not None
bootstrap = module_from_spec(_SPEC)
sys.modules[_SPEC.name] = bootstrap
_SPEC.loader.exec_module(bootstrap)


def test_bootstrap_declares_expected_orchestration_labels():
    names = {label.name for label in bootstrap.LABELS}

    assert names == {
        "codex-task",
        "codex-running",
        "codex-review",
        "codex-revise",
        "codex-approved",
        "codex-pr",
        "codex-failed",
        "codex-replan-required",
    }


def test_bootstrap_checks_tools_repo_and_creates_labels(monkeypatch, capsys):
    executable_checks = []
    commands = []

    monkeypatch.setattr(
        bootstrap,
        "ensure_executable",
        lambda name: executable_checks.append(name),
    )

    def fake_run(args):
        commands.append(args)
        if args[:2] == ["codex", "--version"]:
            return "codex-cli test"
        if args[:3] == ["gh", "repo", "view"]:
            return '{"nameWithOwner":"a4212crew/OrbitFlow-Evo"}'
        return ""

    monkeypatch.setattr(bootstrap, "run_command", fake_run)

    bootstrap.bootstrap()

    assert executable_checks == ["gh", "codex"]
    assert ["gh", "auth", "status"] in commands
    assert ["codex", "--version"] in commands
    label_commands = [command for command in commands if command[:3] == ["gh", "label", "create"]]
    assert len(label_commands) == len(bootstrap.LABELS)
    assert "No OPENAI_API_KEY is required" in capsys.readouterr().out
