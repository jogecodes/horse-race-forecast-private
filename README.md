# horse-race-forecast-private

Latest: [15 feature-ablation variants, November 11](docs/FEATURE_ABLATIONS_20261111.md).
Recent form is strongest; no clear replacement for the existing statistical baseline.
Odds collection is paused while model experiments continue.

T-60 odds comparison: [market-watch implementation and provider status](docs/MARKET_WATCH_20261111.md).
The detector is tested; an automatic fixed-odds provider is not yet connected.

Latest experiments: [race-level statistical baselines, November 11](docs/STATISTICAL_BASELINES_20261111.md).
Four CPU variants completed on development races; no held-out evaluation or historical T-60 claim.

The shared-engine development experiment is documented in
[`docs/SHARED_WEEKEND_20261106.md`](docs/SHARED_WEEKEND_20261106.md).
Its live status is `runs/shared_weekend_20261106_gpu3/status.json`.
It imports the sibling forecasting system directly and runs sequentially on GPU 3.

A sibling of `../forecast-cal-private`, starting with a local SQLite database for an agentic horse-racing forecasting toy study. Spanish flat racing is the initial scope. **Database, retrospective benchmark, local forecasting engine and leakage judges are implemented.** No paid services are required.

The populated database is [`data/racing.sqlite`](data/racing.sqlite): **1,593 races, 312 meetings, 8 Spanish venues and 12,872 selected runner-result rows**, spanning **27 November 2022–1 November 2026**. The backfill uses Masdehipódromos public historical results, retaining the original 12 official JCE races as preferred overlapping versions. Masdehipódromos horses/connections use provider IDs; the original JCE names remain provisional and are not silently merged across providers. Full coverage is measured in [`data/coverage_summary.json`](data/coverage_summary.json); this is not certified complete national coverage.

## Use

Python 3.10+, with Beautiful Soup for historical HTML and Requests for the collector. A local `.venv` is prepared. Run commands from this directory:

```bash
source .venv/bin/activate
python -m horse_racing coverage
python -m horse_racing stats
python -m horse_racing seed              # replay the local seed, idempotently
python -m pytest -q                      # needs pytest; synthetic tests, no network/models
```

`python -m horse_racing --help` lists all commands. To create another database, put the global option before the command:

```bash
python -m horse_racing --db /tmp/racing-copy.sqlite seed
```

Read [`docs/DATABASE.md`](docs/DATABASE.md) for the schema, SQL examples and ingestion instructions, [`docs/AGENT_PROTOCOL.md`](docs/AGENT_PROTOCOL.md) for the agent boundary and judge/packet interface, and [`docs/SOURCES.md`](docs/SOURCES.md) for source findings.

## The key temporal rule

**A race date is not a document-availability date.** These seed pages were retrieved on 5 November 2026 and contain results. They cannot support clean forecasts made before those races. The gate consequently rejects them for those historical cutoffs, even if every judge approves. The seed is useful for testing ingestion, labels, research tooling, and later prospective races.

Every source snapshot stores its exact collected text, URL, SHA-256, acquisition method and timezone-aware observation time. Imports preserve revisions and raw runner names. Data and audit tables reject SQL UPDATE/DELETE. This gives an application audit trail; it is not cryptographic tamper resistance against an administrator who controls the database.

Code checks observation time and race context. All judges on a panel of at least three must then approve an evidence item. Missing, malformed and negative votes block admission. Judges cannot override a temporal rejection. A standalone packet database contains only approved snippets and a minimal forecasting task; full result tables, raw pages and judge replies stay in the master database.

This does not eliminate model memorization or mistaken unanimous judge decisions. Forecasters must run with only the exported packet mounted and with network access disabled; a Python API alone is not an access-control sandbox. Prefer prospectively collected future races for credible evaluation. The engine supports per-run article/social discovery and Wayback captures; historical backtests still require verified pre-cutoff rosters, which the H1 bundle currently lacks.

## Current validation

**Deterministic tests pass**, covering both importers, schema migrations, source identity, and leakage controls. Full-cache replay leaves the database unchanged; all 1,595 snapshot hashes verify, and the original JCE snapshot IDs/hashes/timestamps are preserved. All 12 overlapping race winners agree between providers. Details are in [`data/validation_summary.json`](data/validation_summary.json). The seed replay is idempotent; SQLite integrity and foreign-key checks pass. The original declaration/result discrepancy is recorded for ALHAMA RIVER on 25 October: struck through in the declaration but placed eighth, tied, in the results. Both source records are preserved. Historical source weight errors and unclassified status codes are also preserved and flagged. These are data/plumbing checks, not forecasting findings.

