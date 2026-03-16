## Why

Across 5 harness runs (PRs #31-35), review agents found the same classes of bugs repeatedly: missing subprocess timeouts, bare assert for type narrowing, unanchored regex, generic error messages, validation ordering, inconsistent error handling, DRY violations. These are universal patterns — they apply to any Python codebase, and many are language-agnostic.

Currently, the harness detects these issues AFTER implementation via review agents. The catalog moves prevention BEFORE implementation: the worker gets the top rules before writing code, and the review agents get a richer checklist. The per-repo knowledge store tracks which rules fire most often, so the harness gets smarter over time for each repo.

## What Changes

- YAML catalog of bug/quality issue entries at `src/action_harness/catalog/entries/`
- Catalog loader that filters entries by ecosystem (Python, JS, Rust, etc.)
- Renderer that produces: concise worker rules (top N by severity), detailed reviewer checklists, assessment scoring criteria
- Worker system prompt injection: top rules from the catalog added to the worker prompt at dispatch time
- Review agent prompt enrichment: full checklist injected into review agent system prompts
- Per-repo knowledge store: JSON file tracking finding frequency per catalog entry, stored in harness home

## Capabilities

### New Capabilities
- `knowledge-catalog`: Structured catalog of bug/quality issue classes with ecosystem filtering, multi-format rendering (worker rules, reviewer checklists, assessment criteria), and per-repo finding frequency tracking.

### Modified Capabilities
None — worker and review agent prompts are enhanced, not changed.

## Impact

- New module: `src/action_harness/catalog/` — entries (YAML), loader, renderer
- `worker.py` — inject catalog worker rules into system prompt
- `review_agents.py` — inject catalog reviewer checklist into review agent system prompts
- `~/.harness/repos/<repo>/knowledge/` — per-repo finding frequency JSON
- Builds on: `profiler.py` (ecosystem detection), `codebase-assessment` (scoring integration)

## Prerequisites

None — the catalog is a standalone addition. Ecosystem detection from `profiler.py` is already available.

See `docs/research/agent-quality-catalog.md` for the full research behind this change.
