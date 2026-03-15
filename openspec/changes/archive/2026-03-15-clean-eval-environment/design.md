## Context

`run_eval` in `evaluator.py` calls `subprocess.run` without specifying `env`, which inherits the harness's environment including `VIRTUAL_ENV`. The target repo's tools see the wrong venv.

## Goals / Non-Goals

**Goals:**
- Eval commands run without `VIRTUAL_ENV` from the harness
- Simple, targeted fix

**Non-Goals:**
- Full environment isolation (containers, nix)
- Managing the target repo's venv

## Decisions

### 1. Strip VIRTUAL_ENV from subprocess env

Create a copy of `os.environ`, remove `VIRTUAL_ENV` and `VIRTUAL_ENV_PROMPT`, pass as `env` to `subprocess.run`.

**Why:** Minimal change. Removes the leak without affecting anything else.
