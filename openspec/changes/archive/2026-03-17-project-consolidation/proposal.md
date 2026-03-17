# Project Consolidation

## Problem

After completing 30+ self-hosted changes, the project documentation has drifted from reality:

1. **ARCHITECTURE.md module map is stale** — lists 12 modules but the codebase has 32. Seventeen modules added post-bootstrap are undocumented.
2. **Orphaned proposal file** — `openspec/changes/proposal.md` (the original project proposal) sits loose in the changes directory. It's historical context, not an active change.
3. **Documentation hierarchy is unclear** — PROJECT_VISION.md, ARCHITECTURE.md, CLAUDE.md, HARNESS.md, and README.md have overlapping content with no guidance on which to consult for what.
4. **Agent definition locations undocumented** — `.harness/agents/` (6 files) and `.claude/agents/` (1 file) serve different purposes but this isn't explained anywhere.
5. **Research and exploration docs have no index** — 7 files across `docs/research/` and `docs/explore/` with no discoverability.
6. **README.md "How it works" section is stale** — describes only the bootstrap 6-stage pipeline, missing review agents, auto-merge, checkpoint resume, and other post-bootstrap capabilities.

## Solution

Update all project-level documentation to reflect the current state of the codebase. No code changes — documentation only.

## Validation

- All markdown files render correctly (no broken links within updated files)
- ARCHITECTURE.md module map matches actual `src/action_harness/` contents
- No orphaned files in `openspec/changes/` root
- `uv run pytest -v` still passes (no code changes)
- `uv run ruff check .` clean
- `uv run mypy src/` clean
