# Forecasting engine and leakage controls

The executable engine is `horse_racing/engine/`, adapted from the A → B → C → D → A research architecture in the sibling `forecast-cal-private`. The sibling and frozen H1 benchmark have not been modified. Models run locally through Ollama; there is no hosted fallback, automatic model download or paid search dependency.

## Run

From this study directory, with Ollama listening on `127.0.0.1:11434` and `llama3.1:8b` installed:

```bash
source .venv/bin/activate
# Declaration-based H1 v2 with explicit publisher-date assumptions is the default.
python scripts/run_forecasting_engine.py --out runs/my-research-run --limit 2
# Full strict mode correctly blocks H1 cases lacking independent roster proof.
python scripts/run_forecasting_engine.py --out runs/my-strict-run --track strict --limit 2
# Explicitly opt into reconstructed, time-unverified benchmark inputs.
python scripts/run_forecasting_engine.py --out runs/my-diagnostic-run \
  --bundle benchmarks/h1_2026_v1 --track diagnostic --split development --limit 2 --rounds 1
python scripts/evaluate_leakage_judges.py --out runs/my-judge-probe
```

Output directories must be new. Development is the default split. Use `--split validation` or `--split test` only after fixing the research protocol. A limited run reports coverage against the entire selected split, and also records the subset on which both arms returned valid forecasts. No two-race smoke result establishes forecasting skill.

For an upcoming race, first collect/import its actual declaration through the existing database ingestion interface, then run:

```bash
python scripts/forecast_declared_race.py --race SOURCE_RACE_ID \
  --cutoff '2026-11-07T22:00:00+00:00' --out runs/my-declared-race
```

The example date is illustrative: the race must be on a later calendar day in Europe/Madrid, and its declaration must already have been collected by the cutoff. This command derives the roster and jockey/trainer/stable names from a collected declaration. It excludes declared withdrawals, refuses result-only races, reads no outcome labels, and strips diagnostic history. Until actual-off timestamps are verified, strict declaration runs deliberately require a deadline before race day. Collect subsequent withdrawals and outcomes separately; do not silently change a committed field. There is no automatic scheduled race monitor in this release.

## Roles and boundaries

1. **A, planner:** requests at most two information needs per round, for one to three rounds. Requests can concern earlier form, distance/track suitability, jockeys, trainers, stables or conditions. Invalid plans fall back to a query using a listed horse's name; forecasts never fall back to invented probabilities.
2. **B, researcher:** formulates fresh article and public social-post searches per race, covering horses and connections within bounded budgets. It selects real discovered candidate IDs and fetches original source text. Search snippets remain discovery-only. Public X, Bluesky and Telegram post adapters complement dated article HTML; unavailable material leaves a recorded gap. Use the standalone RSS provider or the host internet-search bridge. See [WEB_SOCIAL_RESEARCH.md](WEB_SOCIAL_RESEARCH.md) for commands and protocol.
3. **C, code and judges:** code validates provenance and exact UTC timestamps under the explicit strict or publisher-dated policy. Publisher dating is an assumption about availability, with unverified edit history; strict mode still requires archive or pre-cutoff live observation. Clear future realized facts are rejected; planned race dates receive semantic review. Only surviving passages reach three stateless judge roles: provenance, outcome leakage, relevance. Every role must allow; malformed/missing replies, errors or a veto block admission. No judge can override code rejection.
4. **D, extractive selector:** chooses only code-generated sentence IDs, with offsets and the whole admitted paragraph attached. Unknown IDs cannot introduce text. At most five selections within a serialized context budget reach the predictor. The system admits at most eight paragraphs per race.
5. **A, forecaster:** receives a whitelisted task and the selected source text in a fresh conversation. It receives no rejected text, judge reasoning, raw search results, outcome labels, source-retrieval tools or database tools. The orchestrator validates exact runner identity, finite probabilities, duplicate JSON keys and a sum of one. At most two complete model attempts are allowed with validation feedback; invalid forecasts remain excluded. There is no renormalization or missing-value imputation. Short model-facing runner IDs have an audited bijection to the benchmark IDs, with probability values unchanged. Missing research coverage is explicitly unknown.

The default for all roles is `llama3.1:8b`, temperature zero, with distinct judge seeds. They are **three roles sharing one set of weights**, not three independent trained models. Judge mappings can be configured through the Python interface. Separate conversations prevent shared conversational state; they cannot remove correlations or historical winners memorized during training. The installed Gemma model failed arithmetic and/or judge probes and is not the default.

