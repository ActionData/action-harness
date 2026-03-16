## Why

The harness can detect what ecosystem a repo uses and what eval commands to run, but it has no way to assess *how well-equipped* a repo is for autonomous agent work. A repo with a CI pipeline that only runs `echo "done"` looks the same as one with full test/lint/typecheck coverage. Without quality assessment, the harness can't tell the operator "this repo is missing critical infrastructure" or proactively propose improvements.

The goal is a `harness assess` command that scores a repo's agentic readiness — not just what's present, but whether it's effective — and optionally generates OpenSpec proposals to close the gaps.

## What Changes

- New CLI command: `harness assess --repo <path>` with three progressive modes:
  - Base: deep mechanical scan (file parsing, CI workflow analysis, config inspection) — fast, no LLM
  - `--deep`: dispatches a read-only assessment agent to judge quality where mechanical checks can't (test quality, documentation clarity, architecture legibility)
  - `--propose`: dispatches spec-writer agents in parallel to generate OpenSpec change proposals for each identified gap
- New scoring model: `AssessmentReport` with per-category scores (context, testability, CI guardrails, observability, tooling, isolation), findings, and gap proposals
- Extends the existing `profiler.py` mechanical scan with CI workflow parsing, lockfile detection, and deeper config analysis
- Assessment agent is a specialized Claude Code worker dispatch (read-only, structured JSON output)
- Spec-writer agents reuse the existing spec-writer pattern to generate proposals

## Capabilities

### New Capabilities
- `mechanical-scan`: Extended file and config analysis — CI workflow parsing, dependency lockfile detection, test structure analysis, branch protection checks via GitHub API
- `agent-assessment`: Read-only Claude Code worker that judges quality of context, tests, and observability based on actually reading the code
- `scoring`: Per-category weighted scoring formula mapping mechanical signals to 0-100 scores, gap identification from low-scoring signals, and agent adjustment bounds (±20 points)
- `assessment-report`: Scoring model, CLI output formatting, JSON output mode, and persistence for the agentic readiness report
- `gap-proposals`: Automated OpenSpec proposal generation for identified gaps using spec-writer agent dispatches

### Modified Capabilities
- `repo-profiling`: The mechanical scan extends the existing profiler with additional signals (CI analysis, lockfile detection, test structure metrics). The `RepoProfile` model gains new fields or a companion `AssessmentReport` model.

## Impact

- `profiler.py` — extended with CI parsing, lockfile checks, test structure analysis
- `cli.py` — new `assess` command with `--repo`, `--deep`, `--propose` flags
- `worker.py` — may need a read-only worker dispatch mode (no commits expected)
- New module for assessment report model and scoring logic
- New module for CI workflow parsing (`.github/workflows/*.yml`)
- GitHub API integration for branch protection checks (`gh api`)
