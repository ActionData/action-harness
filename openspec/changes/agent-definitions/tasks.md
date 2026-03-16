## 1. Agent Definition Files

- [x] 1.1 Create `.harness/agents/bug-hunter.md` — port from `~/.claude/agents/bug-hunter.md` with frontmatter (`name`, `description`). Include: persona, "What to hunt for" section, "How to work" section (read CLAUDE.md, get PR diff via `gh pr diff {pr_number}`, read full files, trace data flow), "Rules" section. Do NOT include JSON output format or severity definitions — the harness appends those.
- [x] 1.2 Create `.harness/agents/test-reviewer.md` — port from `~/.claude/agents/test-reviewer.md` with same structure. Include test coverage, correctness, edge cases, isolation, flakiness sections. Prompt must contain `{pr_number}` placeholder.
- [x] 1.3 Create `.harness/agents/quality-reviewer.md` — port from `~/.claude/agents/quality-reviewer.md` with same structure. Include convention adherence, CLAUDE.md grounding rule, spec compliance sections. Prompt must contain `{pr_number}` placeholder.
- [x] 1.4 Create `.harness/agents/spec-compliance-reviewer.md` — port from `_AGENT_PROMPTS["spec-compliance-reviewer"]` in `review_agents.py`. Include the task-verification workflow, custom severity definitions (critical/high/medium/low specific to spec compliance). This agent defines its own severity scale, so severity definitions MUST be in the persona file. Prompt must contain `{pr_number}` placeholder.
- [x] 1.5 Create `.harness/agents/openspec-reviewer.md` — extract the persona portion from `REVIEW_SYSTEM_PROMPT` in `openspec_reviewer.py`. Keep `{change_name}` placeholders for templating. Include the step-by-step review instructions (read tasks.md, run `openspec validate`, semantic review, archive if ready, HUMAN task handling). Do NOT include the JSON output block (`"status": "approved"...` etc.) — that stays in Python.

## 2. File Loading Infrastructure

- [x] 2.1 Create `src/action_harness/agents.py`. Add `parse_agent_file(path: Path) -> tuple[dict[str, str], str]`. Split content on `---` delimiters, parse YAML frontmatter via `yaml.safe_load`, return `(metadata, body)`. Handle: no frontmatter (return `({}, full_content)`), malformed YAML (return `({}, full_content)`, log warning via `typer.echo(..., err=True)`).
- [x] 2.2 Add `load_agent_prompt(agent_name: str, repo_path: Path, harness_agents_dir: Path) -> str` to `agents.py`. Check `<repo_path>/.harness/agents/<agent_name>.md` first, then `<harness_agents_dir>/<agent_name>.md`. Parse via `parse_agent_file`, return the body text (not metadata). Raise `FileNotFoundError(f"No agent definition found for '{agent_name}'")` if neither exists.
- [x] 2.3 Add `resolve_harness_agents_dir() -> Path` to `agents.py`. Try source checkout first: walk up from `Path(__file__)` to find `.harness/agents/` in the repo root. If not found (installed as package), use `importlib.resources.files("action_harness") / "default_agents"`. Log the resolved path via `typer.echo` at verbose level.

## 3. Wire Into Review Agents

