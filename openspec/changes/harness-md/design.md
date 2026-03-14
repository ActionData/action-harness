## Context

Workers currently receive a generic system prompt built by `build_system_prompt()` in `worker.py`. The prompt contains the change name and instructions to run opsx:apply. There's no mechanism to inject repo-specific guidance — every repo gets the same treatment.

The harness already reads CLAUDE.md (via Claude Code itself), but CLAUDE.md targets interactive sessions. Autonomous workers need different guidance: skill invocations, extra eval steps, path restrictions, retry hints, migration context.

## Goals / Non-Goals

**Goals:**
- Define a HARNESS.md file convention for repo-specific autonomous worker instructions
- Read HARNESS.md from the target repo at dispatch time and inject into the worker system prompt
- Keep it optional — repos without HARNESS.md work unchanged
- Document when to use HARNESS.md vs CLAUDE.md vs AGENTS.md

**Non-Goals:**
- Workspace-local overrides (operator-specific HARNESS.md outside the repo) — future work
- Structured/parsed sections (YAML frontmatter, typed fields) — keep it freeform markdown for now
- HARNESS.md generation or templating — the operator writes it by hand
- Validation of HARNESS.md contents

## Decisions

### 1. File lives in the target repo root as `HARNESS.md`

HARNESS.md lives alongside CLAUDE.md in the repo root. This means it's version-controlled, travels with the repo, and other harness operators benefit from it.

**Alternative considered:** Workspace-local file (e.g., `~/.harness/workspaces/<repo>/HARNESS.md`). Rejected for now — the repo-local convention is simpler and more collaborative. Workspace-local overrides can be layered on later.

### 2. Freeform markdown, no structured parsing

The harness reads HARNESS.md as a string and injects it verbatim into the system prompt. No YAML frontmatter, no typed sections, no parsing.

**Rationale:** The consumer is an LLM — it handles unstructured text natively. Adding structure would constrain what operators can express without meaningfully improving worker behavior. If structured sections prove valuable later, they can be added without breaking existing files.

### 3. Injected into system prompt, not user prompt

HARNESS.md content goes into the system prompt alongside the existing role instructions from `build_system_prompt()`. This positions it as persistent context rather than task-specific input.

**Alternative considered:** Appending to the user prompt. Rejected because HARNESS.md is repo-level context, not task-level — it applies to every worker dispatch against that repo.

### 4. Read from worktree path at dispatch time

The harness reads `{worktree_path}/HARNESS.md` when building the worker prompt. Since the worktree is a copy of the repo, this naturally gets the correct version for the branch being worked on.

### 5. Detection surfaced in repo profile

When repo profiling exists, the presence/absence of HARNESS.md should be captured in the profile. Before repo profiling lands, the harness simply checks for the file at dispatch time.

## Risks / Trade-offs

- [Prompt length] HARNESS.md content adds to system prompt size, consuming context window → Mitigation: document a recommended max length (~500 lines). The operator controls this.
- [Conflicting instructions] HARNESS.md could contradict CLAUDE.md → Mitigation: document the precedence convention (HARNESS.md is additive context for autonomous workers, CLAUDE.md still applies via Claude Code's native loading).
- [Stale content] HARNESS.md could become outdated → Mitigation: same risk as CLAUDE.md — it's the operator's responsibility. Repo profiling could warn if HARNESS.md references files/paths that don't exist.
