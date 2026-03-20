## Context

The harness assumes target repos have certain infrastructure: `openspec/` for work management, `HARNESS.md` for worker instructions, and a `config.yaml` registration for dashboard visibility. Today these are set up manually or not at all — `gather_lead_context()` detects their absence but can only log a warning. The profiler already detects ecosystems and eval commands, and `repo.py` already handles project directory creation and config writing, but nothing ties these together into a coherent onboarding flow.

Two entry points are needed: an explicit `harness onboard` command for scripting and CI, and lead auto-detection for interactive discovery. Both share the same gap-detection and scaffolding logic.

## Goals / Non-Goals

**Goals:**
- Idempotent gap detection: check what's missing, scaffold only what's needed
- Automate mechanical steps: `openspec init`, `HARNESS.md` scaffold, project registration
- Lead auto-detection: lead notices un-onboarded repos and offers onboarding
- Safe re-runs: running onboard on a fully-onboarded repo is a no-op with a status report

**Non-Goals:**
- Generating ROADMAP.md content automatically — this requires human judgment and belongs in the lead conversation
- Generating or modifying CLAUDE.md — this is project-owned documentation, not harness infrastructure
- Onboarding non-GitHub repos — the harness is GitHub-native for now
- Replacing `openspec init` — we call it as a subprocess, not reimplement it

## Decisions

### 1. Onboarding module as pure gap-detect-and-fill

The core logic lives in a new `onboarding.py` module with two main functions: `detect_gaps()` returns a structured report of what's missing, and `fill_gaps()` scaffolds missing pieces. Both are independently callable — the CLI command uses both, the lead uses `detect_gaps()` to decide whether to offer onboarding.

**Why not integrate into the profiler?** The profiler answers "what is this repo?" — onboarding answers "what does this repo need?" They're complementary but distinct concerns. Onboarding calls the profiler to get eval commands for the HARNESS.md scaffold.

### 2. HARNESS.md scaffold uses profiler-detected eval commands

The scaffolded HARNESS.md includes eval commands detected by `profile_repo()`, formatted as the worker's eval section. This gives workers useful instructions from the first dispatch, even before the human customizes HARNESS.md.

**Alternative considered:** Empty HARNESS.md template with placeholders. Rejected because the profiler already does the hard work of detecting eval commands — not using them wastes that signal.

### 3. `openspec init --tools claude` called as subprocess

We shell out to `openspec init --tools claude` rather than reimplementing its file creation. The `--tools claude` flag is hardcoded since the harness is Claude-native.

**Why subprocess?** OpenSpec is a Node.js CLI — we can't import it. The `--tools` flag makes it non-interactive. If openspec is not installed, we fail with a clear error message.

### 4. Project registration uses existing `repo.py` functions

`ensure_project_dir()` and `write_project_config()` already handle project directory creation and config.yaml writing. Onboarding calls these for managed repos (remote references). For local repos (`.` or absolute paths), registration creates a symlink-style entry pointing at the local path.

**Why not always register?** Local repos the user passes as `.` may be temporary or one-off. We register them anyway because the user explicitly chose to onboard — that's a strong signal of intent.

### 5. Lead detection via `detect_gaps()` in context gathering

`gather_lead_context()` already checks for missing files. We add a `detect_gaps()` call and surface the result in `LeadContext` as a new `onboarding_gaps` field. The lead persona checks this field and offers to run onboarding if gaps exist.

**Why not a separate pre-flight check?** The lead already gathers context before starting — adding gap detection there keeps it in one pass and avoids duplicating filesystem checks.

### 6. Dry-run by default for `harness onboard`

`harness onboard` shows what it would do and prompts for confirmation. `--yes` skips the prompt for scripted usage. This matches the pattern of `openspec init` itself being interactive by default.

## Risks / Trade-offs

- **openspec CLI not installed** → `fill_gaps()` catches `FileNotFoundError` from the subprocess call and returns a clear error. The other scaffolding steps still proceed — partial onboarding is better than none.
- **HARNESS.md scaffold may have wrong eval commands** → The profiler's convention detection is best-effort. The scaffold includes a comment saying "detected automatically — review and adjust." The human or lead can refine later.
- **Lead onboarding offer adds noise to existing repos** → Gap detection is cheap (a few `Path.exists()` calls). For fully onboarded repos, no offer is shown. For partially onboarded repos, the offer is specific about what's missing.
- **config.yaml collision for local repos** → If two local repos have the same directory name, `ensure_project_dir` handles the collision with an `owner-repo` fallback. For local repos without a remote, we use the directory name.
