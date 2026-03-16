"""Mechanical scanners for codebase assessment."""

import glob as glob_mod
import re
import subprocess
from pathlib import Path

import typer

from action_harness.assessment import (
    ContextMechanicalSignals,
    IsolationMechanicalSignals,
    ObservabilityMechanicalSignals,
    TestabilityMechanicalSignals,
    ToolingMechanicalSignals,
)

# Directories to exclude from recursive glob scans (vendored, build artifacts).
_EXCLUDED_DIRS: set[str] = {
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    "site-packages",
    "target",
    ".git",
    "dist",
    "build",
    ".tox",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
}


def _filter_vendored(paths: list[str]) -> list[str]:
    """Filter out paths inside vendored/build directories."""
    return [
        p for p in paths if not any(f"/{d}/" in p or p.startswith(f"{d}/") for d in _EXCLUDED_DIRS)
    ]


# Priority-ordered lockfiles: first match reported as the lockfile name.
_LOCKFILES: list[str] = [
    "uv.lock",
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "Cargo.lock",
    "go.sum",
    "Gemfile.lock",
]

# Secret-like patterns (conservative — high-confidence patterns only).
_SECRET_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"(?:api[_-]?key|secret[_-]?key|password|token)\s*[:=]\s*['\"][^'\"]{8,}", re.I),
    re.compile(r"AKIA[0-9A-Z]{16}"),  # AWS access key
    re.compile(r"-----BEGIN (?:RSA |EC )?PRIVATE KEY-----"),
]


def detect_lockfiles(repo_path: Path) -> tuple[bool, str | None]:
    """Check for dependency lockfiles in the repository.

    Returns (lockfile_present, lockfile_name).
    """
    typer.echo("[scanner] checking for lockfiles", err=True)
    for lockfile in _LOCKFILES:
        if (repo_path / lockfile).exists():
            typer.echo(f"[scanner] found lockfile: {lockfile}", err=True)
            return True, lockfile
    typer.echo("[scanner] no lockfile found", err=True)
    return False, None


def analyze_test_structure(repo_path: Path, ecosystem: str) -> TestabilityMechanicalSignals:
    """Analyze test file structure and count test files/functions.

    Detects test framework configuration, counts test files and functions
    based on ecosystem conventions.
    """
    typer.echo(f"[scanner] analyzing test structure (ecosystem={ecosystem})", err=True)

    test_files = 0
    test_functions = 0
    test_framework_configured = False
    coverage_configured = False

    if ecosystem == "python":
        # Check for pytest configuration
        pyproject = repo_path / "pyproject.toml"
        if pyproject.exists():
            try:
                content = pyproject.read_text()
                if "[tool.pytest" in content:
                    test_framework_configured = True
                if "[tool.coverage" in content:
                    coverage_configured = True
            except OSError:
                pass

        # Also check for pytest.ini, setup.cfg
        if (repo_path / "pytest.ini").exists() or (repo_path / "setup.cfg").exists():
            test_framework_configured = True

        # Count test files (test_*.py and *_test.py)
        test_file_paths = _filter_vendored(
            glob_mod.glob(str(repo_path / "**/test_*.py"), recursive=True)
        )
        test_file_paths += _filter_vendored(
            glob_mod.glob(str(repo_path / "**/*_test.py"), recursive=True)
        )
        # Deduplicate
        test_file_paths = list(set(test_file_paths))
        test_files = len(test_file_paths)

        # Count test functions
        for tf in test_file_paths:
            try:
                content = Path(tf).read_text()
                test_functions += len(re.findall(r"def test_", content))
            except OSError:
                pass

    elif ecosystem == "javascript":
        # Check for test framework in package.json
        package_json = repo_path / "package.json"
        if package_json.exists():
            try:
                content = package_json.read_text()
                if any(fw in content for fw in ["jest", "mocha", "vitest", "ava"]):
                    test_framework_configured = True
            except OSError:
                pass

        # Check for coverage config
        if (repo_path / ".nycrc").exists() or (repo_path / ".nycrc.json").exists():
            coverage_configured = True

        # Count test files (*.test.ts, *.test.js, *.spec.ts, *.spec.js)
        for pattern in ["**/*.test.ts", "**/*.test.js", "**/*.spec.ts", "**/*.spec.js"]:
            test_file_paths = _filter_vendored(
                glob_mod.glob(str(repo_path / pattern), recursive=True)
            )
            test_files += len(test_file_paths)
            for tf in test_file_paths:
                try:
                    content = Path(tf).read_text()
                    test_functions += len(re.findall(r"\bit\(", content))
                    test_functions += len(re.findall(r"\btest\(", content))
                except OSError:
                    pass

    elif ecosystem == "rust":
        # Rust uses #[test] annotations
        rs_files = _filter_vendored(glob_mod.glob(str(repo_path / "**/*.rs"), recursive=True))
        for rf in rs_files:
            try:
                content = Path(rf).read_text()
                count = len(re.findall(r"#\[test\]", content))
                if count > 0:
                    test_files += 1
                    test_functions += count
            except OSError:
                pass
        if (repo_path / "Cargo.toml").exists():
            test_framework_configured = True

    typer.echo(
        f"[scanner] test structure: framework={test_framework_configured}, "
        f"files={test_files}, functions={test_functions}, "
        f"coverage={coverage_configured}",
        err=True,
    )

    return TestabilityMechanicalSignals(
        test_framework_configured=test_framework_configured,
        test_files=test_files,
        test_functions=test_functions,
        coverage_configured=coverage_configured,
    )