For retrospective runs only, the supervisor can supply known winners to the outcome judge. These labels are not supplied to the other judges, planner, selector or predictor. Judge prose stays in the restricted audit log and cannot become forecast evidence. The declared-race runner reads no labels.

## Availability and audit

Strict H1 runs require a collected, pre-cutoff declaration whose horse set matches the benchmark. The current historical database has no such proof for the 161 H1 cases. A flag inside a packet cannot certify its own availability. The diagnostic switch is therefore necessary to run those reconstructed cases; their rosters and pre-2026 aggregate form remain time-unverified.

Wikipedia evidence must match an exact revision ID and timestamp in metadata and content responses. Wayback evidence must match the requested original URL, capture stamp, successful HTML response and immutable capture URL. Live content is available at its actual acquisition time. A 2026 race date does not make a page collected in November available in January.

Every run preserves model names/digests, options, engine source snapshots/hashes, exact prompts, raw responses, HTTP receipts, decisions, committed predictions and scoring coverage. JSONL events form a hash chain; the run manifest hashes complete ledgers. `horse_racing.engine.run.audit_run(path)` verifies frozen code, ledger integrity and the recorded approval/selection/forecast data flow. Administrator-controlled files are not an externally anchored tamper-proof log. Raw receipts and confidential labels must stay out of forecaster-visible artifacts.

This implementation enforces the boundary through code-owned requests and stateless model messages. It does **not** configure an OS sandbox for the supervisor, researcher, judges and predictor. Do not describe it as a proof of leakage freedom or grant the predictor separate filesystem/browser tools. A production deployment should isolate processes and mount only predictor packets. Judge mistakes, current-search selection bias, implicit leakage and model memorization remain limitations.

## Local verification

`runs/h1_diagnostic_final` records two development races, with a closed-book and researched arm for each. All four forecasts were valid, and ledger audits passed. No historical passage was admitted: unavailable archives and post-cutoff live sources were not converted into historical evidence. Consequently this smoke tests execution and rejection, not a research advantage.

`runs/h1_strict_final` records both requested races blocked before model calls. `runs/leakage_judge_probe_v3/report.json` records four explicitly synthetic real-model probes: earlier history admitted; undated target outcome, prompt injection and post-cutoff source blocked. These are plumbing probes, not a validated estimate of judge sensitivity. Earlier failed probes and malformed forecast runs are retained locally rather than included in scores.

`runs/synthetic_pipeline_smoke` also exercises the entire positive path with actual local-model calls and explicitly synthetic evidence: one paragraph unanimously admitted, one exact sentence selected, a valid forecast emitted and the full audit passed. This fixture is not a claim about a real race.

Run `python -m pytest -q` for the deterministic tests without models or internet. Tests cover timestamp/provenance rejection, model-role data separation, selector extraction, invalid predictions, strict declaration requirements and audit tampering.

## Declaration-based H1 v2

[RECOVERED_BENCHMARK_H1_2026.md](RECOVERED_BENCHMARK_H1_2026.md) describes the new 155-race declaration bundle. The CLI defaults to `--bundle benchmarks/h1_2026_v2 --track publisher-documented`. This mode accepts the bundle's publisher-dated official declaration inputs, with no reconstructed career aggregates. Research defaults to the separately labeled publisher-dated policy; use `--research-policy strict` for archive/pre-cutoff collection requirements. Undated current horse profiles remain inadmissible. Full strict mode has not been relaxed. See [WEB_SOCIAL_RESEARCH.md](WEB_SOCIAL_RESEARCH.md).

## Article/social research validation

The [per-run research guide](WEB_SOCIAL_RESEARCH.md) documents the current discovery agent, public post adapters, publisher-dated policy and search bridge. A live seeded four-runner integration admitted two historical paragraphs, selected one exact sentence and produced a valid forecast; the audit passed. An eight-runner run reached the same evidence handoff but both forecast distributions failed validation and were excluded. The current suite has 97 deterministic tests; four synthetic real-model leakage probes also passed. See `data/web_research_validation.json`.

## Exploratory semantic policy

The optional `--research-policy exploratory` lets undated article passages reach the temporal, outcome and relevance judges, recording unavailable publication times as null. It preserves explicit source-date blocks, requires exact supporting quotes, and keeps uncertain decisions outside predictor inputs. Existing defaults and strict declarations remain unchanged. The 24-scenario real-passage diagnostic is described in [SEMANTIC_REVIEW.md](SEMANTIC_REVIEW.md); its annotations were assigned by the assistant before evaluation and are not independent human labels.
