## 1. Lead Agent Persona [no dependencies]

- [x] 1.1 Create `.harness/agents/lead.md` with YAML frontmatter (`name: lead`, `description: ...`) and persona body. The persona describes: you are a technical lead for this repository, you have full repo context, you can draft OpenSpec proposals, create issues, recommend harness dispatches, and explore ideas. You prioritize based on roadmap order, issue severity, assessment gaps, and failure patterns. Output a JSON plan with `summary`, `proposals`, `issues`, and `dispatches` keys.
- [x] 1.2 Add tests: verify the lead agent file exists, parses with valid frontmatter, and body contains key capability descriptions.

## 2. Context Gathering [no dependencies]

- [x] 2.1 Create `src/action_harness/lead.py` with `gather_lead_context(repo_path: Path, harness_home: Path | None = None, max_section_chars: int = 3000) -> str`. Reads and assembles context sections, truncating each to `max_section_chars`: (a) ROADMAP.md content (if exists), (b) CLAUDE.md content (if exists), (c) HARNESS.md content (if exists), (d) open issues via `gh issue list --json title,body,labels --limit 20 --state open` — truncate each issue body to 500 chars (skip if `gh` not available, log warning), (e) assessment scores via reading the most recent assessment manifest or running a quick base scan, (f) recent run summary from manifests (last 5 runs: change name, success, duration), (g) catalog frequency top 5 entries from harness home knowledge store. Format each section with a markdown header. Return the assembled context string.
- [x] 2.2 Add tests: `gather_lead_context` with a repo containing ROADMAP.md and CLAUDE.md includes both. Missing files are skipped without error. `gh` failure is non-fatal (warning logged, issues section omitted). Empty repo returns minimal context with a note.

## 3. Lead Dispatch [depends: 1, 2]

- [x] 3.1 Add `dispatch_lead(repo_path: Path, prompt: str, context: str, harness_agents_dir: Path, max_turns: int = 50) -> str` to `lead.py`. Loads the lead persona via `load_agent_prompt("lead", repo_path, harness_agents_dir)` — the existing function handles repo override lookup at `repo_path/.harness/agents/lead.md` automatically. Builds system prompt from persona. Builds user prompt from `context + "\n\n## Your Task\n\n" + prompt`. Dispatches via `claude -p <user_prompt> --system-prompt <system_prompt> --output-format json --max-turns <max_turns> --permission-mode default`. Returns the JSON output string. Includes `timeout=7200` on subprocess.run. Catches `TimeoutExpired`, `FileNotFoundError`, `OSError` with clear error messages.
- [x] 3.2 Add tests: dispatch with mock subprocess returns output. Persona loaded from agent file. Timeout/error handling returns error message. Permission mode is `plan`.

## 4. Plan Parsing [depends: 3]

- [x] 4.1 Add Pydantic models to `lead.py`: `ProposalItem(name: str, description: str, priority: str = "medium")`, `IssueItem(title: str, body: str, labels: list[str] = [])`, `DispatchItem(change: str)`, `LeadPlan(summary: str = "", proposals: list[ProposalItem] = [], issues: list[IssueItem] = [], dispatches: list[DispatchItem] = [])`. Add `parse_lead_plan(raw_output: str) -> LeadPlan`. Extracts the JSON plan from the claude CLI output's `result` field via `extract_json_block` (same pattern as `parse_review_result`). Validates via `LeadPlan.model_validate(data)`. Returns a default empty `LeadPlan()` if parsing fails (log warning, never crash). When the agent produces no extractable JSON, display the raw output text and log a warning.
- [x] 4.2 Add tests: parse valid plan JSON returns populated LeadPlan. Parse malformed output returns empty LeadPlan with warning. Parse output with no JSON block returns empty LeadPlan and raw text is logged. Verify model roundtrip via `model_dump_json()` / `model_validate_json()`.

## 5. CLI Command [depends: 2, 3, 4]

- [x] 5.1 Add `harness lead` command to `cli.py` with `--repo` (required Path), `--dispatch` (flag, default False), `--harness-home` (optional Path), and positional `prompt` argument (optional str, default "Review the repo state and recommend what to work on next"). Calls `gather_lead_context`, `dispatch_lead`, `parse_lead_plan`. Displays the plan as formatted output.
- [x] 5.2 When `--dispatch` is provided: for each entry in `plan.dispatches`, verify `repo_path / "openspec" / "changes" / dispatch.change / "tasks.md"` exists (directory AND tasks.md — a change without tasks isn't implementable). Execute dispatches sequentially. Run `harness run --change <name> --repo <path>` via subprocess with `timeout=7200`. If a dispatch exits non-zero, log the failure with change name and exit code, then continue to the next dispatch (failure does not abort remaining dispatches). Report all dispatch results at the end.
- [x] 5.3 Update CLI docstring for the `lead` command.
- [x] 5.4 Add tests: `--help` shows lead command. Lead with mock dispatch returns formatted plan. `--dispatch` with existing change triggers subprocess. `--dispatch` with nonexistent change logs warning and skips.

## 6. Validation [depends: all]

- [x] 6.1 Run `uv run pytest -v` — all tests pass
- [x] 6.2 Run `uv run ruff check .` and `uv run mypy src/` — clean
