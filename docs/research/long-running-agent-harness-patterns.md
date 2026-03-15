# Long-Running Agent Harness Patterns

Date: 2026-03-15

## Origin

Anthropic engineering blog post: "Effective Harnesses for Long-Running Agents"
https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents

Companion to the OpenAI Codex harness post that inspired this project. The OpenAI post focuses on runtime observability (logs, metrics, traces). This Anthropic post focuses on session continuity — how agents stay effective across multiple context windows.

## Core Problem

Each worker dispatch starts with a fresh context window. The agent has no memory of what came before. In a retry loop, the second dispatch doesn't know what the first one tried, what commits it made, or what approach failed. The article frames this as a "shift handoff" problem.

## Key Patterns from the Article

### 1. Initializer + Coding Agent Split

The first context window gets a different prompt focused on setup:
- Create `init.sh` script for running the dev server
- Create `claude-progress.txt` for session memory
- Create initial git commit showing added files
- Establish feature list with 200+ testable items

Subsequent sessions get a "make incremental progress" prompt and read the artifacts the initializer created.

### 2. Progress File (`claude-progress.txt`)

A persistent file the agent reads at the start and writes at the end of each session. Serves as cross-session memory:
- What was done in prior sessions
- What's currently working
- What was attempted and failed
- Read alongside `git log --oneline -20` for recent history

### 3. Feature List as Regression Prevention

A JSON file with 200+ features, each structured as:
```json
{
  "category": "functional",
  "description": "New chat button creates fresh conversation",
  "steps": ["Navigate to main interface", "Click 'New Chat' button", ...],
  "passes": false
}
```

Critical constraint: **agents can only edit the `passes` field**. This prevents:
- Silently dropping requirements
- Accidentally deleting test descriptions
- Premature completion declarations

JSON was chosen over Markdown because models are less likely to inappropriately modify JSON structure.

### 4. Session Startup Checklist

Every coding session follows this sequence before doing new work:
1. Run `pwd` to confirm working directory
2. Read git logs and progress files for context
3. Review feature list, select highest-priority incomplete feature
4. Start development server via `init.sh`
5. Run basic end-to-end test before starting new work

Step 5 is key — verify the environment is healthy *before* making changes.

### 5. End-to-End Testing over Unit Tests

Agents must test "as a human user would" using browser automation (Puppeteer MCP). Unit tests alone aren't sufficient for verifying full-stack behavior. Known limitation: Claude cannot detect browser-native alert modals through Puppeteer.

### 6. Git as State Management

- Initial commit captures setup state
- Descriptive commit messages per feature
- Agents read `git log --oneline -20` at session start
- Enables reverting bad changes and recovering working states
- Commits written at session end with progress updates

### 7. Failure Modes

| Problem | Fix |
|---------|-----|
| Early victory declaration | Comprehensive feature list, all initially `passes: false` |
| Buggy undocumented state | Git repo + progress file, start sessions with verification |
| Premature feature completion | Self-verify with testing tools before marking complete |
| Runtime confusion / setup waste | `init.sh` script read at session start |

### 8. Single Agent vs Multi-Agent

The article explicitly flags this as unresolved: specialized agents (testing, QA, cleanup) might excel at sub-tasks, but no conclusion reached.

## How This Maps to action-harness

### Already covered

| Article Pattern | action-harness Equivalent |
|---|---|
| Git for state management | Worktree isolation, commit verification |
| Testing as evaluation | `run_eval()` with subprocess exit codes |
| Single feature per session | One OpenSpec change per pipeline run |
| Structured task list | OpenSpec `tasks.md` with checkboxes |
| Multi-agent architecture | Review agents as separate Claude Code dispatches |
| Feature list guards | OpenSpec specs define requirements, eval is the gate |

### Gaps / opportunities

#### 1. Progress file for retry continuity (HIGH VALUE)

The harness retries workers with eval feedback, but the new worker starts fresh — no memory of what the prior dispatch tried. Writing a `.harness-progress.md` in the worktree between retries would let the next worker pick up where the last left off.

```
Current retry loop:
  Dispatch 1 → makes changes → eval fails
  Dispatch 2 → gets feedback string → starts fresh (no memory)

With progress file:
  Dispatch 1 → makes changes → writes progress → eval fails
  Dispatch 2 → reads progress + feedback → continues intelligently
```

The progress file would capture: commits made so far, eval results, what approach was taken, what specifically failed. This is low-effort (write a file before re-dispatch) and high-impact (prevents repeating failed approaches).

#### 2. Pre-work verification on retries (HIGH VALUE)

Run eval *before* the worker starts on retries. If the worktree is already broken from a prior dispatch, catch it immediately rather than letting the worker compound the problem.

#### 3. HARNESS.md setup section (MEDIUM VALUE)

The `init.sh` pattern maps to a `## Setup` section in HARNESS.md — commands the harness runs before dispatching the worker (install deps, boot dev server, etc.). Relevant for service-type repos, not CLI tools.

Connects to the `ephemeral-observability` roadmap item — boot the app and observability stack *before* the worker starts.

#### 4. Task regression tracking (MEDIUM VALUE)

OpenSpec tasks can be marked complete, but there's no mechanism to verify they *stay* passing across retries. If retry 2 breaks something retry 1 fixed, the harness doesn't know until final eval. Per-task eval checks could catch regressions earlier.

Connects to the `checkpoint-resume` roadmap item — not just resuming stages, but ensuring completed work within a stage doesn't regress.

## Comparison: OpenAI vs Anthropic Harness Posts

```
                    OpenAI Codex Post           Anthropic Post
                    ─────────────────           ──────────────
Focus               Runtime observability       Session continuity
Problem             "Agent can't see the app"   "Agent forgets what it did"
Solution            Ephemeral observability      Progress files + feature lists
                    stack (Vector, Victoria)     + git state management

Tools               Victoria Logs/Metrics/       Puppeteer MCP, git,
                    Traces, Chrome DevTools       claude-progress.txt

Architecture        Per-worktree services        Per-session file artifacts
                    torn down after task          persist across dispatches

Key insight         Give agents the same         Treat agent sessions like
                    signals humans use to         engineering shift handoffs —
                    debug (logs, metrics)         leave a paper trail

Relevance to        Roadmap items:               Roadmap items:
action-harness      ephemeral-observability,     checkpoint-resume,
                    repo-profiling               harness-md, retry loop
```

Both posts converge on the same meta-principle: **agents work best when they have the same artifacts and signals that human engineers use to orient themselves in a codebase.**

## Captured In

Insights from this research have been captured in the following roadmap items and changes:

| Insight | Captured In |
|---------|-------------|
| Progress file for retry continuity | `retry-progress` (roadmap item 2, `openspec/changes/retry-progress/`) |
| Pre-work verification on retries | `retry-progress` (roadmap item 2, included as pre-work eval) |
| Session resume for retry continuity | `session-resume` (roadmap item 1, `openspec/changes/session-resume/`) |
| HARNESS.md setup section | `harness-md` (roadmap item 7, updated description to include executable `## Setup` section) |
| Task regression tracking | `checkpoint-resume` (roadmap item 14, scope clarified to distinguish from retry-progress) |
| Feature list as regression gate | Already covered by OpenSpec tasks + eval |
| Multi-agent architecture | Already covered by review agents |
