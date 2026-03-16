"""Catalog renderers — produce prompt sections for workers and reviewers."""

from action_harness.catalog.models import SEVERITY_ORDER, CatalogEntry


def render_for_worker(
    entries: list[CatalogEntry],
    top_n: int = 10,
    boosted: list[CatalogEntry] | None = None,
) -> str | None:
    """Render a concise ``## Quality Rules`` section for the worker prompt.

    Returns the top N entries' ``worker_rule`` as bullets, sorted by severity
    descending. Returns None if no entries (caller skips injection).

    When ``boosted`` entries are provided (repo-specific "hot rules"), up to 2
    extra entries are appended after the top N.
    """
    if not entries and not boosted:
        return None

    # Sort by severity (high first)
    sorted_entries = sorted(entries, key=lambda e: SEVERITY_ORDER.get(e.severity, 99))
    selected = sorted_entries[:top_n]

    if not selected and not boosted:
        return None

    lines = ["## Quality Rules", ""]
    for entry in selected:
        lines.append(f"- {entry.worker_rule}")

    # Append boosted entries (up to 2 extra slots)
    if boosted:
        # Exclude entries already in selected
        selected_ids = {e.id for e in selected}
        extra = [e for e in boosted if e.id not in selected_ids][:2]
        for entry in extra:
            lines.append(f"- [repo-frequent] {entry.worker_rule}")

    return "\n".join(lines)


def render_for_reviewer(entries: list[CatalogEntry]) -> str | None:
    """Render a detailed ``## Catalog Checklist`` section for review agents.

    Returns a section with each entry's id, checklist items, and examples.
    Returns None if no entries.
    """
    if not entries:
        return None

    lines = ["## Catalog Checklist", ""]

    for entry in entries:
        lines.append(f"### {entry.id} ({entry.severity})")
        for item in entry.reviewer_checklist:
            lines.append(f"- {item}")
        if entry.examples:
            if "bad" in entry.examples:
                lines.append(f"- Bad: `{entry.examples['bad']}`")
            if "good" in entry.examples:
                lines.append(f"- Good: `{entry.examples['good']}`")
        lines.append("")

    return "\n".join(lines)
