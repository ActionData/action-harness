Implement before `enrich-pr-description` and `worker-config` — the manifest is the foundation they build on.

## 1. RunManifest Model

- [ ] 1.1 In `models.py`: define `RunManifest(BaseModel)` with fields: `change_name` (str), `repo_path` (str), `started_at` (str, ISO format), `completed_at` (str, ISO format), `success` (bool), `stages` (list[StageResult]), `total_duration_seconds` (float), `total_cost_usd` (float | None = None), `retries` (int = 0), `pr_url` (str | None = None), `error` (str | None = None).
- [ ] 1.2 In `tests/test_models.py`: test `RunManifest` construction with success and failure cases. Verify `model_dump_json()` produces valid JSON. Verify stages list accepts mixed StageResult subtypes (WorktreeResult, WorkerResult, EvalResult, PrResult).

## 2. Pipeline Manifest Collection

- [ ] 2.1 In `pipeline.py`: at the start of `run_pipeline`, record `started_at = datetime.now(UTC).isoformat()`. Initialize `stages: list[StageResult] = []` and `retries = 0`.
- [ ] 2.2 In `pipeline.py`: after each stage call (create_worktree, dispatch_worker, run_eval, create_pr), append the result to `stages`. Increment `retries` on each retry loop iteration.
- [ ] 2.3 In `pipeline.py`: add `_build_manifest(change_name, repo, started_at, stages, retries, pr_result)` helper that constructs a `RunManifest` from the collected data. Compute `total_duration_seconds` from started_at to now. Sum `cost_usd` from any WorkerResult stages for `total_cost_usd`.
- [ ] 2.4 In `pipeline.py`: add `_write_manifest(manifest, repo)` helper that writes `manifest.model_dump_json(indent=2)` to `<repo>/.action-harness/runs/<timestamp>-<change-name>.json`. Create the directory with `mkdir -p` if it doesn't exist. Log the path to stderr.
- [ ] 2.5 In `pipeline.py`: call `_build_manifest` and `_write_manifest` at the end of `run_pipeline` (both success and failure paths). Return `(PrResult, RunManifest)` tuple.

## 3. CLI Update

- [ ] 3.1 In `cli.py`: update the `run_pipeline(...)` call to unpack the `(PrResult, RunManifest)` return. Log the manifest path to stderr: `[pipeline] manifest saved to <path>`.
- [ ] 3.2 In `cli.py`: exit code logic stays the same (check `pr_result.success`).

## 4. Gitignore

- [ ] 4.1 In `.gitignore`: add `.action-harness/` entry.

## 5. Tests

- [ ] 5.1 In `tests/test_integration.py`: update integration tests for new `run_pipeline` return type `(PrResult, RunManifest)`. Verify manifest contains expected stages, success status, and change name.
- [ ] 5.2 In `tests/test_integration.py`: add test that manifest is written to disk — check `.action-harness/runs/` directory exists and contains a JSON file after pipeline run. Verify the JSON deserializes to a valid `RunManifest`.
- [ ] 5.3 In `tests/test_integration.py`: add test for failed pipeline — verify manifest is written with `success=False` and error field populated.
- [ ] 5.4 In `tests/test_cli.py`: update CLI tests that mock `run_pipeline` to return `(PrResult, RunManifest)` tuple.

## 6. Validation

```bash
uv run pytest -v
uv run ruff check .
uv run ruff format --check .
uv run mypy src/
```
