# Testing and Evaluation

## Unit and route tests

The `TESTS/` directory uses Python's `unittest` framework. Run the suite from the repository root:

```powershell
python -m unittest discover -s TESTS -v
```

The suite covers route contracts and authentication/session ownership, Supabase data helpers, agent behavior, RAG, and documentation generation. Live integration tests are opt-in; for example, documentation-agent live tests require `OPENFORGE_RUN_LIVE_DOC_TEST=1` and a configured repository URL. Use test credentials and avoid running live tests against repositories or accounts you do not control.

## Live HTTP evaluation

The evaluator in `Evalution/online.py` exercises a running API using the cases in `Evalution/dataset.json`. It checks health, creates a temporary chat, sends agent requests, checks response fields, verifies saved session history, and deletes the chat unless `--keep-session` is set.

Required values:

- `OPENFORGE_EVAL_ACCESS_TOKEN`: access token belonging to a dedicated evaluation user.
- `OPENFORGE_EVAL_REPOSITORY_ID`: already indexed repository in `owner/name` form.

Optional values:

- `OPENFORGE_API_URL`: base URL; defaults to `http://127.0.0.1:8000`.
- `--repository-url`: GitHub URL for documentation evaluation; otherwise derived from the repository ID.
- `--dataset`: alternate dataset JSON.
- `--output`: write the JSON report to a file.
- `--keep-session`: retain the temporary session and transcript.

Example in PowerShell:

```powershell
$env:OPENFORGE_EVAL_ACCESS_TOKEN = "<evaluation access token>"
$env:OPENFORGE_EVAL_REPOSITORY_ID = "owner/indexed-repository"
python -m Evalution.online --base-url http://127.0.0.1:8000 --output .\evaluation-report.json
```

Documentation and repository-discovery cases are marked skipped when their optional GitHub MCP integration returns HTTP 503. Other failures produce a nonzero process exit code. The evaluator prints a JSON report with pass/fail/skip counts, pass rate, per-case timing, and the session ID. The summary also reports nearest-rank p50/p95 case latency, the number of latency samples, and HTTP success/error counts and rate for results that include an HTTP status. These latency values describe evaluator case requests, not pure model-generation time; the overall duration includes setup and cleanup. Skipped optional integrations are excluded from the pass-rate denominator. The report does not calculate answer correctness, RAG groundedness, or retrieval Recall@K/MRR unless a separate labelled dataset is evaluated.

## Suggested development loop

1. Run the narrow relevant test module while changing an agent or route.
2. Run the full `unittest` discovery command before merging.
3. For integration changes, run the online evaluator against a dedicated test account and a repository that has been indexed for that account.
4. Confirm temporary sessions were deleted unless intentionally retained.

The online evaluator exercises external model and GitHub behavior, so results depend on credentials, provider availability, repository state, and configured model output. It is a contract check, not a deterministic quality benchmark.