Raw source material and generated databases are excluded from version control by default and retained locally. Keep this study private; `-private` in the directory name does not configure remote repository visibility. No repository was published and the original forecasting study was not changed.

## Reproduce or extend the historical backfill

```bash
source .venv/bin/activate
python scripts/discover_mdh.py
python scripts/download_mdh.py
python -m horse_racing import-mdh-cache
python -m horse_racing coverage --out data/coverage_summary.json
```

Discovery follows public seasonal archive links; it does not enumerate guessed race IDs. Downloads are sequential, rate limited, hash checked and resumable. Raw HTML and acquisition metadata are saved under `data/raw/mdh/`. Re-importing the cache is idempotent. The default date scope is 2022 through 5 November 2026; linked pages outside that scope, incomplete results and download failures are explicitly reported in [`data/mdh_import_report.json`](data/mdh_import_report.json).

Results-only pages do not become historical declaration records. Missing saddlecloth numbers remain null; the source's `CS` field is a stall/draw. View `latest_results` selects one result version per race, preferring JCE when present, then the latest acquisition. This supervisor/scorer view is for current labels, not pre-cutoff features. See [`docs/HISTORICAL_BACKFILL.md`](docs/HISTORICAL_BACKFILL.md).

Expert recommendations and the TodoTurf “Resultados” navigation tip are recorded in [docs/EXPERT_RECOMMENDED_SITES.md](docs/EXPERT_RECOMMENDED_SITES.md).

## First-half-2026 benchmark

The [benchmark protocol](docs/BENCHMARK_H1_2026.md) and [frozen bundle](benchmarks/h1_2026_v1/README.md) contain **161 races / 1,395 runner records**, with fields and winners checked against TodoTurf. Chronological splits are 48 development races (January–February), 57 validation races (March–April), and 56 test races (May–June). Uniform and pre-2026-history baselines have been scored. The suite also covers the forecasting engine and odds provenance.

The bundle is explicitly a **retrospective diagnostic**. Its reconstructed fields and event-time histories are not certified historical inputs; all 161 cases remain rejected for strict pre-cutoff agent research until verified archive evidence exists. The protocol records 19 excluded candidates and all source comparisons.

## Forecasting engine and odds

See [docs/FORECASTING_ENGINE.md](docs/FORECASTING_ENGINE.md) for executable commands, bounded internet research, three unanimous judge roles, extractive evidence selection, paired forecasts, audit logs and strict upcoming-declaration runs. Local `llama3.1:8b` is the default. Strict H1 runs remain blocked by missing pre-cutoff roster proof. The CLI defaults to the declaration-based v2 publisher-documented track, with explicit publisher-dated research assumptions. Diagnostic v1 runs require explicit opt-in. Read [docs/WEB_SOCIAL_RESEARCH.md](docs/WEB_SOCIAL_RESEARCH.md) for the per-run researcher, social adapters, judge controls, partial-information behavior and host search bridge.

[docs/ODDS.md](docs/ODDS.md) describes the collected prices: **236 PMU quotes across 14 races**, plus separately labeled post-result `DG` fields for 158 races. The later actual-start recovery identifies 32 quotes across three races nominally within the final minute before official photo-finish start clocks; see the updated odds documentation. The [coverage report](data/odds_h1_2026_report.json) and [CSV export](data/odds_h1_2026.csv) retain that distinction.

## Recovered pre-race benchmark v2

The [declaration-based benchmark](docs/RECOVERED_BENCHMARK_H1_2026.md) now contains **155 races / 1,404 declared runners**, including 54 declared horses omitted from v1 result fields. Inputs come directly from 33 official PDFs, with declared connections, weights, draws and prior-form strings. The new [declaration database](data/declarations_h1_2026.sqlite) is separate from the frozen master. Publisher dating is explicit; independent archive certification remains incomplete. Use `--bundle benchmarks/h1_2026_v2 --track publisher-documented` with the engine.

The [updated odds report](data/odds_actual_start_comparison.json) matches actual-start proof to all 14 PMU-covered races. The [last-minute price CSV](data/odds_preoff_last60s.csv) contains 32 quotes from three races.
