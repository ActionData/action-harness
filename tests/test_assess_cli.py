"""Tests for the assess CLI command."""

import json
import subprocess
from pathlib import Path

from typer.testing import CliRunner

from action_harness.cli import app

runner = CliRunner()


def _init_git_repo(path: Path) -> None:
    """Initialize a minimal git repo for testing."""
    subprocess.run(["git", "init"], cwd=path, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=path, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=path, capture_output=True)
    (path / "README.md").write_text("# Test")
    subprocess.run(["git", "add", "."], cwd=path, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=path, capture_output=True)


def test_assess_help() -> None:
    """--help output works for assess command."""
    result = runner.invoke(app, ["assess", "--help"])
    assert result.exit_code == 0
    assert "assess" in result.output.lower()
    assert "--repo" in result.output
    assert "--deep" in result.output
    assert "--propose" in result.output
    assert "--json" in result.output


def test_assess_base_mode(tmp_path: Path) -> None:
    """Base mode runs without error on a git repo."""
    _init_git_repo(tmp_path)
    result = runner.invoke(app, ["assess", "--repo", str(tmp_path)])
    assert result.exit_code == 0


def test_assess_json_output(tmp_path: Path) -> None:
    """--json produces valid JSON with all six categories."""
    _init_git_repo(tmp_path)
    result = runner.invoke(app, ["assess", "--repo", str(tmp_path), "--json"])
    assert result.exit_code == 0

    # CliRunner mixes stdout/stderr. Find the JSON block in output.
    output = result.output
    json_start = output.find("{\n")
    assert json_start >= 0, f"No JSON found in output: {output[:200]}"
    json_end = output.rfind("}") + 1
    report = json.loads(output[json_start:json_end])
    assert "overall_score" in report
    assert "categories" in report

    expected_categories = {
        "ci_guardrails",
        "testability",
        "context",
        "tooling",
        "observability",
        "isolation",
    }
    assert set(report["categories"].keys()) == expected_categories

    # overall_score should be an integer 0-100
    assert isinstance(report["overall_score"], int)
    assert 0 <= report["overall_score"] <= 100

    # mode should be "base"
    assert report["mode"] == "base"

    # All agent_assessment should be null in base mode
    for cat in report["categories"].values():
        assert cat["agent_assessment"] is None


def test_assess_nonexistent_repo() -> None:
    """Error for nonexistent repo path."""
    result = runner.invoke(app, ["assess", "--repo", "/nonexistent/path"])
    assert result.exit_code == 1


def test_assess_not_git_repo(tmp_path: Path) -> None:
    """Error for non-git directory."""
    result = runner.invoke(app, ["assess", "--repo", str(tmp_path)])
    assert result.exit_code == 1
