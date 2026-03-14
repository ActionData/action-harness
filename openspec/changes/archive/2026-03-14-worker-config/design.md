## Context

`dispatch_worker` currently builds a fixed `claude` CLI command: `-p`, `--system-prompt`, `--output-format json`, `--max-turns`. The operator cannot control model selection, effort level, budget caps, or permission mode. These are all supported by the `claude` CLI.

## Goals / Non-Goals

**Goals:**
- Expose `--model`, `--effort`, `--max-budget-usd`, `--permission-mode` as CLI flags
- Thread them through pipeline to the `claude` CLI invocation
- Sensible defaults for self-hosting (no required flags beyond what exists today)

**Non-Goals:**
- Per-stage configuration (different model for review vs code) — future work
- Configuration files — CLI flags are sufficient for bootstrap
- Allowed tools restriction — deferred per design Decision 4 in reframe-pipeline

## Decisions

### 1. CLI flags mirror claude CLI flags

Use the same names where possible: `--model`, `--effort`, `--max-budget-usd`, `--permission-mode`. This makes the mapping obvious and the `--dry-run` output predictable.

**Why:** Minimal cognitive overhead. The harness flag name tells you what claude CLI flag it maps to.

### 2. Defaults

- `--model`: no default (omit flag, let claude CLI use its default)
- `--effort`: no default (omit flag, let claude CLI use its default)
- `--max-budget-usd`: no default (no budget cap unless specified)
- `--permission-mode`: default to `"bypassPermissions"` for headless operation

**Why:** The harness runs headless — permission prompts would hang. Budget and model should be explicit operator choices, not harness defaults.

### 3. Only include flags in claude command when explicitly set

If `--model` is not provided, don't include `--model` in the `claude` CLI command at all. This lets claude CLI's own defaults apply.

**Why:** Avoids hardcoding a model that becomes stale. The operator opts in to specific configuration.

## Risks / Trade-offs

**[Risk] Permission mode bypass is a security-relevant default.**
→ Mitigation: The harness is designed for headless operation. Interactive permission prompts would hang. Document this default clearly in `--help`.

**[Trade-off] No per-stage configuration.**
→ Acceptable for bootstrap. When review agents are added, per-stage config becomes valuable. For now, one set of flags applies to all worker dispatches.
