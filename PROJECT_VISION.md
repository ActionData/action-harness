
# PROJECT VISION — action-harness

## What this is

Action-harness automates the task-to-merge workflow by orchestrating Claude Code
workers through: task intake, implementation in isolated worktrees, evaluation,
retry with structured feedback, PR creation, agent review, and merge.

The term "harness" comes from a specific insight: when coding agents do the
implementation, the engineering challenge shifts from writing code to designing
the environment that makes agents effective. The harness is that environment.

```
Human (intent, judgment, taste)
  ↕
Claude Code (interactive lead)
  ↕
action-harness (autonomous pipeline)
  ↕
Target repositories
  ↕
External systems (GitHub, CI)
```

## Core beliefs

**1. Humans steer, agents execute.**
The human specifies intent, encodes taste, and makes judgment calls. The agent
turns intent into merged code. The harness makes that handoff reliable.

**2. Fix the environment, not the agent.**
When an agent fails, the answer is almost never "try harder." It's "what
capability, context, or constraint is missing?" Retry loops are a fallback.
The primary response to failure is improving the scaffolding so the failure
class doesn't recur.

**3. External evaluation is non-negotiable.**
Agents don't grade their own work. The harness runs build, test, lint, and type
checking as subprocesses and checks exit codes. Agent self-assessment is context,
never the gate.

**4. The repository is the system of record.**
Anything an agent can't discover in the repo doesn't exist. The harness helps
push context into repos as versioned, discoverable artifacts.

**5. Enforce boundaries, allow autonomy within them.**
Constraints allow speed without decay. Enforce invariants mechanically. Within
those boundaries, give agents freedom in how they solve problems.

**6. Claude Code is the agent runtime.**
No custom LLM client, no custom agent loop. The harness dispatches Claude Code
and benefits from every upstream improvement.

**7. Corrections are cheap; waiting is expensive.**
Agent throughput exceeds human attention. Optimize for flow: short-lived PRs,
minimal blocking gates, fix forward.

## Safety model

The harness can modify its own code. Safety comes from treating the test suite
as the immune system, requiring human review for load-bearing changes, and
graduating trust — starting with leaf changes before trusting the loop with
core modifications.

## What this is NOT

- **Not a custom agent framework.** Claude Code is the agent.
- **Not an IDE.** The interactive experience is Claude Code itself.
- **Not a CI/CD system.** Uses CI as a signal, not a replacement.

## Architecture principles

**Deterministic supervisor.** Zero LLM calls in orchestration. Decisions based
on observable signals: eval exit codes, git status, retry counts.

**Workers are stateless.** Each dispatch is fresh. Context comes from the repo,
the prompt, and structured feedback.

**Minimal abstraction.** Functions that call subprocess.run and parse JSON. No
framework. Read the code — it should be obvious.

**Workflow-first, architecture-emergent.** Build the loop first. Extract
abstractions when patterns repeat.
