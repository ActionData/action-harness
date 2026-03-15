## 1. Prompt Slug Utility [no dependencies]

- [x] 1.1 Add a `slugify_prompt(prompt: str, max_length: int = 50) -> str` function (in a utils module or worker.py) that converts a prompt to a branch-safe slug: take the first line only, lowercase, non-alphanumeric chars replaced with hyphens, consecutive hyphens collapsed, leading/trailing hyphens stripped, truncated to `max_length`
- [x] 1.2 Add tests for `slugify_prompt`: basic text, special characters, long prompt truncation, unicode, empty string, multiline prompt (uses first line only)

## 2. Worker Prompt Construction [no dependencies]

- [x] 2.1 In `worker.py:13`, change `build_system_prompt(change_name: str)` to `build_system_prompt(change_name: str | None = None)`. When `change_name` is None, return a generic implementation system prompt: "You are implementing a task in this repository. Make the requested changes, commit your work, and verify it works." When `change_name` is provided, return the existing opsx:apply prompt unchanged.
- [x] 2.2 In `worker.py:48`, add an optional `prompt: str | None = None` parameter to `dispatch_worker()`. When `prompt` is provided, set `user_prompt = prompt` (replacing the opsx:apply instruction at line 73) and call `build_system_prompt(change_name=None)`. When `prompt` is None, keep the existing opsx:apply user prompt and system prompt unchanged.
- [x] 2.3 Add tests: assert `"opsx:apply" not in build_system_prompt(None)` and `"implementing a task" in build_system_prompt(None)`. Assert `build_system_prompt("my-change")` still contains `"opsx:apply"`. Assert `dispatch_worker` with `prompt="Fix bug"` uses "Fix bug" as user prompt (mock subprocess).

## 3. CLI Changes [depends: 1]

- [x] 3.1 Make `--change` optional (default None). Add `--prompt` option (default None, type str). Add validation at the start of `run()`: if both are provided, exit with "Specify either --change or --prompt, not both". If neither is provided, exit with "Specify either --change or --prompt".
- [x] 3.2 When `--prompt` is used, compute `task_label = f"prompt-{slugify_prompt(prompt)}"` and pass it as the `change` parameter to the rest of the pipeline. This means `create_worktree` receives `task_label` as `change_name` and produces branch `harness/prompt-{slug}` — no changes to `create_worktree` or `RunManifest` signatures needed. Skip `validate_inputs()` change directory check — call a separate `validate_inputs_prompt(repo)` that checks git repo, claude CLI, and gh CLI but not the openspec directory.
- [x] 3.3 Update the `run()` command docstring at `cli.py:125` and option help strings to document both `--prompt` and `--change` modes. The docstring is the API documentation per CLAUDE.md rules.
- [x] 3.4 Update `--dry-run` output to show prompt text and derived branch name when `--prompt` is used
- [x] 3.5 Add CLI tests: `--prompt` only works, `--change` only works, both fails, neither fails, `--dry-run` with `--prompt` shows correct output

## 4. Pipeline Changes [depends: 2, 3]

- [ ] 4.1 Add `prompt: str | None = None` parameter to `run_pipeline()` and `_run_pipeline_inner()`. Pass `prompt` through to `dispatch_worker()`. The `change_name` parameter always carries a string (either the real change name or the `task_label` slug) — no type change needed. On retries, pass `prompt` alongside `feedback` so the worker retains the original task context across retry loops.
- [ ] 4.2 At `pipeline.py:482`, wrap the `_run_openspec_review()` call in `if prompt is None:` to skip it in prompt mode. Review agents still run unless `--skip-review` is set.
- [ ] 4.3 Add tests: assert that `stages` list contains no `OpenSpecReviewResult` when pipeline is called with `prompt`. Assert pipeline with `change_name` only runs OpenSpec review as before.

## 5. PR Changes [depends: 1]

- [ ] 5.1 Update `create_pr()` to accept `prompt: str | None = None`. When prompt is provided, use `[harness] {first_line_of_prompt}` as PR title, truncated so the full title (including `[harness] ` prefix) is at most 72 characters. Include full prompt in PR body.
- [ ] 5.2 Add tests: PR title from short prompt, PR title from long prompt (verify total length <= 72 including prefix), PR body contains full prompt, multiline prompt uses first line for title

## 6. Validation

- [ ] 6.1 Run full test suite (`uv run pytest -v`) and verify no regressions
- [ ] 6.2 Run lint and type checks (`uv run ruff check .` and `uv run mypy src/`)
- [ ] 6.3 Run `harness run --prompt "Add a hello world test" --repo . --dry-run` and verify output shows prompt and derived branch name `harness/prompt-add-a-hello-world-test`
