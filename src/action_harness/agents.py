"""Agent definition file loading: parse frontmatter, resolve paths, load prompts."""

import importlib.resources
from pathlib import Path

import typer
import yaml


def parse_agent_file(path: Path) -> tuple[dict[str, str], str]:
    """Parse frontmatter and body from an agent markdown file.

    Returns (metadata, body). Handles missing frontmatter (returns empty
    metadata with entire content as body) and malformed YAML (returns empty
    metadata, logs warning).
    """
    typer.echo(f"[agents] parsing agent file: {path}", err=True)
    try:
        content = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        typer.echo(f"[agents] failed to read {path}: {e}", err=True)
        raise

    if not content.startswith("---"):
        typer.echo(f"[agents] no frontmatter in {path.name}", err=True)
        return {}, content

    parts = content.split("---", 2)
    if len(parts) < 3:
        typer.echo(f"[agents] incomplete frontmatter delimiters in {path.name}", err=True)
        return {}, content

    try:
        raw_meta = yaml.safe_load(parts[1])
    except yaml.YAMLError as e:
        typer.echo(
            f"[agents] warning: malformed YAML frontmatter in {path.name}: {e}",
            err=True,
        )
        return {}, parts[2].strip()

    if not isinstance(raw_meta, dict):
        typer.echo(
            f"[agents] warning: frontmatter is not a mapping in {path.name}",
            err=True,
        )
        return {}, parts[2].strip()

    # Ensure all values are strings for the declared return type
    meta: dict[str, str] = {str(k): str(v) for k, v in raw_meta.items()}
    body = parts[2].strip()

    typer.echo(f"[agents] parsed {path.name}: metadata keys={list(meta.keys())}", err=True)
    return meta, body


def load_agent_prompt(agent_name: str, repo_path: Path, harness_agents_dir: Path) -> str:
    """Load agent persona prompt from disk.

    Check target repo override first, then harness defaults. Returns the
    body text (not metadata). Raises FileNotFoundError if neither exists.
    """
    typer.echo(
        f"[agents] loading prompt for '{agent_name}' "
        f"(repo={repo_path}, harness={harness_agents_dir})",
        err=True,
    )

    # 1. Target repo override
    repo_agent = repo_path / ".harness" / "agents" / f"{agent_name}.md"
    if repo_agent.is_file():
        typer.echo(f"[agents] using repo override: {repo_agent}", err=True)
        _, body = parse_agent_file(repo_agent)
        return body

    # 2. Harness default
    default_agent = harness_agents_dir / f"{agent_name}.md"
    if default_agent.is_file():
        typer.echo(f"[agents] using harness default: {default_agent}", err=True)
        _, body = parse_agent_file(default_agent)
        return body

    raise FileNotFoundError(f"No agent definition found for '{agent_name}'")


def resolve_harness_agents_dir() -> Path:
    """Resolve the path to the harness's default agent definitions.

    Tries source checkout first (walk up from this file to find
    .harness/agents/ in the repo root). Falls back to importlib.resources
    for installed-as-package support.
    """
    # Try source checkout: walk up from this file
    current = Path(__file__).resolve().parent
    for _ in range(10):  # Limit traversal depth
        candidate = current / ".harness" / "agents"
        if candidate.is_dir():
            typer.echo(f"[agents] resolved harness agents dir (source): {candidate}", err=True)
            return candidate
        parent = current.parent
        if parent == current:
            break
        current = parent

    # Fallback: installed package
    pkg_path = importlib.resources.files("action_harness") / "default_agents"
    resolved = Path(str(pkg_path))
    if not resolved.is_dir():
        typer.echo(
            f"[agents] warning: package fallback agents dir does not exist: {resolved}. "
            f"Agent definition files may be missing from the installation.",
            err=True,
        )
    else:
        typer.echo(f"[agents] resolved harness agents dir (package): {resolved}", err=True)
    return resolved
