"""Prerequisites: read, check, and compute readiness for OpenSpec changes."""

from pathlib import Path

import typer
import yaml


def read_prerequisites(change_dir: Path) -> list[str]:
    """Read the prerequisites field from a change's .openspec.yaml.

    Returns a list of prerequisite change names. Returns empty list if the
    file doesn't exist, the field is missing, or YAML is malformed.
    """
    typer.echo(f"[prerequisites] reading prerequisites from {change_dir}", err=True)
    yaml_path = change_dir / ".openspec.yaml"

    if not yaml_path.is_file():
        typer.echo(
            f"[prerequisites] no .openspec.yaml in {change_dir}",
            err=True,
        )
        return []

    try:
        content = yaml_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        typer.echo(
            f"[prerequisites] warning: could not read {yaml_path}: {exc}",
            err=True,
        )
        return []

    try:
        data = yaml.safe_load(content)
    except yaml.YAMLError as exc:
        typer.echo(
            f"[prerequisites] warning: malformed YAML in {yaml_path}: {exc}",
            err=True,
        )
        return []

    if not isinstance(data, dict):
        typer.echo(
            f"[prerequisites] warning: .openspec.yaml is not a mapping in {change_dir}",
            err=True,
        )
        return []

    prereqs = data.get("prerequisites")
    if prereqs is None:
        typer.echo(
            f"[prerequisites] no prerequisites field in {change_dir}",
            err=True,
        )
        return []

    if not isinstance(prereqs, list):
        typer.echo(
            f"[prerequisites] warning: prerequisites is not a list in {change_dir}",
            err=True,
        )
        return []

    result = [str(p) for p in prereqs]
    typer.echo(
        f"[prerequisites] found {len(result)} prerequisite(s) in {change_dir}",
        err=True,
    )
    return result


def _extract_archive_change_name(dir_name: str) -> str | None:
    """Extract the change name from an archive directory name.

    Archive dirs are formatted as YYYY-MM-DD-<change-name>.
    Returns the change name, or None if the format doesn't match.
    """
    parts = dir_name.split("-", 3)
    if len(parts) >= 4:
        return "-".join(parts[3:])
    return None


def is_prerequisite_satisfied(name: str, repo_path: Path) -> bool:
    """Check if a prerequisite is satisfied.

    A prerequisite is satisfied when:
    (a) any directory in openspec/changes/archive/ has change name matching
        {name} (archive dirs are YYYY-MM-DD-{name}), OR
    (b) openspec/specs/{name}/ directory exists.

    Returns False otherwise.
    """
    typer.echo(f"[prerequisites] checking if '{name}' is satisfied", err=True)

    # Check archive directories — extract change name from date-prefixed dir
    archive_dir = repo_path / "openspec" / "changes" / "archive"
    if archive_dir.is_dir():
        for entry in archive_dir.iterdir():
            if entry.is_dir() and _extract_archive_change_name(entry.name) == name:
                typer.echo(
                    f"[prerequisites] '{name}' satisfied: archived at {entry.name}",
                    err=True,
                )
                return True

    # Check specs directory
    specs_dir = repo_path / "openspec" / "specs" / name
    if specs_dir.is_dir():
        typer.echo(
            f"[prerequisites] '{name}' satisfied: spec exists at {specs_dir}",
            err=True,
        )
        return True

    typer.echo(f"[prerequisites] '{name}' not satisfied", err=True)
    return False


def compute_readiness(
    repo_path: Path,
) -> tuple[list[str], list[dict[str, str | list[str]]]]:
    """Compute which active changes are ready and which are blocked.

    Scans openspec/changes/ for active changes (non-archive directories with
    .openspec.yaml). For each, reads prerequisites and checks satisfaction.

    Returns (ready_names, blocked_list) where blocked_list items have
    'name' and 'unmet_prerequisites' keys.
    """
    typer.echo(f"[prerequisites] computing readiness for {repo_path}", err=True)

    changes_dir = repo_path / "openspec" / "changes"
    if not changes_dir.is_dir():
        typer.echo("[prerequisites] no openspec/changes/ directory found", err=True)
        return [], []

    # Collect all known change names upfront for unknown-prerequisite warnings
    archive_dir = changes_dir / "archive"
    archived_names: set[str] = set()
    if archive_dir.is_dir():
        for entry in archive_dir.iterdir():
            if entry.is_dir():
                extracted = _extract_archive_change_name(entry.name)
                if extracted is not None:
                    archived_names.add(extracted)

    specs_dir = repo_path / "openspec" / "specs"
    specced_names: set[str] = set()
    if specs_dir.is_dir():
        for entry in specs_dir.iterdir():
            if entry.is_dir():
                specced_names.add(entry.name)

    # First pass: collect all active change names so prerequisite lookups
    # don't depend on iteration order
    active_entries: list[Path] = []
    active_names: set[str] = set()
    for entry in sorted(changes_dir.iterdir()):
        if not entry.is_dir():
            continue
        if entry.name == "archive":
            continue
        if not (entry / ".openspec.yaml").is_file():
            continue
        active_entries.append(entry)
        active_names.add(entry.name)

    # Second pass: compute readiness
    ready_names: list[str] = []
    blocked_list: list[dict[str, str | list[str]]] = []

    for entry in active_entries:
        prereqs = read_prerequisites(entry)

        if not prereqs:
            ready_names.append(entry.name)
            continue

        unmet: list[str] = []
        for prereq_name in prereqs:
            # Warn about unknown prerequisites
            known = (
                prereq_name in active_names
                or prereq_name in archived_names
                or prereq_name in specced_names
            )
            if not known:
                typer.echo(
                    f"[prerequisites] warning: unknown prerequisite '{prereq_name}' "
                    f"in change '{entry.name}' — not found as active, archived, or spec'd",
                    err=True,
                )

            if not is_prerequisite_satisfied(prereq_name, repo_path):
                unmet.append(prereq_name)

        if unmet:
            blocked_list.append({"name": entry.name, "unmet_prerequisites": unmet})
        else:
            ready_names.append(entry.name)

    typer.echo(
        f"[prerequisites] result: {len(ready_names)} ready, {len(blocked_list)} blocked",
        err=True,
    )
    return ready_names, blocked_list