def detect_context_signals(repo_path: Path) -> ContextMechanicalSignals:
    """Check for context files and agent-relevant documentation.

    Detects CLAUDE.md, README, HARNESS.md, AGENTS.md, and samples source
    files for type annotations and docstrings.
    """
    typer.echo("[scanner] detecting context signals", err=True)

    claude_md = (repo_path / "CLAUDE.md").exists()
    readme = (repo_path / "README.md").exists() or (repo_path / "README").exists()
    harness_md = (repo_path / "HARNESS.md").exists()
    agents_md = (repo_path / "AGENTS.md").exists()

    # Sample source files for type annotations and docstrings
    type_annotations_present = False
    docstrings_present = False

    # Find up to 5 source files to sample
    source_patterns = ["**/*.py", "**/*.ts", "**/*.rs"]
    sample_files: list[str] = []
    for pattern in source_patterns:
        sample_files.extend(
            _filter_vendored(glob_mod.glob(str(repo_path / pattern), recursive=True))
        )
        if len(sample_files) >= 10:
            break

    # Filter out test files and limit to 5
    sample_files = [f for f in sample_files if "test_" not in Path(f).name][:5]

    for sf in sample_files:
        try:
            content = Path(sf).read_text()
            # Check for type annotations (Python: -> or : type, TS: : type, Rust: -> type)
            type_pattern = (
                r"def \w+\([^)]*:.*\)|def \w+\(.*\) ->"
                r"|:\s*(str|int|bool|float|list|dict|Path|None)\b"
            )
            if re.search(type_pattern, content):
                type_annotations_present = True
            if re.search(r'""".*?"""', content, re.DOTALL) or re.search(r"///", content):
                docstrings_present = True
        except OSError:
            pass

    typer.echo(
        f"[scanner] context: claude_md={claude_md}, readme={readme}, "
        f"harness_md={harness_md}, agents_md={agents_md}, "
        f"types={type_annotations_present}, docs={docstrings_present}",
        err=True,
    )

    return ContextMechanicalSignals(
        claude_md=claude_md,
        readme=readme,
        harness_md=harness_md,
        agents_md=agents_md,
        type_annotations_present=type_annotations_present,
        docstrings_present=docstrings_present,
    )


