## 1. PipelineCheckpoint Model [no dependencies]

- [ ] 1.1 Add `PipelineCheckpoint` Pydantic model to `models.py` with fields: `run_id: str`, `change_name: str`, `repo_path: str`, `completed_stages: list[str]`, `current_stage: str`, `worktree_path: str | None`, `branch: str | None`, `pr_url: str | None`, `session_id: str | None`, `last_worker_result: WorkerResult | None = None`, `last_eval_result: EvalResult | None = None`, `protected_files: list[str] = []`, `stages: list[StageResultUnion] = []`, `timestamp: str`, `ecosystem: str = "unknown"`. The `stages` field uses the existing `StageResultUnion` discriminated union.
- [ ] 1.2 Add tests: `PipelineCheckpoint` construction, roundtrip via `model_dump_json()` / `model_validate_json()` with nested `WorkerResult` and `EvalResult` in stages list. Verify `session_id` survives roundtrip.

## 2. Checkpoint I/O [depends: 1]

- [ ] 2.1 Create `src/action_harness/checkpoint.py` with `write_checkpoint(repo_path: Path, checkpoint: PipelineCheckpoint) -> None`. Writes to `.action-harness/checkpoints/<run_id>.json` using atomic write (temp file + `os.replace()`). Creates the checkpoints directory if needed.
- [ ] 2.2 Add `read_checkpoint(repo_path: Path, run_id: str) -> PipelineCheckpoint | None`. Returns None if file doesn't exist. Logs warning on parse error.
- [ ] 2.3 Add `find_latest_checkpoint(repo_path: Path, change_name: str) -> PipelineCheckpoint | None`. Scans `.action-harness/checkpoints/` for files matching the change name, returns the most recent by timestamp. Returns None if no checkpoints found.
- [ ] 2.4 Add `delete_checkpoint(repo_path: Path, run_id: str) -> None`. Deletes the checkpoint file. Logs warning if file doesn't exist (non-fatal).
- [ ] 2.5 Add tests: write + read roundtrip, read nonexistent returns None, find_latest with multiple checkpoints returns most recent, find_latest with no matches returns None, delete existing file, delete nonexistent logs warning. Verify atomic write (check no partial files on simulated error).

## 3. Pipeline Checkpoint Integration [depends: 2]

- [ ] 3.1 In `_run_pipeline_inner()`, after each major stage transition, call `write_checkpoint()` with the current state. Checkpoint write points: after worktree creation, after each worker dispatch in the retry loop, after eval pass, after PR creation, after each review round. Build the checkpoint from the local variables: `run_id`, `change_name`, `repo_path`, `worktree_path`, `branch`, `pr_url`, `session_id` (from last WorkerResult), `stages` list, `protected_files`.
- [ ] 3.2 On successful pipeline completion (before returning the final `PrResult`), call `delete_checkpoint()` to clean up.
- [ ] 3.3 Add tests: mock pipeline run produces checkpoint files at each stage. Successful pipeline deletes checkpoint. Failed pipeline preserves checkpoint.

## 4. Resume Logic [depends: 2, 3]

- [ ] 4.1 Add `--resume` option to `cli.py` `run` command (`str | None`, default None, accepts "latest" or a run ID string). When provided, call `find_latest_checkpoint` or `read_checkpoint` before starting the pipeline.
- [ ] 4.2 In `run_pipeline()`, accept `checkpoint: PipelineCheckpoint | None = None`. When a checkpoint is provided: validate that `worktree_path` still exists (if not, log warning and start fresh). Populate local variables from checkpoint (stages, worktree_path, branch, pr_url, session_id). Skip stages already in `completed_stages` — jump to `current_stage`.
- [ ] 4.3 Validate checkpoint matches the current run: `checkpoint.change_name` must equal the `--change` argument, `checkpoint.repo_path` must match the resolved repo path. If mismatch, log warning and start fresh.
- [ ] 4.4 Update dry-run output to show `resume: <run-id>` when `--resume` is provided.
- [ ] 4.5 Add tests: resume skips completed stages (mock pipeline with checkpoint showing worktree+worker+eval done, verify PR creation starts immediately). Resume with missing worktree starts fresh. Resume with mismatched change name starts fresh. `--resume latest` finds most recent checkpoint. `--resume` with no checkpoint starts fresh with warning.

## 5. Validation [depends: all]

- [ ] 5.1 Run `uv run pytest -v` — all tests pass
- [ ] 5.2 Run `uv run ruff check .` and `uv run mypy src/` — clean
