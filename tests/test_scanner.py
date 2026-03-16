"""Tests for mechanical scanners."""

import subprocess
from pathlib import Path

from action_harness.scanner import (
    analyze_test_structure,
    detect_context_signals,
    detect_isolation_signals,
    detect_lockfiles,
    detect_observability_signals,
    detect_tooling_signals,
)

# === Lockfile Detection ===


def test_lockfile_uv_lock(tmp_path: Path) -> None:
    """uv.lock detected as lockfile."""
    (tmp_path / "uv.lock").touch()
    present, name = detect_lockfiles(tmp_path)
    assert present is True
    assert name == "uv.lock"


def test_lockfile_package_lock(tmp_path: Path) -> None:
    """package-lock.json detected as lockfile."""
    (tmp_path / "package-lock.json").touch()
    present, name = detect_lockfiles(tmp_path)
    assert present is True
    assert name == "package-lock.json"


def test_lockfile_cargo_lock(tmp_path: Path) -> None:
    """Cargo.lock detected as lockfile."""
    (tmp_path / "Cargo.lock").touch()
    present, name = detect_lockfiles(tmp_path)
    assert present is True
    assert name == "Cargo.lock"


def test_no_lockfile(tmp_path: Path) -> None:
    """No lockfile returns (False, None)."""
    present, name = detect_lockfiles(tmp_path)
    assert present is False
    assert name is None


# === Test Structure Analysis ===


def test_python_test_structure(tmp_path: Path) -> None:
    """Python test files and functions counted correctly."""
    (tmp_path / "pyproject.toml").write_text('[tool.pytest.ini_options]\ntestpaths = ["tests"]')
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_foo.py").write_text(
        "def test_one():\n    pass\n\ndef test_two():\n    pass\n"
    )
    (tests_dir / "test_bar.py").write_text("def test_three():\n    pass\n")

    result = analyze_test_structure(tmp_path, "python")
    assert result.test_framework_configured is True
    assert result.test_files == 2
    assert result.test_functions == 3


def test_python_with_coverage_config(tmp_path: Path) -> None:
    """Coverage configured detected from pyproject.toml."""
    (tmp_path / "pyproject.toml").write_text(
        '[tool.pytest.ini_options]\n[tool.coverage.run]\nsource = ["src"]'
    )
    result = analyze_test_structure(tmp_path, "python")
    assert result.test_framework_configured is True
    assert result.coverage_configured is True


def test_js_test_structure(tmp_path: Path) -> None:
    """JavaScript test files detected with it() and test() calls."""
    (tmp_path / "package.json").write_text('{"devDependencies": {"jest": "^29.0.0"}}')
    (tmp_path / "foo.test.ts").write_text('it("works", () => {});\ntest("also works", () => {});')

    result = analyze_test_structure(tmp_path, "javascript")
    assert result.test_framework_configured is True
    assert result.test_files == 1
    assert result.test_functions == 2


def test_empty_repo_test_structure(tmp_path: Path) -> None:
    """Empty repo returns zero test counts."""
    result = analyze_test_structure(tmp_path, "python")
    assert result.test_framework_configured is False
    assert result.test_files == 0
    assert result.test_functions == 0


# === Context Signals ===


def test_context_signals_all_present(tmp_path: Path) -> None:
    """All context files present detected correctly."""
    (tmp_path / "CLAUDE.md").write_text("# CLAUDE.md")
    (tmp_path / "README.md").write_text("# README")
    (tmp_path / "HARNESS.md").write_text("# HARNESS")
    (tmp_path / "AGENTS.md").write_text("# AGENTS")

    result = detect_context_signals(tmp_path)
    assert result.claude_md is True
    assert result.readme is True
    assert result.harness_md is True
    assert result.agents_md is True


def test_context_signals_none_present(tmp_path: Path) -> None:
    """No context files returns all False."""
    result = detect_context_signals(tmp_path)
    assert result.claude_md is False
    assert result.readme is False
    assert result.harness_md is False
    assert result.agents_md is False


