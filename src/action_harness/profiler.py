"""Repository profiling — detect ecosystem, build tools, and eval commands."""

import json
import re
import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

# Canonical fallback eval commands. Imported by evaluator.py.
BOOTSTRAP_EVAL_COMMANDS = [
    "uv run pytest -v",
    "uv run ruff check .",
    "uv run ruff format --check .",
    "uv run mypy src/",
]

# Priority-ordered marker files: first match wins.
_MARKER_FILES: list[tuple[str, str]] = [
    ("pyproject.toml", "python"),
    ("setup.py", "python"),
    ("package.json", "javascript"),
    ("Cargo.toml", "rust"),
    ("go.mod", "go"),
    ("Makefile", "make"),
    ("Gemfile", "ruby"),
]


class RepoProfile(BaseModel):
    """Structured profile of a repository's ecosystem and eval commands."""

    ecosystem: str
    eval_commands: list[str]
    source: Literal["claude-md", "convention", "fallback"]
    marker_file: str | None = None


def _detect_ecosystem(repo_path: Path) -> tuple[str, str | None]:
    """Scan for marker files in priority order. Return (ecosystem, marker_filename)."""
    for filename, ecosystem in _MARKER_FILES:
        if (repo_path / filename).exists():
            return ecosystem, filename
    return "unknown", None


def _parse_claude_md(repo_path: Path) -> list[str] | None:
    """Extract eval commands from CLAUDE.md's Build & Test section.

    Returns None if the file is missing, heading not found, or no commands extracted.
    """
    claude_md = repo_path / "CLAUDE.md"
    if not claude_md.exists():
        return None

    try:
        content = claude_md.read_text()
    except OSError:
        return None

    # Find the Build & Test heading (case-insensitive)
    heading_pattern = re.compile(r"^## build (?:&|and) test", re.IGNORECASE | re.MULTILINE)
    match = heading_pattern.search(content)
    if not match:
        return None

    # Extract section content until next ## heading or EOF
    section_start = match.end()
    next_heading = re.search(r"^## ", content[section_start:], re.MULTILINE)
    if next_heading:
        section = content[section_start : section_start + next_heading.start()]
    else:
        section = content[section_start:]

    # Parse fenced code blocks and extract commands
    commands: list[str] = []
    in_code_block = False

    for line in section.splitlines():
        stripped = line.strip()
        if stripped.startswith("```"):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            # Skip empty lines and full comment lines
            if not stripped or stripped.startswith("#"):
                continue
            # Strip inline comments (` # ` pattern with leading space)
            cmd = re.sub(r"\s+#\s.*$", "", stripped).strip()
            if cmd:
                commands.append(cmd)

    return commands if commands else None


def _detect_python_commands(repo_path: Path) -> list[str]:
    """Detect Python eval commands from pyproject.toml tool configuration."""
    pyproject = repo_path / "pyproject.toml"
    if not pyproject.exists():
        return []

    try:
        data = tomllib.loads(pyproject.read_text())
    except Exception:
        return []

    commands: list[str] = []
    tool = data.get("tool", {})

    if "pytest" in tool or "pytest.ini_options" in tool:
        # Check nested form: tool.pytest.ini_options
        pytest_section = tool.get("pytest", {})
        if isinstance(pytest_section, dict) and "ini_options" in pytest_section:
            commands.append("uv run pytest -v")
        elif "pytest" in tool:
            commands.append("uv run pytest -v")

    if "ruff" in tool:
        commands.append("uv run ruff check .")
        commands.append("uv run ruff format --check .")

    if "mypy" in tool:
        commands.append("uv run mypy src/")

    return commands


def _detect_js_commands(repo_path: Path) -> list[str]:
    """Detect JavaScript/TypeScript eval commands from package.json."""
    package_json = repo_path / "package.json"
    if not package_json.exists():
        return []

    try:
        data = json.loads(package_json.read_text())
    except Exception:
        return []

    commands: list[str] = []
    scripts = data.get("scripts", {})

    if "test" in scripts:
        commands.append("npm test")

    if "lint" in scripts:
        commands.append("npm run lint")

    if "format:check" in scripts or "format" in scripts:
        commands.append("npm run format:check")

    if (repo_path / "tsconfig.json").exists():
        commands.append("npx tsc --noEmit")

    return commands


def _detect_convention_commands(ecosystem: str, repo_path: Path) -> list[str]:
    """Dispatch to ecosystem-specific detectors for convention-based commands."""
    if ecosystem == "python":
        return _detect_python_commands(repo_path)

    if ecosystem == "javascript":
        return _detect_js_commands(repo_path)

    if ecosystem == "rust":
        return ["cargo test", "cargo clippy -- -D warnings", "cargo fmt -- --check"]

    if ecosystem == "go":
        return ["go test ./...", "golangci-lint run", "gofmt -l ."]

    if ecosystem == "make":
        makefile = repo_path / "Makefile"
        if makefile.exists():
            try:
                content = makefile.read_text()
                if re.search(r"^test:", content, re.MULTILINE):
                    return ["make test"]
            except OSError:
                pass
        return []

    if ecosystem == "ruby":
        return ["bundle exec rake test", "bundle exec rubocop"]

    return []


def profile_repo(repo_path: Path) -> RepoProfile:
    """Profile a repository to determine ecosystem and eval commands.

    Detection priority:
    1. CLAUDE.md Build & Test section (explicit commands)
    2. Ecosystem convention detection (marker files + tool config)
    3. Fallback to BOOTSTRAP_EVAL_COMMANDS
    """
    ecosystem, marker_file = _detect_ecosystem(repo_path)

    # Try CLAUDE.md first
    claude_commands = _parse_claude_md(repo_path)
    if claude_commands:
        return RepoProfile(
            ecosystem=ecosystem,
            eval_commands=claude_commands,
            source="claude-md",
            marker_file="CLAUDE.md",
        )

    # Try convention detection
    convention_commands = _detect_convention_commands(ecosystem, repo_path)
    if convention_commands:
        return RepoProfile(
            ecosystem=ecosystem,
            eval_commands=convention_commands,
            source="convention",
            marker_file=marker_file,
        )

    # Fallback
    return RepoProfile(
        ecosystem=ecosystem,
        eval_commands=list(BOOTSTRAP_EVAL_COMMANDS),
        source="fallback",
        marker_file=marker_file,
    )
