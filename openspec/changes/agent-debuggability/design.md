## Context

The harness is self-hosting: agents build it, agents debug it, agents review it. Every component must be observable by an agent reading stderr output or inspecting return values. The bootstrap spec (reframe-pipeline) defines the pipeline stages but includes no logging or stage-isolation requirements. The first self-hosted task on the roadmap is "structured logging" (JSON logs for phase transitions), but that assumes a working pipeline to build it with — creating a chicken-and-egg problem if the bootstrap itself can't be diagnosed.

Current state: `cli.py` validates inputs and prints a status line. The remaining pipeline modules are stubs. Now is the time to set the conventions before the pipeline is built.

## Goals / Non-Goals

**Goals:**
- Establish design rules for agent-debuggability that apply to all bootstrap and future code
- Define logging conventions (stderr for progress, structured returns for programmatic use)
- Require stage isolation: each pipeline stage is callable as a standalone function with clear inputs and outputs
- Add `--verbose` and `--dry-run` CLI flags
- Update CLAUDE.md with the new rules so all future implementation follows them

**Non-Goals:**
- JSON structured logging (self-hosted task #1 — this change provides the foundation it builds on)
- Log aggregation, dashboards, or observability infrastructure
- Changing the pipeline architecture — this is about conventions, not restructuring

## Decisions

### 1. stderr for human-readable progress, return values for programmatic consumption

Every pipeline function prints progress to stderr (via `typer.echo(..., err=True)`) and returns a result dataclass/model describing what happened. The CLI reads return values and decides what to print to stdout. Agents reading stderr get a timeline of what the harness did. Agents calling functions programmatically get structured results.

**Why stderr over stdout:** stdout is reserved for final output (PR URL, error summary). stderr is the diagnostic channel. This matches Unix conventions and means piping `action-harness run ... 2>log.txt` captures diagnostics without mixing with the result.

**Why not Python logging module:** At bootstrap scale, `typer.echo(..., err=True)` is simpler and sufficient. The structured-logging self-hosted task can migrate to `logging` or `structlog` when it adds JSON output.

### 2. Every pipeline stage is a standalone function with typed inputs and outputs

Each stage (validate, create_worktree, dispatch_worker, run_eval, create_pr) is a function that takes explicit parameters and returns a result object. The pipeline wires them together but any stage can be called independently in a test or a debugging session.

**Why:** An agent debugging a worktree failure shouldn't need to run the full pipeline. Calling `create_worktree("my-change", repo_path)` directly and inspecting the result is the fastest path to diagnosis. This also makes unit testing trivial — no mocking of earlier stages to test later ones.

### 3. Result objects, not exceptions, for expected outcomes

Pipeline stages return result objects that include success/failure status, not just raising exceptions. Exceptions are for unexpected errors (bug in the harness). Expected failures (eval fails, worker produces no commits) are returned as result values the caller can inspect.

**Why:** An agent can inspect `result.success`, `result.output`, `result.error_message` without catching exceptions. This makes the retry loop in pipeline.py a simple conditional, not a try/except block. It also makes test assertions clearer: `assert result.success is False` vs catching an exception.

### 4. `--verbose` flag for detailed stderr output

Default stderr output logs stage boundaries only (entering/exiting each stage, pass/fail). `--verbose` adds detail: full subprocess commands, working directories, output previews. This gives agents a knob to control how much diagnostic output they receive.

**Why:** Default output should be scannable (5-10 lines for a successful run). Verbose output should be comprehensive enough to diagnose any failure without re-running.

### 5. `--dry-run` flag for validation without execution

`--dry-run` validates all inputs, resolves the worktree path, prints what each stage would do, and exits. No worktree creation, no worker dispatch, no eval, no PR.

**Why:** An agent testing harness configuration or verifying a change exists shouldn't need to run the full pipeline. Dry-run also serves as documentation — the output shows the exact sequence of operations.

## Risks / Trade-offs

**[Risk] Logging conventions add boilerplate to every function.**
→ Mitigation: Keep it minimal — one line at entry, one at exit. The structured-logging task can wrap this in helpers later.

**[Risk] Result objects add types that need to be maintained.**
→ Mitigation: Use simple dataclasses in models.py. They're plain data, not abstractions. Add fields as needed, don't over-design upfront.

**[Trade-off] stderr logging is not structured (not JSON).**
→ Acceptable. The bootstrap needs human/agent-readable diagnostics now. The structured-logging self-hosted task upgrades to JSON later. The convention (stderr for diagnostics) stays the same.
