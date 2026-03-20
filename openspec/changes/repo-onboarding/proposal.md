## Why

The harness uses OpenSpec as its work management control plane, but there is no mechanism to bootstrap a target repo into a harness-ready state. When `harness lead` or `harness run` targets a repo without `openspec/`, `HARNESS.md`, or a project registration, the system degrades silently — the lead says "this repo may need initial setup" but can't act on it, and headless runs get poor context. Onboarding should be an intentional, idempotent flow that closes the gap between "repo exists" and "repo is harness-ready."

## What Changes

- Add a `harness onboard --repo <path-or-ref>` CLI command that detects missing harness infrastructure and scaffolds it
- Mechanical steps run automatically: `openspec init --tools claude`, `HARNESS.md` scaffold with profiler-detected eval commands, project registration in `~/.harness/projects/<name>/config.yaml`
- Conversational steps (ROADMAP.md content, project priorities) are deferred to the lead session
- Lead auto-detects un-onboarded or partially-onboarded repos and offers to run onboarding before proceeding
- Gap detection is idempotent — only acts on what's missing, safe to re-run

## Capabilities

### New Capabilities

- `repo-onboarding`: Idempotent onboarding flow that detects missing harness infrastructure (openspec/, HARNESS.md, config.yaml registration) and scaffolds it, with two entry points (explicit CLI command and lead auto-detection)

### Modified Capabilities

- `lead-interactive`: Lead detects un-onboarded repos and offers onboarding before greeting

## Impact

- New CLI command `harness onboard` in `cli.py`
- New module `onboarding.py` for gap detection and scaffolding logic
- Modification to `lead.py` / lead persona to detect and trigger onboarding
- Depends on existing `profiler.py` (eval command detection), `repo.py` (project registration), and external `openspec init` CLI
- No breaking changes — existing repos continue to work; onboarding adds structure, never removes it
