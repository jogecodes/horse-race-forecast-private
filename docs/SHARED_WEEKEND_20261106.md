# Shared forecasting engine development experiment

The horse study imports `/app/more_studies/forecast-cal-dev/forecast_system`
directly. The sibling engine owns the agent workflow, review and aggregation.
`horse_racing/shared_forecast/` owns public racing inputs and declaration-source
mapping. No engine package is installed or duplicated for execution.

Run directory: `runs/shared_weekend_20261106_gpu3/`.

## Frozen design

Twelve races are selected at evenly spaced indices of the chronological list of
48 January–February development races, without looking at outcomes. Their 95
declared runners each receive a binary official-winner forecast, in two arms,
with `llama3.1:8b` and `gemma3:4b`, using seeds 0 and 1: 760 cases total.
Later nonstarters remain targets. A dead-heat first-place finisher resolves YES,
using a positive frozen target share only in the separate evaluator.

Both arms receive the same current official declaration and full declared field.
The declaration-only arm has an empty search corpus. The research arm can search
368 structured runner declarations from the development period. Search and fetch
filter by the original publisher-claimed availability date before exposing any
metadata. These are identified structured extractions, with document URL, hash,
retrieval timestamp and original timing receipt; they are not invented article
titles or independently certified archival captures. Previously printed form,
weights and connections may provide additional context across declarations.
No results or reconstructed result-derived career histories enter this corpus.

This is a bounded corpus research experiment, not an open-web or social-media
experiment. There is no unattended chat-tool dependency or external network
research. Validation/test races, market odds and paid models are excluded.

The shared engine is binary-only. Runner probabilities are scored as binary
events and their unmodified sums are reported for complete races. They are never
normalized into race distributions or submitted to the existing multiclass race
scorer. Reports include coverage, retained evidence, raw binary Brier, a uniform
1/field-size comparator on the same valid subset, and research-minus-declaration
Brier on common valid runner cases. Seeds and runners within a race are dependent;
these descriptive development results are not independent evidence of improvement.
The repeated seed is not assumed to cause stochastic diversity at temperature 0.

## Lifecycle and inspection

Only GPU 3 is authorized. A dedicated Ollama service uses its GPU UUID and port
11439, one loaded model and one request at a time. No other service is stopped or
reconfigured. Existing installed-model digests are saved in `runtime.json`.
The controller runs detached from the chat. It continues until all 760 cases
have been attempted, including after Monday morning if needed. The user explicitly
removed the original Monday cutoff. Each case has a
900-second wall-clock bound and the shared configuration caps model calls,
queries, sources and context. This does not survive a machine shutdown.

`status.json` contains progress, current case, controller and owned service PIDs.
`controller.log`, `smoke_controller.log` and `ollama.log` capture process output.
Each `cases/case_*/attempt_*/` retains its trace, raw model responses, worker log,
result or exception. A timeout becomes a missing forecast, never a substitute
probability. Completed `outcome.json` records are skipped on restart; incomplete
attempt directories are preserved and a new numbered attempt is created.
`evaluation/summary.json` is refreshed after race blocks and on shutdown.

`manifest.json` freezes code, selected packets, database/bundle hashes, public
corpus, cases, configuration and stop time. Source snapshots are audit records
only: subprocesses still import the sibling. A detected engine/adapter source
change stops the queue before another case, preventing mixed-version results.
The original deadline manifest/source and stopped checkpoint are preserved under
`lifecycle_revisions/001_before_remove_deadline/`. Only scheduling and socket
restart handling changed; forecasting settings and completed results are retained.
Code and input hashes are checked on restart and original input hashes again at
shutdown. The lock prevents duplicate controllers for this run directory.

To resume a stopped run, after ensuring GPU 3 is free:

```bash
cd /app/more_studies/horse-race-forecast-private
/app/more_studies/forecast-cal-private/.venv/bin/python \
  scripts/run_shared_weekend.py --out runs/shared_weekend_20261106_gpu3
```

Use a detached process with redirected logs for a long restart. Do not restart
while its controller is running. To request a graceful stop, send SIGTERM to the
controller PID in `status.json`; it finishes the current bounded case, scores,
and stops only its own service. The same command with `--smoke` runs four cases
covering both models and arms. `--prepare` requires a new output directory.

The horse virtualenv lacks jsonschema. The experiment uses the existing sibling
research interpreter, which already has requests, jsonschema and pytest. No
dependencies or models were downloaded. The optional `shared-experiment`
dependency is documented in pyproject; ordinary horse tests skip this optional
integration module if jsonschema is absent.

Validation: 133 existing horse tests passed; five new integration checks passed
using the sibling interpreter. They exercise outcome-free mapping, development
restriction, actual source provenance, hidden future metadata/fetches, missing
and invalid probabilities, dead-heat binary resolution, and success/failure
persistence through the real shared engine with a deterministic test client.
Actual local-model smoke results and live progress are in the run directory.