def detect_tooling_signals(repo_path: Path) -> ToolingMechanicalSignals:
    """Check for tooling configuration markers.

    Detects package managers, lockfiles, MCP configs, Claude skills,
    Docker files, and CLI tools.
    """
    typer.echo("[scanner] detecting tooling signals", err=True)

    # Package manager markers
    pm_markers = [
        "pyproject.toml",
        "package.json",
        "Cargo.toml",
        "go.mod",
        "Gemfile",
        "setup.py",
    ]
    package_manager = any((repo_path / m).exists() for m in pm_markers)

    # Lockfiles
    lockfile_present, lockfile = detect_lockfiles(repo_path)

    # MCP configs
    claude_dir = repo_path / ".claude"
    mcp_configured = False
    if claude_dir.is_dir():
        mcp_files = glob_mod.glob(str(claude_dir / "mcp*.json"))
        mcp_configured = len(mcp_files) > 0

    # Skills
    skills_present = False
    commands_dir = claude_dir / "commands"
    if commands_dir.is_dir():
        skill_files = list(commands_dir.iterdir())
        skills_present = len(skill_files) > 0

    # Docker
    docker_files = ["Dockerfile", "docker-compose.yml", "compose.yml"]
    docker_configured = any((repo_path / f).exists() for f in docker_files)

    # CLI tools available (check for common tool configs)
    cli_tools_available = package_manager and lockfile_present

    typer.echo(
        f"[scanner] tooling: pm={package_manager}, lock={lockfile_present}, "
        f"mcp={mcp_configured}, skills={skills_present}, "
        f"docker={docker_configured}, cli={cli_tools_available}",
        err=True,
    )

    return ToolingMechanicalSignals(
        package_manager=package_manager,
        lockfile_present=lockfile_present,
        lockfile=lockfile,
        mcp_configured=mcp_configured,
        skills_present=skills_present,
        docker_configured=docker_configured,
        cli_tools_available=cli_tools_available,
    )


def detect_observability_signals(repo_path: Path) -> ObservabilityMechanicalSignals:
    """Check for observability-related libraries and configurations.

    Scans for structured logging, health endpoints, metrics, tracing,
    and log level configuration.
    """
    typer.echo("[scanner] detecting observability signals", err=True)

    structured_logging_lib = False
    health_endpoint = False
    metrics_lib = False
    tracing_lib = False
    log_level_configurable = False

    # Check dependency files for observability libraries
    _dep_content = _read_dependency_content(repo_path)

    # Structured logging
    logging_patterns = ["structlog", "winston", "pino", "bunyan", "tracing", "slog", "loguru"]
    structured_logging_lib = any(p in _dep_content for p in logging_patterns)

    # Also check for logging config in source
    if not structured_logging_lib:
        source_files = _filter_vendored(glob_mod.glob(str(repo_path / "**/*.py"), recursive=True))[
            :10
        ]
        for sf in source_files:
            try:
                content = Path(sf).read_text()
                if "logging.config" in content or "structlog" in content or "loguru" in content:
                    structured_logging_lib = True
                    break
            except OSError:
                pass

    # Health endpoints
    all_source = _collect_source_snippets(repo_path, limit=20)
    if re.search(r'["\'/]health[z]?["\']', all_source):
        health_endpoint = True

    # Metrics libs
    metrics_patterns = ["prometheus_client", "prom-client", "prometheus", "statsd", "datadog"]
    metrics_lib = any(p in _dep_content for p in metrics_patterns)

    # Tracing libs
    tracing_patterns = ["opentelemetry", "jaeger", "zipkin", "dd-trace", "sentry"]
    tracing_lib = any(p in _dep_content for p in tracing_patterns)

    # Log level configurable
    if re.search(r"log[_-]?level|LOG_LEVEL|logging\.setLevel|setLogLevel", all_source):
        log_level_configurable = True

    typer.echo(
        f"[scanner] observability: logging={structured_logging_lib}, "
        f"health={health_endpoint}, metrics={metrics_lib}, "
        f"tracing={tracing_lib}, log_level={log_level_configurable}",
        err=True,
    )

    return ObservabilityMechanicalSignals(
        structured_logging_lib=structured_logging_lib,
        health_endpoint=health_endpoint,
        metrics_lib=metrics_lib,
        tracing_lib=tracing_lib,
        log_level_configurable=log_level_configurable,
    )


