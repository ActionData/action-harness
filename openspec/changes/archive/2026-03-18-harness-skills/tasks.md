## 1. Skill Discovery Module

- [x] 1.1 Create `src/action_harness/skills.py` with `resolve_harness_skills_dir()` that walks up from `__file__` to find `.claude/skills/` in the harness repo root (same pattern as `resolve_harness_agents_dir()` in `agents.py`). Returns the path. Falls back to importlib.resources.
- [x] 1.2 Add `discover_skills(skills_dir: Path) -> list[str]` that scans a directory for subdirectories containing `SKILL.md` and returns their names sorted.
- [x] 1.3 Add `inject_skills(source_dir: Path, worktree_path: Path, verbose: bool = False) -> list[str]` that copies skill directories from source to `worktree_path/.claude/skills/`, skipping existing ones. Writes `.harness-injected` marker. Returns list of injected skill names. Logs entry/exit to stderr. Catches OSError gracefully.

## 2. Pipeline Integration

- [x] 2.1 In `pipeline.py`, import `inject_skills` and `resolve_harness_skills_dir` from `skills.py`. After the worktree is created and before `dispatch_worker()`, call `inject_skills()` to copy harness skills into the worktree. Pass `verbose` flag through. Log the count of injected skills.

## 3. Tests

- [x] 3.1 Add `tests/test_skills.py` with tests for: `resolve_harness_skills_dir()` returns a valid path, `discover_skills()` finds skill directories, `discover_skills()` ignores directories without SKILL.md, `inject_skills()` copies skills into target, `inject_skills()` skips existing skills (precedence), `inject_skills()` writes `.harness-injected` marker, `inject_skills()` handles missing source dir gracefully.

## 4. Validation

- [x] 4.1 Run full validation suite: `uv run pytest -v`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy src/` — all must pass with no errors.
