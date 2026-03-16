"""Shared parsing utilities for extracting structured data from LLM output."""

import json
import re
from typing import Any


def extract_json_block(text: str) -> dict[str, Any] | None:
    """Extract a JSON object from text that may contain surrounding prose.

    Tries to parse the entire text as JSON first. If that fails, looks for
    a JSON block delimited by ```json ... ``` or braces.
    """
    # Try the whole text first
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            return data
    except (json.JSONDecodeError, TypeError):
        pass

    if not isinstance(text, str):
        return None

    # Look for ```json ... ``` fenced block
    fenced = re.search(r"```json\s*\n(.*?)```", text, re.DOTALL)
    if fenced:
        try:
            data = json.loads(fenced.group(1))
            if isinstance(data, dict):
                return data
        except json.JSONDecodeError:
            pass

    # Try each { position from the start to find the outermost JSON object.
    # Starting from the first brace handles nested JSON correctly (e.g.
    # {"categories": {"ci": ...}}) — rfind would start at an inner brace.
    pos = 0
    while True:
        brace_start = text.find("{", pos)
        if brace_start == -1:
            break

        # Find matching closing brace
        depth = 0
        for i in range(brace_start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        data = json.loads(text[brace_start : i + 1])
                        if isinstance(data, dict):
                            return data
                    except json.JSONDecodeError:
                        pass
                    break

        pos = brace_start + 1

    return None
