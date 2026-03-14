## Context

The CLI needs a `--version` flag. Standard typer pattern.

## Goals / Non-Goals

**Goals:**
- `action-harness --version` prints the version and exits

**Non-Goals:**
- Version auto-detection from git tags or pyproject.toml at runtime

## Decisions

### 1. Version string in `__init__.py`

Define `__version__ = "0.1.0"` in `src/action_harness/__init__.py`. The CLI imports and uses it. This is the standard Python convention.

### 2. Typer version callback

Use typer's callback pattern: a `--version` option on the app callback that prints the version and raises `typer.Exit()`.
