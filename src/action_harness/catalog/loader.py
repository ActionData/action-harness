"""Catalog loader — reads YAML entries and filters by ecosystem."""

from pathlib import Path

import typer
import yaml
from pydantic import ValidationError

from action_harness.catalog.models import CatalogEntry

# Severity sort order: high first
_SEVERITY_ORDER: dict[str, int] = {"high": 0, "medium": 1, "low": 2}

# Default entries directory relative to this file
_DEFAULT_ENTRIES_DIR = Path(__file__).parent / "entries"


def load_catalog(
    ecosystem: str,
    entries_dir: Path | None = None,
) -> list[CatalogEntry]:
    """Load catalog entries filtered by ecosystem.

    Reads all ``.yaml`` files from ``entries_dir`` (default:
    ``src/action_harness/catalog/entries/``), parses each into a
    ``CatalogEntry``, and filters to entries where ``ecosystem`` is in
    ``entry.ecosystems`` or ``"all"`` is in ``entry.ecosystems``.

    Returns entries sorted by severity (high first). Skips invalid YAML
    files with a warning logged to stderr.
    """
    resolved_dir = entries_dir if entries_dir is not None else _DEFAULT_ENTRIES_DIR

    typer.echo(f"[catalog] loading entries from {resolved_dir} (ecosystem={ecosystem})", err=True)

    if not resolved_dir.is_dir():
        typer.echo(f"[catalog] entries directory does not exist: {resolved_dir}", err=True)
        return []

    entries: list[CatalogEntry] = []
    yaml_files = sorted(resolved_dir.glob("*.yaml"))

    for yaml_file in yaml_files:
        try:
            raw_text = yaml_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            typer.echo(
                f"[catalog] warning: could not read {yaml_file.name}: {exc}",
                err=True,
            )
            continue

        try:
            data = yaml.safe_load(raw_text)
        except yaml.YAMLError as exc:
            typer.echo(
                f"[catalog] warning: invalid YAML in {yaml_file.name}: {exc}",
                err=True,
            )
            continue

        if not isinstance(data, dict):
            typer.echo(
                f"[catalog] warning: {yaml_file.name} does not contain a YAML mapping",
                err=True,
            )
            continue

        # Remap 'class' -> 'entry_class' to avoid Python keyword conflict
        if "class" in data and "entry_class" not in data:
            data["entry_class"] = data.pop("class")

        try:
            entry = CatalogEntry(**data)
        except (ValidationError, TypeError) as exc:
            typer.echo(
                f"[catalog] warning: invalid entry in {yaml_file.name}: {exc}",
                err=True,
            )
            continue

        entries.append(entry)

    # Filter by ecosystem
    filtered = [
        e
        for e in entries
        if ecosystem in e.ecosystems or "all" in e.ecosystems
    ]

    # Sort by severity (high first)
    filtered.sort(key=lambda e: _SEVERITY_ORDER.get(e.severity, 99))

    typer.echo(
        f"[catalog] loaded {len(filtered)} entries (of {len(entries)} total) "
        f"for ecosystem '{ecosystem}'",
        err=True,
    )

    return filtered
