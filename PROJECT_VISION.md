
# PROJECT VISION — action-harness

## The goal: self-hosting

Action-harness is a harness that builds itself. The organizing goal is to reach
self-hosting: the point where the harness can accept feature requests for its own
codebase, implement them, get them reviewed, merge them, and upgrade itself.

We manually build the minimum viable loop — task intake, code agent dispatch,
eval, retry, PR creation. Then we point it at itself. Every capability after the
bootstrap (review agents, auto-merge, observability, repo profiling) is a task
the harness implements on its own codebase.

This is not a milestone on a roadmap. It is the roadmap.

```
Bootstrap (built by hand)
  → Minimum dispatch-eval-PR loop
  → Human reviews and merges

Self-hosting (harness builds these)
  → Review agents
  → Auto-merge with protected paths
  → Observability
  → Repo profiling
  → GitHub issue intake
  → Always-on server mode
  → ... everything else
```

## What this is

A harness engineering system. It automates the task-to-merge workflow by
orchestrating Claude Code workers through: task intake, implementation,
evaluation, PR creation, review, feedback iteration, and merge.

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
Target repositories (starting with itself)
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

## Bootstrap: what we build by hand

The minimum loop that can work on itself:

1. **CLI intake** — `ah run --change <name> --repo <path>` accepts
   an OpenSpec change name and a repo path.

2. **Worktree isolation** — Create a git worktree with branch
   `harness/<change-name>`. Agent works there, never the main checkout.

3. **Code agent dispatch** — Launch Claude Code CLI in the worktree with a
   system prompt instructing it to run `opsx-apply` on the change.

4. **Evaluation** — Run eval commands (pytest, ruff, mypy) as subprocesses.
   Binary pass/fail from exit codes.

5. **Retry loop** — On eval failure, format structured feedback with the failure
   output and re-dispatch. Cap at 3 retries, then exit with error.

6. **PR creation** — Open a PR via `gh pr create` with structured title/body.

7. **Human review and merge** — Human reviews the PR and merges. No auto-merge
   in the bootstrap.

This is all that's needed to start self-hosting. The test suite is the safety
net — it must be solid before the harness works on itself.

## Self-hosted backlog: what the harness builds

Once the bootstrap loop works, these become tasks for the harness itself. Each
is an OpenSpec change. Priority order reflects dependencies and safety:

1. **Structured logging** — JSON logs for every phase transition, dispatch, and
   eval result. The harness needs to observe itself before it can improve itself.

2. **Review agents** — Bug hunter, test reviewer, quality reviewer as
   independent Claude Code dispatches. This is the safety net upgrade that makes
   auto-merge possible.

3. **Protected paths** — Files/modules where changes always escalate to human
   review (e.g., eval runner, core dispatch, safety mechanisms). Required before
   auto-merge.

4. **Auto-merge** — After review agents approve and CI passes, merge without
   human intervention. Only enabled after protected paths are in place.

5. **Repo profiling** — Detect eval capabilities and context quality before
   dispatch. Needed when the harness works on repos other than itself.

6. **GitHub issue intake** — Parse issues for OpenSpec references. Needed when
   tasks come from GitHub, not just CLI.

7. **Unspecced tasks** — Support simple bugs/fixes described in issue body
   without a full OpenSpec change.

8. **Failure reporting** — Aggregate failure logs, identify systemic patterns,
   surface environment improvement opportunities.

9. **Always-on server** — Event-driven intake from webhooks. Recurring
   maintenance tasks. Escalation via Slack.

## Self-hosting safety

The harness modifying its own code is the "sawing the branch you're sitting on"
problem. Three mechanisms mitigate this:

**The test suite is the immune system.** It must be robust before self-hosting
begins. Weak tests mean the harness can merge changes that break itself. Invest
heavily in tests during the bootstrap phase.

**Pinned recovery baseline.** Tag a "known good" version before self-hosting.
If the harness breaks itself, checkout the tag and recover.

**Protected paths.** Changes to eval commands, core dispatch, or safety
mechanisms always require human review. The harness can build everything else
autonomously, but load-bearing code needs human judgment.

**Graduated trust.** First self-hosted tasks are leaf changes — a new log field,
a CLI flag, a data model. Not modifications to the dispatch loop. Build
confidence in the feedback loop before trusting it with load-bearing changes.

## What this is NOT

- **Not a custom agent framework.** Claude Code is the agent.
- **Not an IDE.** The interactive experience is Claude Code itself.
- **Not a CI/CD system.** Uses CI as a signal, not a replacement.
- **Not multi-tenant.** Single operator, starting with a single repo (itself).

## Architecture principles

**Deterministic supervisor.** Zero LLM calls in orchestration. Decisions based
on observable signals: eval exit codes, git status, retry counts.

**Workers are stateless.** Each dispatch is fresh. Context comes from the repo,
the prompt, and structured feedback.

**Minimal abstraction.** Functions that call subprocess.run and parse JSON. No
framework. Read the code — it should be obvious.

**Workflow-first, architecture-emergent.** Build the loop first. Extract
abstractions when patterns repeat.

## Success criteria

**Bootstrap is done when:**
- `ah run --change <name> --repo .` creates a worktree, dispatches
  a code agent, runs eval, retries on failure, and opens a PR — on its own
  codebase.
- A human can review and merge the PR.
- The harness's test suite catches bad changes reliably.

**Self-hosting is working when:**
- The harness accepts an OpenSpec change for a new feature, implements it, gets
  it reviewed (by agents), and merges it — without human intervention except for
  protected-path changes.
- The failure rate decreases over time because failures become environment
  improvements.
- The harness has built more of itself than was built by hand.
