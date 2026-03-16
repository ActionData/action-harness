## 1. Catalog Models and Loader [no dependencies]

- [ ] 1.1 Create `src/action_harness/catalog/__init__.py` and `src/action_harness/catalog/models.py` with a `CatalogEntry` Pydantic model: `id: str`, `entry_class: str` (renamed from `class` to avoid Python keyword), `severity: Literal["high", "medium", "low"]`, `ecosystems: list[str]`, `worker_rule: str`, `reviewer_checklist: list[str]`, `examples: dict[str, str] | None = None` (bad/good), `learned_from: list[dict[str, str]] | None = None`.
- [ ] 1.2 Create `src/action_harness/catalog/loader.py` with `load_catalog(ecosystem: str, entries_dir: Path | None = None) -> list[CatalogEntry]`. Reads all `.yaml` files from `entries_dir` (default: `src/action_harness/catalog/entries/`), parses each into `CatalogEntry`, filters to entries where `ecosystem` is in `entry.ecosystems` or `"all"` is in `entry.ecosystems`. Returns sorted by severity (high first).
- [ ] 1.3 Add tests: load with ecosystem "python" returns Python + "all" entries. Load with "unknown" returns only "all" entries. Load with "javascript" excludes Python-only entries. Invalid YAML file is skipped with a warning. Empty entries directory returns empty list.

## 2. Seed Catalog Entries [depends: 1]

- [ ] 2.1 Create `src/action_harness/catalog/entries/` directory with YAML files for the 10 entries identified from PRs #31-35: `subprocess-timeout.yaml`, `bare-assert-narrowing.yaml`, `type-ignore-ban.yaml`, `regex-word-boundary.yaml`, `generic-error-messages.yaml`, `validate-before-operate.yaml`, `inconsistent-error-handling.yaml`, `duplicated-utility.yaml`, `dry-run-mismatch.yaml`, `string-field-access.yaml`. Map to research doc classes: defensive-io, language-pitfall, language-pitfall, pattern-safety, error-clarity, ordering, consistency, DRY, preview-fidelity, stringly-typed. Use the examples and provenance from `docs/research/agent-quality-catalog.md`.
- [ ] 2.2 Add test: verify all 10 entries load successfully and have valid fields. Verify at least 6 are tagged with `ecosystems: [python]` and at least 3 with `ecosystems: [all]`.

## 3. Renderer [depends: 1]

- [ ] 3.1 Create `src/action_harness/catalog/renderer.py` with `render_for_worker(entries: list[CatalogEntry], top_n: int = 10) -> str | None`. Returns a `## Quality Rules` section with the top N entries' `worker_rule` as bullets. Returns None if no entries (caller skips injection). Sort by severity descending.
- [ ] 3.2 Add `render_for_reviewer(entries: list[CatalogEntry]) -> str | None`. Returns a `## Catalog Checklist` section with each entry's id, checklist items, and examples. Returns None if no entries.
- [ ] 3.3 Add tests: `render_for_worker` with 15 entries and `top_n=10` returns 10 lines. With 3 entries returns 3. With 0 entries returns None. `render_for_reviewer` includes checklist items and example code.

## 4. Worker Prompt Injection [depends: 2, 3]

- [ ] 4.1 In `dispatch_worker()` in `worker.py`, after injecting HARNESS.md: call `load_catalog(ecosystem)` where `ecosystem` comes from the profiler (already available via the pipeline). Call `render_for_worker(entries)`. If the result is not None, append it to the system prompt.
- [ ] 4.2 The ecosystem needs to be passed to `dispatch_worker`. Add `ecosystem: str = "unknown"` parameter. The pipeline already has `profile.ecosystem` — pass it through.
- [ ] 4.3 Add tests: worker dispatched with `ecosystem="python"` — verify system prompt contains `## Quality Rules` with Python-relevant entries. Worker with `ecosystem="unknown"` — verify only universal rules appear. Worker with no matching entries — verify no `## Quality Rules` section.

## 5. Review Agent Prompt Injection [depends: 2, 3]

- [ ] 5.1 In `build_review_prompt()` in `review_agents.py`, append the catalog reviewer checklist to the system prompt. Call `load_catalog(ecosystem)` and `render_for_reviewer(entries)`. Append to the system prompt string.
- [ ] 5.2 Thread `ecosystem` through the full review prompt call chain: add `ecosystem: str = "unknown"` to `dispatch_review_agents()`, `dispatch_single_review()`, and `build_review_prompt()`. In `dispatch_review_agents`, pass `ecosystem` to each `executor.submit(dispatch_single_review, ...)` call. In `dispatch_single_review`, pass it to `build_review_prompt()`.
- [ ] 5.3 Add tests: review agent prompt with `ecosystem="python"` contains `## Catalog Checklist` with Python entries. Prompt with no matching entries has no checklist section.

## 6. Per-Repo Finding Frequency [depends: 2]

- [ ] 6.1 Create `src/action_harness/catalog/frequency.py` with `update_frequency(repo_knowledge_dir: Path, catalog_entries: list[CatalogEntry], findings: list[ReviewFinding]) -> None`. For each finding, match against catalog entries using: (a) the entry's `id` as a case-insensitive substring of `finding.title` or `finding.description`, OR (b) ALL non-stop-words from the entry's `worker_rule` (case-insensitive) appear in `finding.title + finding.description`. If matched, increment the count in `findings-frequency.json` and update `last_seen`. Test example: finding `"subprocess.run call missing timeout parameter"` SHALL match entry `subprocess-timeout` with rule `"Every subprocess.run() must include timeout="` because "subprocess", "run", "timeout" all appear.
- [ ] 6.2 Add `get_boosted_entries(repo_knowledge_dir: Path, catalog_entries: list[CatalogEntry], threshold: int = 3) -> list[CatalogEntry]`. Returns entries with frequency count >= threshold that aren't already in the top N by severity. These are the repo's "hot rules".
- [ ] 6.3 Update `render_for_worker` to accept optional `boosted: list[CatalogEntry]`. When boosted entries exist, add them after the top N (up to 2 extra slots).
- [ ] 6.4 Add tests: `update_frequency` creates file on first match, increments on subsequent. `get_boosted_entries` returns entries above threshold. Renderer with boosted entries includes them.

## 7. Pipeline Integration [depends: 4, 5, 6]

- [ ] 7.1 In `_run_pipeline_inner()`, after review rounds complete: call `update_frequency` with the review findings and catalog entries. Use the harness home `repos/<repo_name>/knowledge/` path.
- [ ] 7.2 Thread `ecosystem` from `profile.ecosystem` through to `dispatch_worker` and `dispatch_review_agents` in ALL call sites. The full list of functions needing `ecosystem: str = "unknown"` added to their signatures: `_run_pipeline_inner`, `_run_review_fix_retry`, `_run_review_agents_only`. Call sites for `dispatch_worker`: main loop (~line 376), resume fallback (~line 406), fix-retry (~line 1010), fix-retry resume fallback (~line 1033). Call sites for `dispatch_review_agents`: `_run_review_agents_only` (~line 884). Thread `ecosystem` through each intermediate function to the dispatch call.
- [ ] 7.3 Add tests: verify `dispatch_worker` receives `ecosystem` matching the profiler. Verify `dispatch_review_agents` receives `ecosystem`. Verify `update_frequency` is called after review rounds.

## 8. Validation [depends: all]

- [ ] 8.1 Run `uv run pytest -v` — all tests pass
- [ ] 8.2 Run `uv run ruff check .` and `uv run mypy src/` — clean
- [ ] 8.3 Run `harness run --change <test> --repo . --dry-run` and verify no errors from catalog loading
