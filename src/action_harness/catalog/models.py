"""Pydantic models for catalog entries."""

from typing import Literal

from pydantic import BaseModel

# Canonical severity sort order: high first. Imported by loader and renderer.
SEVERITY_ORDER: dict[str, int] = {"high": 0, "medium": 1, "low": 2}


class CatalogEntry(BaseModel):
    """A single entry in the agent knowledge catalog.

    Each entry represents a class of bug or quality issue that agents
    should know about. Entries are stored as YAML files and loaded at
    dispatch time.
    """

    id: str
    entry_class: str
    severity: Literal["high", "medium", "low"]
    ecosystems: list[str]
    worker_rule: str
    reviewer_checklist: list[str]
    examples: dict[str, str] | None = None
    learned_from: list[dict[str, str]] | None = None