- [x] 3.1 In `review_agents.py`, remove the `_AGENT_PROMPTS` dict (lines 28–113). Update `build_review_prompt` signature to `build_review_prompt(agent_name: str, pr_number: int, repo_path: Path, harness_agents_dir: Path, ecosystem: str = "unknown") -> str`. The function SHALL: (a) call `load_agent_prompt(agent_name, repo_path, harness_agents_dir)` to get the persona, (b) format `{pr_number}` in the result, (c) append `_JSON_OUTPUT_FORMAT`, (d) conditionally append `_GENERIC_SEVERITY_SUFFIX` (skip if agent is in `_AGENTS_WITH_CUSTOM_SEVERITY`), (e) call `load_catalog(ecosystem)` and append `render_for_reviewer(catalog_entries)` if non-None. Keep `_JSON_OUTPUT_FORMAT`, `_GENERIC_SEVERITY_SUFFIX`, and `_AGENTS_WITH_CUSTOM_SEVERITY` as module-level constants.
- [x] 3.2 Update `dispatch_single_review` signature: add `repo_path: Path` and `harness_agents_dir: Path` parameters. Pass them to `build_review_prompt` along with existing `ecosystem` parameter. Note: `repo_path` is the target repo root (for `.harness/agents/` lookup), distinct from `worktree_path` (subprocess cwd). For managed repos this is `harness_home / "repos" / repo_name`; for local repos it's the original repo path.
- [x] 3.3 Update `dispatch_review_agents` signature: add `repo_path: Path` and `harness_agents_dir: Path`. Pass through to each `dispatch_single_review` call in the thread pool executor.
- [x] 3.4 Update call site in `pipeline.py` (`_run_review_agents`): pass `repo_path` (the resolved repo root from `run_pipeline`'s `repo` parameter) and `harness_agents_dir` (from `resolve_harness_agents_dir()`, called once at pipeline start) to `dispatch_review_agents`.

## 4. Wire Into OpenSpec Reviewer

- [x] 4.1 In `openspec_reviewer.py`, remove `REVIEW_SYSTEM_PROMPT` string. Extract the JSON output block (from `5. Output a final JSON block...` through the end of the `Important:` paragraph) into a module-level constant `_OPENSPEC_JSON_SUFFIX`. This constant uses literal braces `{` `}` (not escaped `{{` `}}`), because it is appended AFTER `.format(change_name=...)` is called on the persona text.
- [x] 4.2 Update `build_review_prompt(change_name: str, repo_path: Path, harness_agents_dir: Path) -> str`. Call `load_agent_prompt("openspec-reviewer", repo_path, harness_agents_dir)`, then `.format(change_name=change_name)` on the result, then append `_OPENSPEC_JSON_SUFFIX`.
- [x] 4.3 Update `dispatch_openspec_review` signature: add `repo_path: Path` and `harness_agents_dir: Path`. Pass through to `build_review_prompt`.
- [x] 4.4 Update call site in `pipeline.py` (`_run_openspec_review`): pass `repo_path` and `harness_agents_dir` to `dispatch_openspec_review`.

## 5. Package Data

- [x] 5.1 Add `[tool.hatch.build.targets.wheel.force-include]` to `pyproject.toml`: map `.harness/agents/` to `action_harness/default_agents/` so agent files are bundled inside the wheel. This matches the fallback path in `resolve_harness_agents_dir()`.

## 6. Tests

- [x] 6.1 Test `parse_agent_file` with frontmatter: create a temp file with `---\nname: test\n---\nPrompt body`. Assert metadata `{"name": "test"}` and body `"Prompt body"`.
- [x] 6.2 Test `parse_agent_file` without frontmatter: create a temp file with `"Prompt body"`. Assert metadata `{}` and body `"Prompt body"`.
- [x] 6.3 Test `parse_agent_file` with malformed YAML: create a temp file with `---\n: invalid: yaml:\n---\nBody`. Assert metadata `{}` and body contains `"Body"`.
- [x] 6.4 Test `load_agent_prompt` with repo override: create temp dirs for repo (`.harness/agents/bug-hunter.md` with body `"repo version"`) and harness (`bug-hunter.md` with body `"default version"`). Assert returns `"repo version"`.
- [x] 6.5 Test `load_agent_prompt` fallback: create only harness dir with `bug-hunter.md` body `"default version"`. No repo override. Assert returns `"default version"`.
- [x] 6.6 Test `load_agent_prompt` missing: call with agent name that has no file in either location. Assert `FileNotFoundError` raised with agent name in message.
- [x] 6.7 Test `build_review_prompt` end-to-end: create a real agent file in a temp dir with body `"Review PR #{pr_number} for bugs"`. Call `build_review_prompt("bug-hunter", 42, repo_path, harness_dir, ecosystem="python")`. Assert result contains `"Review PR #42 for bugs"`, contains `_JSON_OUTPUT_FORMAT` text, and contains `_GENERIC_SEVERITY_SUFFIX` text.
- [x] 6.8 Test `build_review_prompt` with custom-severity agent: create a temp `spec-compliance-reviewer.md`. Call `build_review_prompt`. Assert result contains `_JSON_OUTPUT_FORMAT` but does NOT contain `_GENERIC_SEVERITY_SUFFIX`.
- [x] 6.9 Verify all 5 default agent files exist in `.harness/agents/` and each has valid YAML frontmatter with `name` and `description` fields.

## 7. Self-Validation

- [ ] 7.1 `uv run pytest tests/ -v` — all existing and new tests pass
- [ ] 7.2 `uv run ruff check .` — no lint errors
- [ ] 7.3 `uv run ruff format --check .` — formatting clean
- [ ] 7.4 `uv run mypy src/` — no type errors
- [ ] 7.5 Verify agent files parse: `python -c "from action_harness.agents import parse_agent_file; from pathlib import Path; [print(parse_agent_file(p)[0]) for p in Path('.harness/agents').glob('*.md')]"` — prints 5 metadata dicts without errors