def detect_isolation_signals(repo_path: Path) -> IsolationMechanicalSignals:
    """Check for isolation and reproducibility signals.

    Detects git repo, lockfiles, .env.example, potential committed secrets,
    and reproducible build indicators.
    """
    typer.echo("[scanner] detecting isolation signals", err=True)

    git_repo = (repo_path / ".git").exists()
    lockfile_present, _ = detect_lockfiles(repo_path)
    env_example_present = (repo_path / ".env.example").exists() or (
        repo_path / ".env.sample"
    ).exists()

    # Check for committed secrets (conservative scan)
    no_committed_secrets = True
    source_files = _get_tracked_files(repo_path)
    for sf in source_files[:50]:  # limit to 50 files
        try:
            content = Path(sf).read_text(errors="replace")
            for pattern in _SECRET_PATTERNS:
                if pattern.search(content):
                    no_committed_secrets = False
                    typer.echo(
                        f"[scanner] warning: potential secret in {sf}",
                        err=True,
                    )
                    break
        except OSError:
            pass
        if not no_committed_secrets:
            break

    # Reproducible build: lockfile + package manager config
    reproducible_build = lockfile_present and any(
        (repo_path / f).exists()
        for f in ["pyproject.toml", "package.json", "Cargo.toml", "go.mod", "Dockerfile"]
    )

    typer.echo(
        f"[scanner] isolation: git={git_repo}, lock={lockfile_present}, "
        f"env_example={env_example_present}, no_secrets={no_committed_secrets}, "
        f"reproducible={reproducible_build}",
        err=True,
    )

    return IsolationMechanicalSignals(
        git_repo=git_repo,
        lockfile_present=lockfile_present,
        env_example_present=env_example_present,
        no_committed_secrets=no_committed_secrets,
        reproducible_build=reproducible_build,
    )


def _read_dependency_content(repo_path: Path) -> str:
    """Read dependency file contents for library detection."""
    dep_files = ["pyproject.toml", "package.json", "Cargo.toml", "go.mod", "Gemfile"]
    contents: list[str] = []
    for dep_file in dep_files:
        path = repo_path / dep_file
        if path.exists():
            try:
                contents.append(path.read_text())
            except OSError:
                pass
    return "\n".join(contents)


def _collect_source_snippets(repo_path: Path, limit: int = 20) -> str:
    """Collect source code snippets for pattern matching."""
    patterns = ["**/*.py", "**/*.ts", "**/*.js", "**/*.rs", "**/*.go"]
    snippets: list[str] = []
    count = 0
    for pattern in patterns:
        for sf in _filter_vendored(glob_mod.glob(str(repo_path / pattern), recursive=True)):
            if count >= limit:
                break
            try:
                content = Path(sf).read_text(errors="replace")
                # Only first 200 lines of each file
                snippets.append("\n".join(content.splitlines()[:200]))
                count += 1
            except OSError:
                pass
        if count >= limit:
            break
    return "\n".join(snippets)


def _get_tracked_files(repo_path: Path) -> list[str]:
    """Get list of git-tracked files (non-binary)."""
    try:
        result = subprocess.run(
            ["git", "ls-files"],
            cwd=repo_path,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return [
                str(repo_path / f)
                for f in result.stdout.strip().split("\n")
                if f and not f.endswith((".png", ".jpg", ".gif", ".ico", ".woff", ".ttf", ".lock"))
            ]
    except FileNotFoundError:
        pass
    return []
