## 1. Agent Prompt and Dispatch Signature [no dependencies]

- [x] 1.1 Add `spec-compliance-reviewer` case to `build_review_prompt()` in `review_agents.py`. The system prompt instructs the agent to: parse tasks.md, identify `[x]` tasks, check each against the diff (fetched via `gh pr diff`), and report findings. Include severity definitions: critical (function/integration absent), high (shortcut taken), medium (parameter/type mismatch), low (weak test assertion).
- [x] 1.2 Add `extra_context: str | None = None` parameter to `dispatch_single_review()`. When set, append `extra_context` to the user prompt after the standard `"Review PR #{pr_number}"` text. Existing agents pass `None` (no behavior change).
- [x] 1.3 Add tests: `build_review_prompt("spec-compliance-reviewer", ...)` returns a prompt containing "tasks" and "compliance" and severity definitions. `dispatch_single_review` with `extra_context="sentinel text"` includes `"sentinel text"` in the user prompt. `dispatch_single_review` with `extra_context=None` produces unchanged user prompt.

## 2. Dispatch Integration [depends: 1]

- [x] 2.1 Add `change_name: str | None = None` parameter to `dispatch_review_agents()`. When `change_name is not None`, check if `worktree_path / "openspec" / "changes" / change_name / "tasks.md"` exists. If it does, read its content and include `spec-compliance-reviewer` in the agent list, passing the tasks content as `extra_context` to `dispatch_single_review`. If `change_name is None` or tasks.md doesn't exist, dispatch only the existing 3 agents.
- [x] 2.2 Build the agent list dynamically in `dispatch_review_agents`: start with `REVIEW_AGENT_NAMES` (the existing 3), then append `"spec-compliance-reviewer"` only when change_name is set and tasks.md exists.
- [x] 2.3 Add tests: dispatch with `change_name="test-change"` and a mock tasks.md containing `"- [x] 99.1 sentinel task"` — assert 4 agents dispatched and the spec-compliance-reviewer prompt contains the sentinel string. Dispatch with `change_name=None` — assert 3 agents dispatched. Dispatch with `change_name="nonexistent"` (no tasks.md file) — assert 3 agents dispatched.

## 3. Pipeline Threading [depends: 2]

- [ ] 3.1 Update all call sites of `dispatch_review_agents` in `pipeline.py` to pass `change_name=change_name`. The `change_name` parameter is already available in `_run_pipeline_inner`.
- [ ] 3.2 Add test: verify that when pipeline runs with a change name, `dispatch_review_agents` is called with `change_name` matching the pipeline's change name. When pipeline runs in prompt mode, `dispatch_review_agents` is called with `change_name` that starts with `prompt-` — verify spec-compliance-reviewer is NOT dispatched (tasks.md won't exist).

## 4. Validation [depends: all]

- [ ] 4.1 Run `uv run pytest -v` — all tests pass
- [ ] 4.2 Run `uv run ruff check .` and `uv run mypy src/` — clean
