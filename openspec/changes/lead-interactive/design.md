## Context

The `harness lead` command currently dispatches a one-shot Claude Code session via `claude -p` that produces a structured JSON plan. This works for autonomous dispatch but prevents conversational interaction. The human must separately open Claude Code if they want to explore ideas or refine recommendations.

Claude Code supports interactive sessions natively — `claude` without `-p` starts a conversational session. It accepts `--system-prompt` and an initial prompt as a positional argument. The lead's context-gathering infrastructure already exists; we just need to route it through an interactive session instead of a one-shot dispatch.

## Goals / Non-Goals

**Goals:**
- Make `harness lead` spawn an interactive Claude Code session by default
- Pre-load the session with gathered repo context (roadmap, issues, assessment, etc.)
- Preserve the existing non-interactive behavior behind a `--no-interactive` flag
- Keep the interactive session as a simple `subprocess.run` of `claude` (no PTY tricks)

**Non-Goals:**
- Parsing output from interactive sessions (the human is driving)
- Supporting `--dispatch` in interactive mode (the human dispatches manually)
- Changing the lead agent persona or context gathering logic
- Adding new context sources or changing truncation limits

## Decisions

### Decision 1: Interactive mode via `claude` without `-p`

Run `claude "initial prompt" --system-prompt <persona> --append-system-prompt <context>` which starts an interactive session with the lead persona and repo context pre-loaded. The initial prompt argument seeds the conversation.

**Alternative considered**: Write context to a file and tell the user to open Claude Code manually. Rejected — defeats the purpose of `harness lead` as a single command.

**Alternative considered**: Use `--initial-prompt` or pipe stdin. Rejected — Claude Code's positional argument already serves as the initial prompt for interactive sessions.

### Decision 2: System prompt structure

Use `--system-prompt` for the lead persona (from `.harness/agents/lead.md`) and `--append-system-prompt` for the gathered repo context. This keeps the persona as the primary system prompt while injecting context as supplementary information.

**Alternative considered**: Concatenate persona + context into a single `--system-prompt`. Rejected — `--append-system-prompt` provides cleaner separation and the persona serves as the base identity.

### Decision 3: Interactive as default, `--no-interactive` for one-shot

The primary use case is human-in-the-loop planning. Making interactive the default means `harness lead --repo .` does the right thing. The `--no-interactive` flag preserves the existing JSON-plan-and-dispatch behavior for automation.

**Alternative considered**: Keep non-interactive as default, add `--interactive`/`-i`. Rejected — the interactive use case is the more common one; automation callers can specify `--no-interactive`.

### Decision 4: No `--dispatch` in interactive mode

Interactive mode is conversational — the human decides what to do. `--dispatch` is mutually exclusive with interactive mode. If both are provided, error with a clear message.

### Decision 5: subprocess.run with inherited stdio

Interactive sessions need real terminal access. Use `subprocess.run` without `capture_output` so stdin/stdout/stderr are inherited from the parent process. This lets the human type and see responses naturally.

**Alternative considered**: Use `os.execvp` to replace the harness process entirely. Rejected — `subprocess.run` lets us do cleanup after the session ends (logging, exit code reporting).

## Risks / Trade-offs

- [Interactive sessions can't produce structured output] → Accepted. Interactive mode is for human use; structured output remains available via `--no-interactive`.
- [Default behavior change is breaking for scripts] → Mitigated by `--no-interactive` flag. Any script calling `harness lead` for JSON parsing needs to add `--no-interactive`. Document in CLI help.
- [System prompt + append-system-prompt may hit length limits] → Mitigated by existing 3000-char truncation per section in `gather_lead_context`.
