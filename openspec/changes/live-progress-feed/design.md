## Context

The `EventLogger` writes JSONL events to `.action-harness/runs/<run-id>.events.jsonl` with fields: `timestamp`, `event`, `run_id`, `stage`, `duration_seconds`, `success`, and `metadata`. Events are flushed immediately (`flush()` after each write). The file grows as the pipeline progresses — perfect for tailing.

## Goals / Non-Goals

**Goals:**
- `harness progress --repo <path>` tails the latest event log
- Human-readable live display with stage names, timing, status indicators
- `--run <run-id>` to follow a specific run
- `--json` for streaming JSON events
- Clean exit on `run.completed` or `run.started` (if a new run starts)
- Works while the pipeline is running in another terminal/process

**Non-Goals:**
- Modifying the event logger or adding new events (existing events are sufficient)
- TUI/curses interface (simple line-by-line output for now)
- WebSocket or network streaming (local file tailing only)
- Aggregation across runs (that's `harness report`)

## Decisions

### 1. Tail with polling, not filesystem watchers

Use a simple poll loop: read new lines from the file every 1 second. This is portable across macOS/Linux without inotify/kqueue dependencies. The polling interval is fast enough for a progress display.

### 2. Human-readable format

```
[00:00] run.started — checkpoint-resume (repo: /Users/x/ads/action-harness)
[00:02] worktree.created — branch: harness/checkpoint-resume
[00:35] worker.completed — 5 commit(s), context: 3%
[00:38] eval.started — 5 command(s)
[00:42] eval.completed — 5/5 passed ✓
[00:42] pr.created — https://github.com/org/repo/pull/44
[01:15] review round 1 — 4 agents, 17 findings
[01:45] worker.completed — fix-retry, 6 commit(s)
[02:10] review round 2 — 12 findings
[02:30] openspec_review.completed — archived ✓
[02:31] run.completed — success (32m, 1 retry)
```

Each line: `[MM:SS]` elapsed time, event name, key details from metadata. Color-coded if terminal supports it (green for success, red for failure, yellow for warnings).

### 3. Find latest event log

`harness progress --repo .` without `--run` scans `.action-harness/runs/` for the most recently modified `.events.jsonl` file. This naturally finds the currently-running pipeline's log.

### 4. Exit conditions

- `run.completed` event → print final summary, exit 0
- `pipeline.error` event → print error, exit 1
- File deleted or truncated → exit with warning
- Ctrl+C → clean exit

### 5. `--json` streams raw events

In JSON mode, each event is printed as-is (one JSON object per line, same as the source file). No formatting, no elapsed time calculation. Useful for piping to `jq` or other tools.

## Risks / Trade-offs

- [Stale file] If no pipeline is running, the command tails a completed run's log and exits immediately → Acceptable behavior, clear message.
- [Multiple concurrent runs] If two pipelines run simultaneously, `--repo` finds the latest one → Use `--run` for specific runs.
