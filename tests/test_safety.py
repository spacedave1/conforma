"""Evidence class: stub integration checks using public Conforma surfaces only."""

import asyncio
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from conforma.providers import llm_provider
from conforma.run import run_eval

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.verifies("conforma-safety.1")
def test_judge_diagnostic_redacts_all_provider_configuration(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Fails if evaluation prints a judge provider secret or hides its identity."""
    api_secret = "CONFORMA_SAFETY_API_SECRET_7f0d"
    nested_secret = "CONFORMA_SAFETY_NESTED_SECRET_91ab"
    platform = "judge-visible-platform"
    model = "judge-visible-model"
    calls: list[dict[str, object]] = []

    (tmp_path / "config.yaml").write_text(
        f"""\
models_to_test:
  - name: candidate
    platform: candidate-platform
    model: candidate-model
judge_model:
  platform: {platform}
  model: {model}
  api_key: {api_secret}
  transport:
    nested_secret: {nested_secret}
runs_per_sample: 1
judge_runs_per_output: 1
""",
        encoding="utf-8",
    )
    (tmp_path / "prompt.md").write_text("Answer the scenario.", encoding="utf-8")
    (tmp_path / "spec.md").write_text("The response shall be evaluated.", encoding="utf-8")
    scenarios = tmp_path / "scenarios"
    scenarios.mkdir()
    (scenarios / "simple.json").write_text(
        json.dumps([{"role": "user", "content": "Hello"}]),
        encoding="utf-8",
    )

    def fake_provider_factory(*_args: object, **kwargs: object) -> object:
        calls.append(dict(kwargs))
        return llm_provider(model="fake", platform="fake")

    result = asyncio.run(
        run_eval(str(tmp_path), provider_factory=fake_provider_factory)
    )
    captured = capsys.readouterr()
    diagnostic = captured.out + captured.err

    assert result == 0
    assert any(
        call.get("platform") == platform
        and call.get("model") == model
        and call.get("api_key") == api_secret
        and call.get("transport") == {"nested_secret": nested_secret}
        for call in calls
    )
    assert platform in diagnostic
    assert model in diagnostic
    assert api_secret not in diagnostic
    assert nested_secret not in diagnostic


@pytest.mark.verifies("conforma-safety.2")
@pytest.mark.parametrize(
    "path",
    [
        "outputs.md",
        "summaries.json",
        "chart.png",
        "log.db",
        "scenarios/case-a/outputs.md",
        "scenarios/case-a/summaries.json",
        "scenarios/case-a/chart.png",
        "scenarios/case-a/log.db",
    ],
)
def test_gitignore_excludes_generated_outputs_at_every_scenario_depth(
    tmp_path: Path, path: str
) -> None:
    """Fails if a generated evaluation artifact remains eligible for tracking."""
    source_gitignore = ROOT / ".gitignore"
    assert source_gitignore.is_file(), "repository root must contain .gitignore"
    shutil.copy2(source_gitignore, tmp_path / ".gitignore")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)

    check = subprocess.run(
        ["git", "check-ignore", "-q", "--", path],
        cwd=tmp_path,
        check=False,
    )

    assert check.returncode == 0, f"{path} is not ignored"


@pytest.mark.verifies("conforma-safety.2")
@pytest.mark.parametrize("path", ["prompt.md", "spec.md", "scenarios/case-a.json"])
def test_gitignore_keeps_authored_evaluation_inputs_trackable(
    tmp_path: Path, path: str
) -> None:
    """Fails if an authored evaluation input becomes ignored."""
    source_gitignore = ROOT / ".gitignore"
    assert source_gitignore.is_file(), "repository root must contain .gitignore"
    shutil.copy2(source_gitignore, tmp_path / ".gitignore")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)

    check = subprocess.run(
        ["git", "check-ignore", "-q", "--", path],
        cwd=tmp_path,
        check=False,
    )

    assert check.returncode == 1, f"{path} must remain trackable"


@pytest.mark.verifies("conforma-safety.3")
@pytest.mark.parametrize("env_location", ["current", "parent"])
def test_builtin_provider_does_not_load_dotenv_or_mutate_environment(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, env_location: str
) -> None:
    """Fails if fake-provider creation changes a controlled process environment."""
    parent = tmp_path / "project"
    current = parent / "child"
    current.mkdir(parents=True)
    dotenv = current / ".env" if env_location == "current" else parent / ".env"
    dotenv.write_text(
        "CONFORMA_SAFETY_EXISTING=overwritten\n"
        "CONFORMA_SAFETY_NEW=must-not-appear\n",
        encoding="utf-8",
    )

    controlled_environment = {"CONFORMA_SAFETY_EXISTING": "preserve"}
    monkeypatch.setattr(os, "environ", controlled_environment)
    monkeypatch.chdir(current)
    before = dict(controlled_environment)

    provider = llm_provider(model="fake", platform="fake")

    assert provider is not None
    assert dict(controlled_environment) == before
    assert controlled_environment["CONFORMA_SAFETY_EXISTING"] == "preserve"
    assert "CONFORMA_SAFETY_NEW" not in controlled_environment
