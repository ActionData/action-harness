"""Tests for repository profiler."""

import json
from pathlib import Path

from action_harness.profiler import (
    BOOTSTRAP_EVAL_COMMANDS,
    _detect_ecosystem,
    _detect_js_commands,
    _detect_python_commands,
    _parse_claude_md,
    profile_repo,
)


class TestDetectEcosystem:
    """Tests for _detect_ecosystem."""

    def test_pyproject_toml_detected_as_python(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").touch()
        ecosystem, marker = _detect_ecosystem(tmp_path)
        assert ecosystem == "python"
        assert marker == "pyproject.toml"

    def test_package_json_detected_as_javascript(self, tmp_path: Path) -> None:
        (tmp_path / "package.json").touch()
        ecosystem, marker = _detect_ecosystem(tmp_path)
        assert ecosystem == "javascript"
        assert marker == "package.json"

    def test_cargo_toml_detected_as_rust(self, tmp_path: Path) -> None:
        (tmp_path / "Cargo.toml").touch()
        ecosystem, marker = _detect_ecosystem(tmp_path)
        assert ecosystem == "rust"
        assert marker == "Cargo.toml"

    def test_go_mod_detected_as_go(self, tmp_path: Path) -> None:
        (tmp_path / "go.mod").touch()
        ecosystem, marker = _detect_ecosystem(tmp_path)
        assert ecosystem == "go"
        assert marker == "go.mod"

    def test_makefile_detected_as_make(self, tmp_path: Path) -> None:
        (tmp_path / "Makefile").touch()
        ecosystem, marker = _detect_ecosystem(tmp_path)
        assert ecosystem == "make"
        assert marker == "Makefile"

    def test_no_markers_returns_unknown(self, tmp_path: Path) -> None:
        ecosystem, marker = _detect_ecosystem(tmp_path)
        assert ecosystem == "unknown"
        assert marker is None

    def test_multiple_markers_returns_highest_priority(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").touch()
        (tmp_path / "package.json").touch()
        (tmp_path / "Makefile").touch()
        ecosystem, marker = _detect_ecosystem(tmp_path)
        assert ecosystem == "python"
        assert marker == "pyproject.toml"


class TestParseClaudeMd:
    """Tests for _parse_claude_md."""

    def test_extracts_commands_from_build_and_test(self, tmp_path: Path) -> None:
        (tmp_path / "CLAUDE.md").write_text(
            "# Project\n\n## Build & Test\n\n```bash\nuv run pytest -v\nuv run ruff check .\n```\n"
        )
        commands = _parse_claude_md(tmp_path)
        assert commands == ["uv run pytest -v", "uv run ruff check ."]

    def test_extracts_from_alternate_heading(self, tmp_path: Path) -> None:
        (tmp_path / "CLAUDE.md").write_text(
            "## Build and Test\n\n```\nnpm test\nnpm run lint\n```\n"
        )
        commands = _parse_claude_md(tmp_path)
        assert commands == ["npm test", "npm run lint"]

    def test_ignores_comment_lines_in_code_blocks(self, tmp_path: Path) -> None:
        (tmp_path / "CLAUDE.md").write_text(
            "## Build & Test\n\n```bash\n# install deps first\nuv sync\nuv run pytest -v\n```\n"
        )
        commands = _parse_claude_md(tmp_path)
        assert commands == ["uv sync", "uv run pytest -v"]

    def test_ignores_empty_lines(self, tmp_path: Path) -> None:
        (tmp_path / "CLAUDE.md").write_text(
            "## Build & Test\n\n```bash\nuv run pytest -v\n\nuv run ruff check .\n```\n"
        )
        commands = _parse_claude_md(tmp_path)
        assert commands == ["uv run pytest -v", "uv run ruff check ."]

    def test_returns_none_when_no_claude_md(self, tmp_path: Path) -> None:
        assert _parse_claude_md(tmp_path) is None

    def test_returns_none_when_heading_not_found(self, tmp_path: Path) -> None:
        (tmp_path / "CLAUDE.md").write_text("# Project\n\n## Usage\n\nSome text.\n")
        assert _parse_claude_md(tmp_path) is None

    def test_returns_none_when_code_block_is_empty(self, tmp_path: Path) -> None:
        (tmp_path / "CLAUDE.md").write_text("## Build & Test\n\n```bash\n```\n")
        assert _parse_claude_md(tmp_path) is None

    def test_stops_at_next_heading(self, tmp_path: Path) -> None:
        (tmp_path / "CLAUDE.md").write_text(
            "## Build & Test\n\n"
            "```bash\n"
            "uv run pytest -v\n"
            "```\n\n"
            "## Other Section\n\n"
            "```bash\n"
            "echo should not appear\n"
            "```\n"
        )
        commands = _parse_claude_md(tmp_path)
        assert commands == ["uv run pytest -v"]

    def test_strips_inline_comments(self, tmp_path: Path) -> None:
        (tmp_path / "CLAUDE.md").write_text(
            "## Build & Test\n\n"
            "```bash\n"
            "uv sync                          # install dependencies\n"
            "uv run pytest -v                  # run all tests\n"
            "```\n"
        )
        commands = _parse_claude_md(tmp_path)
        assert commands == ["uv sync", "uv run pytest -v"]


class TestDetectPythonCommands:
    """Tests for _detect_python_commands."""

    def test_all_tools_configured(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text(
            "[tool.pytest.ini_options]\n"
            'testpaths = ["tests"]\n\n'
            "[tool.ruff]\n"
            "line-length = 100\n\n"
            "[tool.mypy]\n"
            "strict = true\n"
        )
        commands = _detect_python_commands(tmp_path)
        assert len(commands) == 4
        assert "uv run pytest -v" in commands
        assert "uv run ruff check ." in commands
        assert "uv run ruff format --check ." in commands
        assert "uv run mypy src/" in commands

    def test_only_pytest_configured(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text(
            '[tool.pytest.ini_options]\ntestpaths = ["tests"]\n'
        )
        commands = _detect_python_commands(tmp_path)
        assert commands == ["uv run pytest -v"]

    def test_no_tools_configured(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text('[project]\nname = "myproject"\n')
        commands = _detect_python_commands(tmp_path)
        assert commands == []

    def test_malformed_toml_returns_empty(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text("this is not valid toml {{{")
        commands = _detect_python_commands(tmp_path)
        assert commands == []


class TestDetectJsCommands:
    """Tests for _detect_js_commands."""

    def test_test_and_lint_scripts_detected(self, tmp_path: Path) -> None:
        (tmp_path / "package.json").write_text(
            json.dumps({"scripts": {"test": "jest", "lint": "eslint ."}})
        )
        commands = _detect_js_commands(tmp_path)
        assert "npm test" in commands
        assert "npm run lint" in commands

    def test_no_scripts_key_returns_empty(self, tmp_path: Path) -> None:
        (tmp_path / "package.json").write_text(json.dumps({"name": "mypackage"}))
        commands = _detect_js_commands(tmp_path)
        assert commands == []

    def test_tsconfig_present_adds_tsc_command(self, tmp_path: Path) -> None:
        (tmp_path / "package.json").write_text(json.dumps({"scripts": {"test": "jest"}}))
        (tmp_path / "tsconfig.json").touch()
        commands = _detect_js_commands(tmp_path)
        assert "npm test" in commands
        assert "npx tsc --noEmit" in commands


class TestProfileRepo:
    """Tests for profile_repo."""

    def test_claude_md_takes_precedence_over_pyproject(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text(
            '[tool.pytest.ini_options]\ntestpaths = ["tests"]\n'
        )
        (tmp_path / "CLAUDE.md").write_text("## Build & Test\n\n```bash\nmake test\n```\n")
        profile = profile_repo(tmp_path)
        assert profile.source == "claude-md"
        assert profile.eval_commands == ["make test"]
        assert profile.marker_file == "CLAUDE.md"

    def test_python_convention_detection(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text(
            '[tool.pytest.ini_options]\ntestpaths = ["tests"]\n\n[tool.ruff]\nline-length = 100\n'
        )
        profile = profile_repo(tmp_path)
        assert profile.source == "convention"
        assert profile.ecosystem == "python"
        assert profile.marker_file == "pyproject.toml"
        assert "uv run pytest -v" in profile.eval_commands

    def test_fallback_when_nothing_detected(self, tmp_path: Path) -> None:
        profile = profile_repo(tmp_path)
        assert profile.source == "fallback"
        assert profile.ecosystem == "unknown"
        assert profile.eval_commands == list(BOOTSTRAP_EVAL_COMMANDS)

    def test_source_field_correct_for_each_path(self, tmp_path: Path) -> None:
        # Fallback
        profile = profile_repo(tmp_path)
        assert profile.source == "fallback"

        # Convention
        (tmp_path / "Cargo.toml").touch()
        profile = profile_repo(tmp_path)
        assert profile.source == "convention"

        # CLAUDE.md
        (tmp_path / "CLAUDE.md").write_text("## Build & Test\n\n```\ncargo test\n```\n")
        profile = profile_repo(tmp_path)
        assert profile.source == "claude-md"

    def test_profile_is_json_serializable(self, tmp_path: Path) -> None:
        (tmp_path / "pyproject.toml").write_text(
            '[tool.pytest.ini_options]\ntestpaths = ["tests"]\n'
        )
        profile = profile_repo(tmp_path)
        json_str = profile.model_dump_json()
        data = json.loads(json_str)
        assert "ecosystem" in data
        assert "eval_commands" in data
        assert "source" in data
        assert "marker_file" in data


def test_profile_action_harness_repo() -> None:
    """Integration test: profile the actual action-harness repo."""
    profile = profile_repo(Path(".").resolve())
    assert profile.ecosystem == "python"
    assert profile.source == "claude-md"
    assert "uv run pytest -v" in profile.eval_commands
