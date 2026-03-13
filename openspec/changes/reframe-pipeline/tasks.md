## 1. Project Setup

- [ ] 1.1 Update CLAUDE.md to reflect self-hosting goal and workflow-first framing
- [ ] 1.2 Set up CLI entrypoint with typer: `action-harness run --change <name> --repo <path>` with `--max-retries` (default: 3)
- [ ] 1.3 Validate inputs: repo path exists and is a git repo, change directory exists in repo

## 2. Worktree Management

- [ ] 2.1 Create git worktree from default branch with branch name `harness/<change-name>`
- [ ] 2.2 Implement worktree cleanup: remove on terminal failure (preserve branch), preserve on PR creation

## 3. Code Agent Dispatch

- [ ] 3.1 Build the worker system prompt: change name, instruction to run `opsx:apply`, commit incrementally, self-validate
- [ ] 3.2 Invoke `claude` CLI as subprocess in the worktree directory with flags: `--output-format json`, `--system-prompt`, `--max-turns`, `--allowedTools`
- [ ] 3.3 Capture and parse worker JSON output (cost, duration, result)

## 4. Evaluation

- [ ] 4.1 Run eval commands as subprocesses in the worktree: `uv run pytest -v`, `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy src/`
- [ ] 4.2 On failure: capture stdout/stderr, format structured feedback prompt with failure output
- [ ] 4.3 Re-dispatch worker with feedback prompt (retry loop up to `--max-retries`)
- [ ] 4.4 On max retries exceeded: log failure context and exit with error

## 5. PR Creation

- [ ] 5.1 Push worktree branch to remote
- [ ] 5.2 Open PR via `gh pr create` with title `[harness] <change-name>` and structured body (change name, implementation summary, eval results)
- [ ] 5.3 Print PR URL and exit

## 6. End-to-End Wiring

- [ ] 6.1 Wire all stages: validate inputs → create worktree → dispatch agent → eval → retry loop → push → open PR
- [ ] 6.2 Handle errors at each stage with clear messages (not silent failures)

## 7. Tests

- [ ] 7.1 Unit tests for CLI argument validation and input parsing
- [ ] 7.2 Unit tests for worktree creation and cleanup
- [ ] 7.3 Unit tests for eval command execution and exit code handling
- [ ] 7.4 Unit tests for retry loop logic (feedback formatting, retry counting, max retries)
- [ ] 7.5 Unit tests for PR creation (gh command construction)
- [ ] 7.6 Integration test: full loop on a test fixture repo with a trivial OpenSpec change

## Validation

Run these commands to verify the implementation:

```bash
uv run pytest -v                  # all tests pass
uv run ruff check .               # no lint errors
uv run ruff format --check .      # formatting correct
uv run mypy src/                  # type checking passes
```

Then verify end-to-end on the harness's own repo:

1. Create a trivial OpenSpec change (e.g., "add --version flag to CLI")
2. Run `action-harness run --change <name> --repo .`
3. Confirm: worktree created, worker dispatched, eval runs, PR opened
4. Confirm: eval failure → structured feedback → retry works (introduce a deliberate test failure)
5. Confirm: max retries → clean exit with error message
6. Tag this version as the recovery baseline before beginning self-hosted work
