## Why

The CLI has no way to check what version is installed. A `--version` flag is standard for CLI tools and useful for debugging.

## What Changes

- Add `--version` flag to the CLI that prints the version from `__init__.py`
- Add `__version__` string to `src/action_harness/__init__.py`

## Capabilities

### New Capabilities

- `version-flag`: CLI `--version` flag that prints the package version

### Modified Capabilities

## Impact

- `src/action_harness/__init__.py` — add `__version__`
- `src/action_harness/cli.py` — add version callback
- `tests/test_cli.py` — test for `--version` output
