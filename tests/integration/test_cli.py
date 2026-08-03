from __future__ import annotations

from typer.testing import CliRunner

from argus.cli.main import app

runner = CliRunner()


def test_graph_command_prints_mermaid() -> None:
    result = runner.invoke(app, ["graph"])
    assert result.exit_code == 0
    assert "graph TD" in result.stdout
    assert "risk_estimation" in result.stdout


def test_config_command_masks_secrets(monkeypatch) -> None:
    monkeypatch.setenv("GOOGLE_API_KEY", "supersecretkey1234")
    result = runner.invoke(app, ["config"])
    assert result.exit_code == 0
    assert "supersecretkey1234" not in result.stdout
    assert "1234" in result.stdout


def test_doctor_command_fails_without_api_key(monkeypatch) -> None:
    monkeypatch.delenv("GOOGLE_API_KEY", raising=False)
    monkeypatch.delenv("ARGUS_GOOGLE_API_KEY", raising=False)
    result = runner.invoke(app, ["doctor"])
    assert result.exit_code == 1
    assert "FAIL" in result.stdout