def test_context_type_annotations_detected(tmp_path: Path) -> None:
    """Type annotations in source files detected."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "foo.py").write_text('def greet(name: str) -> str:\n    """Hello."""\n    return name\n')

    result = detect_context_signals(tmp_path)
    assert result.type_annotations_present is True
    assert result.docstrings_present is True


# === Tooling Signals ===


def test_tooling_signals_python(tmp_path: Path) -> None:
    """Python tooling markers detected."""
    (tmp_path / "pyproject.toml").write_text("[project]")
    (tmp_path / "uv.lock").touch()

    result = detect_tooling_signals(tmp_path)
    assert result.package_manager is True
    assert result.lockfile_present is True
    assert result.lockfile == "uv.lock"


def test_tooling_mcp_configured(tmp_path: Path) -> None:
    """MCP configuration detected."""
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir()
    (claude_dir / "mcp.json").write_text("{}")

    result = detect_tooling_signals(tmp_path)
    assert result.mcp_configured is True


def test_tooling_skills_present(tmp_path: Path) -> None:
    """Claude skills detected."""
    commands_dir = tmp_path / ".claude" / "commands"
    commands_dir.mkdir(parents=True)
    (commands_dir / "review.md").write_text("Review skill")

    result = detect_tooling_signals(tmp_path)
    assert result.skills_present is True


def test_tooling_docker(tmp_path: Path) -> None:
    """Docker configuration detected."""
    (tmp_path / "Dockerfile").write_text("FROM python:3.13")
    result = detect_tooling_signals(tmp_path)
    assert result.docker_configured is True


def test_tooling_empty_repo(tmp_path: Path) -> None:
    """Empty repo has no tooling signals."""
    result = detect_tooling_signals(tmp_path)
    assert result.package_manager is False
    assert result.lockfile_present is False


# === Observability Signals ===


def test_observability_structlog(tmp_path: Path) -> None:
    """structlog dependency detected."""
    (tmp_path / "pyproject.toml").write_text('dependencies = ["structlog"]')
    result = detect_observability_signals(tmp_path)
    assert result.structured_logging_lib is True


def test_observability_health_endpoint(tmp_path: Path) -> None:
    """Health endpoint pattern detected in source."""
    src = tmp_path / "src"
    src.mkdir()
    (src / "app.py").write_text('app.route("/health")\ndef health(): return "ok"')

    result = detect_observability_signals(tmp_path)
    assert result.health_endpoint is True


def test_observability_empty_repo(tmp_path: Path) -> None:
    """Empty repo has no observability signals."""
    result = detect_observability_signals(tmp_path)
    assert result.structured_logging_lib is False
    assert result.health_endpoint is False
    assert result.metrics_lib is False
    assert result.tracing_lib is False


# === Isolation Signals ===


def test_isolation_git_repo(tmp_path: Path) -> None:
    """Git repo detection."""
    subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
    (tmp_path / "pyproject.toml").write_text("[project]")
    (tmp_path / "uv.lock").touch()
    (tmp_path / ".env.example").touch()

    result = detect_isolation_signals(tmp_path)
    assert result.git_repo is True
    assert result.lockfile_present is True
    assert result.env_example_present is True
    assert result.reproducible_build is True


def test_isolation_empty_dir(tmp_path: Path) -> None:
    """Empty directory has minimal isolation signals."""
    result = detect_isolation_signals(tmp_path)
    assert result.git_repo is False
    assert result.lockfile_present is False
    assert result.env_example_present is False


def test_isolation_no_committed_secrets_default(tmp_path: Path) -> None:
    """Default assumption: no committed secrets."""
    result = detect_isolation_signals(tmp_path)
    assert result.no_committed_secrets is True


def test_isolation_detects_aws_key(tmp_path: Path) -> None:
    """Secret scanner detects AWS access key pattern."""
    subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "t@t.com"],
        cwd=tmp_path,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "T"],
        cwd=tmp_path,
        capture_output=True,
    )
    (tmp_path / "config.py").write_text('AWS_KEY = "AKIAIOSFODNN7EXAMPLE1"\n')
    subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "add config"],
        cwd=tmp_path,
        capture_output=True,
    )

    result = detect_isolation_signals(tmp_path)
    assert result.no_committed_secrets is False


def test_rust_test_structure(tmp_path: Path) -> None:
    """Rust #[test] annotations detected and counted."""
    (tmp_path / "Cargo.toml").write_text("[package]\nname = 'demo'\n")
    src = tmp_path / "src"
    src.mkdir()
    (src / "lib.rs").write_text(
        "#[cfg(test)]\nmod tests {\n"
        "    #[test]\n    fn test_a() {}\n"
        "    #[test]\n    fn test_b() {}\n"
        "}\n"
    )

    result = analyze_test_structure(tmp_path, "rust")
    assert result.test_framework_configured is True
    assert result.test_files == 1
    assert result.test_functions == 2


def test_isolation_detects_api_key_pattern(tmp_path: Path) -> None:
    """Secret scanner detects api_key = 'value' pattern."""
    subprocess.run(["git", "init"], cwd=tmp_path, capture_output=True)
    subprocess.run(
        ["git", "config", "user.email", "t@t.com"],
        cwd=tmp_path,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "T"],
        cwd=tmp_path,
        capture_output=True,
    )
    (tmp_path / "settings.py").write_text('api_key = "supersecretkey12345"\n')
    subprocess.run(["git", "add", "."], cwd=tmp_path, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "add settings"],
        cwd=tmp_path,
        capture_output=True,
    )

    result = detect_isolation_signals(tmp_path)
    assert result.no_committed_secrets is False
