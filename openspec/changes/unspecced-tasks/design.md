## Context

The harness pipeline currently flows: CLI (`--change`) → `validate_inputs()` → `run_pipeline(change_name)` → `dispatch_worker(change_name)` → `build_system_prompt(change_name)` → opsx:apply prompt. The `change_name` string threads through every layer and is used for:
1. Validating the OpenSpec change directory exists
2. Building the worker system prompt (opsx:apply instruction)
3. Naming the worktree branch (`harness/{change_name}`)
4. PR title (`[harness] {change_name}`)
5. OpenSpec review stage (archive check)

To support freeform prompts, we need to make `change_name` optional and provide an alternative path at each of these touch points.

## Goals / Non-Goals

**Goals:**
- Add `--prompt` flag to `harness run` as an alternative to `--change`
- Mutual exclusion: exactly one of `--prompt` or `--change` required
- Worker receives the freeform prompt directly, no opsx:apply
- All pipeline stages (worktree, eval, retry, PR, review agents) work unchanged
- OpenSpec review stage skipped when no change name
- PR title/description derived from the prompt when no change name

**Non-Goals:**
- GitHub issue parsing (that's `github-issue-intake`, a separate roadmap item)
- Auto-generating OpenSpec proposals from prompts
- Different eval strategies for prompted vs change-based runs
- Prompt templates or structured prompt formats

## Decisions

### 1. Mutually exclusive --change and --prompt flags

The CLI requires exactly one of `--change` or `--prompt`. Both are optional with defaults of None, and the command validates that exactly one is provided. This is cleaner than making `--change` accept a special value.

**Alternative considered:** Making `--change` accept a freeform string when no OpenSpec directory matches. Rejected — the implicit behavior is confusing and makes error messages ambiguous.

### 2. Branch naming for prompted runs

When `--prompt` is used, there's no change name to derive a branch from. Use a sanitized slug from the first ~50 chars of the prompt: `harness/prompt-{slug}`. For example, "Fix the auth bug in issue #42" → `harness/prompt-fix-the-auth-bug-in-issue-42`.

**Alternative considered:** Random UUID branches. Rejected — a readable branch name helps operators identify what the harness is working on when looking at `git branch` output.

### 3. Worker prompt construction

`build_system_prompt()` gets a new mode. When `change_name` is provided, the existing opsx:apply prompt is used. When `prompt` is provided instead, the system prompt becomes a generic implementation role:

```
"You are implementing a task in this repository. Make the requested
changes, commit your work, and verify it works."
```

The user's freeform prompt becomes the user prompt, replacing the opsx:apply instruction.

### 4. `task_label` always flows as `change_name` — no type signature changes downstream

The CLI computes a `task_label` string: either the change name (for `--change`) or `f"prompt-{slug}"` (for `--prompt`). This `task_label` is passed as `change_name` to `run_pipeline()`, which passes it through to `create_worktree()`, `dispatch_worker()`, `create_pr()`, `_build_manifest()`, and `RunManifest`. The type stays `str` everywhere — no cascading `str | None` changes needed.

`run_pipeline()` gains an optional `prompt: str | None = None` parameter. When `prompt` is provided, the pipeline passes it to `dispatch_worker()` as the user prompt instead of the opsx:apply instruction. The `change_name` parameter still carries the `task_label` for branch naming, PR title, and manifest identification.

**Alternative considered:** Making `change_name: str | None` across the entire call chain. Rejected — this would require updating every function signature and adding None checks at every call site. Since the slug serves the same purpose (branch naming, PR title, manifest ID), passing it as `change_name` is simpler and avoids cascading changes.

### 5. OpenSpec review skipped for prompted runs

The OpenSpec review stage (`_run_openspec_review`) is skipped when there's no change name, since there are no OpenSpec artifacts to validate or archive.

### 6. PR title for prompted runs

When no change name is available, the PR title is `[harness] {first_line_of_prompt}` truncated to ~72 chars. The full prompt is included in the PR body.

## Risks / Trade-offs

- [Branch collision] Two runs with similar prompts could produce the same branch slug → Mitigation: `create_worktree()` already handles this — it calls `_cleanup_existing_branch()` to remove the old worktree and branch before creating a new one.
- [Prompt quality] Vague prompts will produce poor results → Mitigation: not our problem — the operator writes the prompt. The harness eval will catch broken implementations regardless.
- [No spec validation] Prompted runs have no OpenSpec review gate → Acceptable: the eval gate (build, test, lint) and review agents still run. OpenSpec review is specifically for spec compliance.
