## 1. Prerequisite Parsing [no dependencies]

- [x] 1.1 Create `src/action_harness/prerequisites.py` with `read_prerequisites(change_dir: Path) -> list[str]`. Reads `.openspec.yaml` from the change directory, extracts the `prerequisites` field (list of strings). Returns empty list if field is missing or file doesn't exist. Log warning on YAML parse errors (never crash).
- [x] 1.2 Add tests: change with `prerequisites: [repo-lead, always-on]` returns `["repo-lead", "always-on"]`. No `prerequisites` field returns `[]`. Missing `.openspec.yaml` returns `[]`. Malformed YAML logs warning and returns `[]`.

## 2. Readiness Computation [depends: 1]

- [x] 2.1 Add `is_prerequisite_satisfied(name: str, repo_path: Path) -> bool` to `prerequisites.py`. Returns True if: (a) any directory in `openspec/changes/archive/` ends with `-{name}` (glob pattern `*-{name}`), OR (b) `openspec/specs/{name}/` directory exists. Returns False otherwise.
- [x] 2.2 Add `compute_readiness(repo_path: Path) -> tuple[list[str], list[dict[str, str | list[str]]]]` to `prerequisites.py`. Scans `openspec/changes/` for active changes (non-archive directories with `.openspec.yaml`). For each, reads prerequisites and checks satisfaction. Returns `(ready_names, blocked_list)` where `blocked_list` items have `name` and `unmet_prerequisites` keys. Warns on unknown prerequisites (names not found as active, archived, or spec'd).
- [x] 2.3 Add tests: change with all prerequisites archived → ready. Change with unmet prerequisite → blocked with correct `unmet_prerequisites`. Change with no prerequisites → ready. Unknown prerequisite name → warning logged, treated as unmet. No active changes → empty lists.

## 3. CLI Command [depends: 2]

- [x] 3.1 Add `harness ready` command to `cli.py` with `--repo` (required Path) and `--json` (flag). Calls `compute_readiness`, displays formatted output (ready list + blocked list with unmet prerequisites). `--json` outputs `{"ready": [...], "blocked": [...]}` to stdout.
- [x] 3.2 Update CLI docstring for the `ready` command.
- [x] 3.3 Add tests: `--help` shows ready command. Command with ready changes displays them. Command with blocked changes shows unmet prerequisites. `--json` produces valid JSON with correct keys. No active changes outputs "No active changes found".

## 4. Lead Integration [depends: 2]

- [x] 4.1 In `lead.py:gather_lead_context`, add a "Ready Changes" section by calling `compute_readiness(repo_path)`. List ready change names. If no ready changes, note "No changes currently ready for implementation." Truncate to `max_section_chars` like other sections.
- [x] 4.2 Add test: `gather_lead_context` with active changes includes "Ready Changes" section.

## 5. Validation [depends: all]

- [x] 5.1 Run `uv run pytest -v` — all tests pass
- [x] 5.2 Run `uv run ruff check .` and `uv run mypy src/` — clean
