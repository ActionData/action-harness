"""Prompt-to-slug conversion for branch naming."""

import re


def slugify_prompt(prompt: str, max_length: int = 50) -> str:
    """Convert a prompt to a branch-safe slug.

    Takes the first line only, lowercases, replaces non-alphanumeric chars
    with hyphens, collapses consecutive hyphens, strips leading/trailing
    hyphens, and truncates to max_length.
    """
    # Take first line only
    first_line = prompt.split("\n", maxsplit=1)[0]

    # Lowercase
    slug = first_line.lower()

    # Replace non-alphanumeric chars with hyphens
    slug = re.sub(r"[^a-z0-9]", "-", slug)

    # Collapse consecutive hyphens
    slug = re.sub(r"-{2,}", "-", slug)

    # Strip leading/trailing hyphens
    slug = slug.strip("-")

    # Truncate to max_length
    slug = slug[:max_length]

    # Strip trailing hyphens after truncation
    slug = slug.rstrip("-")

    return slug
