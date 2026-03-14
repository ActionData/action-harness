Implement before `enrich-pr-description` and `worker-config` — the manifest is the foundation they build on.

Note: once this lands, `enrich-pr-description` tasks should be updated to consume the manifest instead of threading `WorkerResult` directly to `create_pr`. The manifest replaces the need for individual result threading.

## 1. RunManifest Model

- [ ] 1.1 In `models.py`: define `RunManifest(BaseModel)` with fields: `change_name` (str), `repo_path` (str), `started_at` (str, ISO format), `completed_at` (str, ISO format), `success` (bool), `stages` (list[StageResult]), `total_duration_seconds` (float), `total_cost_usd` (float | None = None), `retries` (int = 0), `pr_url` (str | None = None), `error` (str | None = None), `manifest_path` (str | None = None). The `retries` field counts re-attempts only (excluding the initial attempt) — matching the pipeline's `attempt` variable which starts at 0.
- [ ] 1.2 In `tests/test_models.py`: test `RunManifest` construction with success and failure cases. Verify `model_dump_json()` produces valid JSON. Verify stages list accepts mixed StageResult subtypes (WorktreeResult, WorkerResult, EvalResult, PrResult).

## 2. Pipeline Manifest Collection

- [ ] 2.1 In `pipeline.py`: at the start of `run_pipeline`, record `started_at = datetime.now(UTC).isoformat()`. Initialize `stages: list[StageResult] = []` and `retries = 0`.
- [ ] 2.2 In `pipeline.py`: after each stage call (create_worktree, dispatch_worker, run_eval, create_pr), append the result to `stages`. Increment `retries` on each retry loop iteration (retries counts re-attempts, not the initial attempt).
- [ ] 2.3 In `pipeline.py`: add `_build_manifest(change_name, repo, started_at, stages, retries, pr_result)` helper that constructs a `RunManifest` from the collected data. Compute `total_duration_seconds` from started_at to now. Sum `cost_usd` across ALL WorkerResult entries in stages (including retries) for `total_cost_usd`.
- [ ] 2.4 In `pipeline.py`: add `_write_manifest(manifest, repo)` helper that writes `manifest.model_dump_json(indent=2)` to `<repo>/.action-harness/runs/<timestamp>-<change-name>.json`. Create the directory with `os.makedirs(..., exist_ok=True)` if it doesn't exist. Log the path to stderr. Set `manifest.manifest_path` to the written path.
- [ ] 2.5 In `pipeline.py`: use a try/finally pattern (or equivalent) so that `_build_manifest` and `_write_manifest` are called on EVERY exit path. There are currently 5 return sites in `run_pipeline` (worktree failure ~line 33, worker exhaustion ~line 67, eval exhaustion ~line 93, else safety net ~line 103, and success/PR failure ~line 120). The manifest must be built and written before each. Return `(PrResult, RunManifest)` tuple.

## 3. CLI Update

- [ ] 3.1 In `cli.py`: update the `run_pipeline(...)` call to unpack the `(PrResult, RunManifest)` return. Log the manifest path to stderr: `[pipeline] manifest saved to <path>`.
- [ ] 3.2 In `cli.py`: exit code logic stays the same (check `pr_result.success`).

## 4. Gitignore

- [ ] 4.1 In `.gitignore`: append `.action-harness/` entry to the existing file.

## 5. Tests

- [ ] 5.1 In `tests/test_integration.py`: update ALL calls to `run_pipeline(...)` that capture the return value to unpack `(pr_result, manifest)`. Currently there are call sites across `TestPipelineSuccess` (3 tests) and `TestPipelineFailure` (5 tests). Each must handle the tuple return.
- [ ] 5.2 In `tests/test_integration.py`: add test that manifest is written to disk — check `.action-harness/runs/` directory exists and contains a JSON file after pipeline run. Verify the JSON deserializes to a valid `RunManifest` via `RunManifest.model_validate_json()`.
- [ ] 5.3 In `tests/test_integration.py`: add test for failed pipeline — verify manifest is written with `success=False`, error field populated, and retries count matches actual retry attempts.
- [ ] 5.4 In `tests/test_cli.py`: update CLI tests that mock `run_pipeline` to return `(PrResult, RunManifest)` tuple.

## 6. Validation

```bash
uv run pytest -v
uv run ruff check .
uv run ruff format --check .
uv run mypy src/
```
