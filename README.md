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
action-harness run --change <change-name> --repo <path>

# Run against the harness's own codebase
action-harness run --change <change-name> --repo .
```

Use `action-harness run --help` for the full set of flags (model, effort, budget, permission mode, etc).

### Development

```bash
uv run pytest -v                  # run tests
uv run ruff check .               # lint
uv run ruff format --check .      # check formatting
uv run mypy src/                  # type check
```

## How it works

The pipeline runs in deterministic stages with zero LLM calls in orchestration:

1. **Task intake** — accepts an OpenSpec change name and repo path
2. **Worktree isolation** — creates a git worktree on a `harness/<change-name>` branch
3. **Code agent dispatch** — launches Claude Code CLI in the worktree
4. **Evaluation** — runs eval commands (pytest, ruff, mypy) as subprocesses; binary pass/fail from exit codes
5. **Retry** — on eval failure, formats structured feedback and re-dispatches (up to 3 retries)
6. **PR creation** — opens a PR via `gh` with a structured description built from the run manifest

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
| [`docs/`](docs/) | Exploration notes and research |
