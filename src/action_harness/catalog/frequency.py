"""Per-repo finding frequency tracking — learns which catalog rules fire most often."""

import json
from datetime import UTC, datetime
from pathlib import Path

import typer

from action_harness.catalog.models import CatalogEntry
from action_harness.models import ReviewFinding

# Common stop words to exclude from keyword matching
_STOP_WORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "could",
        "should",
        "may",
        "might",
        "must",
        "shall",
        "can",
        "need",
        "dare",
        "to",
        "of",
        "in",
        "for",
        "on",
        "with",
        "at",
        "by",
        "from",
        "as",
        "into",
        "through",
        "during",
        "before",
        "after",
        "above",
        "below",
        "between",
        "out",
        "off",
        "over",
        "under",
        "again",
        "further",
        "then",
        "once",
        "here",
        "there",
        "when",
        "where",
        "why",
        "how",
        "all",
        "each",
        "every",
        "both",
        "few",
        "more",
        "most",
        "other",
        "some",
        "such",
        "no",
        "nor",
        "not",
        "only",
        "own",
        "same",
        "so",
        "than",
        "too",
        "very",
        "just",
        "because",
        "but",
        "and",
        "or",
        "if",
        "while",
        "about",
        "up",
        "that",
        "this",
        "it",
        "its",
        "include",
        "includes",
        "always",
        "never",
        "use",
        "using",
        "used",
        "ensure",
    }
)

# Minimum fraction of rule keywords that must appear in a finding for
# criterion (b) to match. Full-subset (1.0) is too strict for long rules
# that include examples/context. Seed entry rules have 12-19 keywords;
# a real finding typically shares 3-5 core keywords (~25-30%). The minimum
# match count of 3 prevents single-word false positives.
_KEYWORD_OVERLAP_THRESHOLD = 0.25
_KEYWORD_OVERLAP_MIN_MATCHES = 3

FREQUENCY_FILENAME = "findings-frequency.json"


def _extract_keywords(text: str) -> set[str]:
    """Extract non-stop-word keywords from text, lowercased.

    Splits on whitespace and common punctuation boundaries, filtering out
    stop words and very short tokens.
    """
    # Replace common punctuation with spaces for splitting
    normalized = text.lower()
    for char in "()[]{}.,;:!?\"'/\\=-`#@+*~^<>|":
        normalized = normalized.replace(char, " ")
    words = normalized.split()
    return {w for w in words if w not in _STOP_WORDS and len(w) >= 2}


def _finding_matches_entry(finding: ReviewFinding, entry: CatalogEntry) -> bool:
    """Check if a review finding matches a catalog entry.

    Match criteria:
    (a) The entry's ``id`` appears as a case-insensitive substring of
        ``finding.title`` or ``finding.description``, OR
    (b) At least ``_KEYWORD_OVERLAP_THRESHOLD`` (50%) of non-stop-words
        from the entry's ``worker_rule`` appear (case-insensitive) in
        ``finding.title + finding.description``. A threshold is used
        instead of full subset because seed entry rules include examples
        and context that won't appear in finding text.
    """
    finding_text = f"{finding.title} {finding.description}".lower()

    # (a) ID substring match
    if entry.id.lower() in finding_text:
        return True

    # (b) Keyword overlap above threshold
    rule_keywords = _extract_keywords(entry.worker_rule)
    if not rule_keywords:
        return False

    finding_keywords = _extract_keywords(finding_text)
    overlap = len(rule_keywords & finding_keywords)
    return (
        overlap >= _KEYWORD_OVERLAP_MIN_MATCHES
        and overlap / len(rule_keywords) >= _KEYWORD_OVERLAP_THRESHOLD
    )


def _load_frequency_file(frequency_path: Path) -> dict[str, dict[str, str | int]]:
    """Load the frequency JSON file, returning empty dict if missing or invalid."""
    if not frequency_path.exists():
        return {}
    try:
        raw = frequency_path.read_text(encoding="utf-8")
        data = json.loads(raw)
        if isinstance(data, dict):
            return data
        typer.echo(
            f"[catalog] warning: frequency file is not a JSON object: {frequency_path}",
            err=True,
        )
        return {}
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        typer.echo(
            f"[catalog] warning: could not read frequency file {frequency_path}: {exc}",
            err=True,
        )
        return {}


def update_frequency(
    repo_knowledge_dir: Path,
    catalog_entries: list[CatalogEntry],
    findings: list[ReviewFinding],
) -> None:
    """Update the per-repo finding frequency file.

    For each finding, attempts to match against catalog entries. On match,
    increments the count and updates ``last_seen`` in
    ``repo_knowledge_dir/findings-frequency.json``.
    """
    typer.echo(
        f"[catalog] updating frequency: {len(findings)} findings, {len(catalog_entries)} entries",
        err=True,
    )

    frequency_path = repo_knowledge_dir / FREQUENCY_FILENAME
    frequency = _load_frequency_file(frequency_path)
    today = datetime.now(UTC).strftime("%Y-%m-%d")

    matches_found = 0
    for finding in findings:
        for entry in catalog_entries:
            if _finding_matches_entry(finding, entry):
                existing = frequency.get(entry.id, {"count": 0, "last_seen": ""})
                count = existing.get("count", 0)
                if not isinstance(count, int):
                    count = 0
                frequency[entry.id] = {
                    "count": count + 1,
                    "last_seen": today,
                }
                matches_found += 1
                break  # One match per finding

    if matches_found > 0:
        try:
            repo_knowledge_dir.mkdir(parents=True, exist_ok=True)
            frequency_path.write_text(
                json.dumps(frequency, indent=2),
                encoding="utf-8",
            )
        except OSError as exc:
            typer.echo(
                f"[catalog] warning: could not write frequency file: {exc}",
                err=True,
            )

    typer.echo(
        f"[catalog] frequency update: {matches_found} matches from {len(findings)} findings",
        err=True,
    )


def get_boosted_entries(
    repo_knowledge_dir: Path,
    catalog_entries: list[CatalogEntry],
    threshold: int = 3,
) -> list[CatalogEntry]:
    """Return catalog entries with finding frequency >= threshold.

    These are the repo's "hot rules" — entries that fire frequently for
    this specific repo. Returns entries sorted by frequency (highest first).
    """
    frequency_path = repo_knowledge_dir / FREQUENCY_FILENAME
    frequency = _load_frequency_file(frequency_path)

    if not frequency:
        return []

    boosted: list[tuple[int, CatalogEntry]] = []
    for entry in catalog_entries:
        entry_data = frequency.get(entry.id, {})
        count = entry_data.get("count", 0)
        if not isinstance(count, int):
            count = 0
        if count >= threshold:
            boosted.append((count, entry))

    # Sort by frequency descending
    boosted.sort(key=lambda t: t[0], reverse=True)
    return [entry for _, entry in boosted]
