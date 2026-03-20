# action-harness

Autonomous engineering pipeline that orchestrates [Claude Code](https://docs.anthropic.com/en/docs/claude-code) workers through the full development lifecycle: task intake, implementation in isolated worktrees, external evaluation, retry with structured feedback, and PR creation.

The organizing goal is **self-hosting** — build the minimum loop by hand, then the harness builds everything else as tasks on its own codebase.

```
Human (intent, judgment, taste)
  ↕
Claude Code (interactive lead)
  ↕
action-harness (autonomous pipeline)
  ↕
Target repositories (starting with itself)
  ↕
External systems (GitHub, CI)
```

## Getting started

### Prerequisites

- Python 3.13+
- [`uv`](https://docs.astral.sh/uv/)
- [`claude`](https://docs.anthropic.com/en/docs/claude-code) CLI
- [`gh`](https://cli.github.com/) CLI

### Install

```bash
uv sync
```

### Run the pipeline

```bash
# Run an OpenSpec change against a repo
ah run --change <change-name> --repo <path>

# Run against the harness's own codebase
ah run --change <change-name> --repo .
```

Use `ah run --help` for the full set of flags (model, effort, budget, permission mode, etc).

### Development

```bash
uv run pytest -v                  # run tests
uv run ruff check .               # lint
uv run ruff format --check .      # check formatting
uv run mypy src/                  # type check
```

## How it works

The pipeline runs in deterministic stages with zero LLM calls in orchestration:

1. **Validate** — assert `claude` and `gh` CLIs exist, profile the repo to detect ecosystem and eval commands
2. **Worktree isolation** — create a git worktree on a `harness/<change-name>` branch
3. **Dispatch + eval loop** — launch Claude Code CLI in the worktree, run eval commands (pytest, ruff, mypy) as subprocesses, retry with structured feedback on failure (up to 3 retries, with session resume when context is fresh)
4. **PR creation** — open a PR via `gh` with a structured description built from the run manifest
5. **Protected paths check** — diff changed files against `.harness/protected-paths.yml`, flag for human review if matched
6. **Review agents** — dispatch 4 specialized agents in parallel (bug-hunter, test-reviewer, quality-reviewer, spec-compliance), triage findings, auto-fix critical/high issues
7. **OpenSpec review** — validate spec completion, semantic review, auto-archive on approval
8. **Auto-merge** (optional) — gate checks (no protected files, review clean, CI passing), merge PR

## Key principles

- **External evaluation** — agents don't grade their own work; the harness checks exit codes
- **Claude Code is the runtime** — no custom LLM client or agent loop
- **Workers are stateless** — each dispatch is fresh; context comes from the repo and the prompt
- **Minimal abstraction** — functions that call `subprocess.run` and parse JSON

## Project documentation

| Document | Description |
|---|---|
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | System overview, module map, and pipeline control flow |
| [`PROJECT_VISION.md`](PROJECT_VISION.md) | Core beliefs, architecture principles, and success criteria |
| [`openspec/ROADMAP.md`](openspec/ROADMAP.md) | Self-hosted backlog — bootstrap and future changes |
| [`CLAUDE.md`](CLAUDE.md) | Design rules, build commands, and development conventions |
| [`docs/`](docs/) | Operational guides |
