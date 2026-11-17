# Per-race internet research

Each researched forecast starts a fresh discovery session. A separate local research agent formulates article and social-post searches about the declared horses, jockeys, trainers and stables. Three separate judge conversations assess provenance, outcome leakage and relevance. An extractive selector passes approved sentences to the forecasting agent, which uses them alongside the declaration. The roles currently share the installed `llama3.1:8b` weights, with stateless requests and different prompts; they are not independently trained models.

Partial information is expected. A failed search, inaccessible post, missing publication date or judge veto leaves an explicit gap. The forecaster receives a coverage summary and approved evidence; unavailable information is unknown, not negative evidence. No missing fact or probability is filled in.

## Run

From this directory with the existing virtual environment and local Ollama running:

```bash
.venv/bin/python scripts/run_forecasting_engine.py \
  --out runs/my-web-research --limit 2 --rounds 2 \
  --max-search-queries 12 --max-research-pages 12
```

Defaults are the frozen 155-race H1 v2 bundle, development split, publisher-documented declarations and publisher-dated research. The standalone search provider uses public Bing RSS. It can return poor or irrelevant results and may ignore date operators; every original source is independently fetched and dated. Coverage is measured, not assumed. Search failures remain in the audit.

Use `--seed-url https://publisher.example/article` to investigate a known candidate as well as discovered URLs. Seeds undergo the same source and judge checks. Budgets are per race: by default 12 searches, 12 pages and 64 HTTP requests. Targets interleave horses, jockeys, trainers and stables and deduplicate repeated connections. Limited budgets need not cover every entity. Increase the explicit budgets (at most 64 queries / 32 pages) or research rounds (at most three) when needed.

To use a separate existing local Ollama service, pass `--ollama-base http://127.0.0.1:11436`. The endpoint is recorded in the run manifest. Select a fixed pilot with repeated `--race-id RACE_ID` arguments; these override `--limit`, preserve the requested order, and must all belong to the selected split. Duplicate or empty selections are rejected before creating run artifacts.

For strict historical research:

```bash
.venv/bin/python scripts/run_forecasting_engine.py \
  --out runs/my-strict-research --research-policy strict --limit 1
```

This keeps the v2 publisher-documented roster but requires stronger provenance for research. A fully strict run additionally needs `--track strict`; current H1 rosters lack independently verified pre-cutoff acquisition, so those runs stop before forecasting.

For future races, import a declaration before the deadline, then use `scripts/forecast_declared_race.py --race SOURCE_RACE_ID --cutoff ISO_TIMESTAMP --out runs/NEW_DIRECTORY`. It exposes the same search backend and budget flags and always uses strict provenance. It reads no outcome labels. Existing strict declaration rules require a deadline before local race day.

## Exploratory content review

Use `--research-policy exploratory` to assess undated articles semantically. Publication/availability remains unknown rather than being invented. Explicit post-cutoff source dates still block passage. Judges return allow/drop/uncertain with exact supporting quotes; only unanimous allow can reach the forecaster. See [SEMANTIC_REVIEW.md](SEMANTIC_REVIEW.md) for the policy, reviewed genuine-source dataset, evaluation commands and limitations. This policy is retrospective and cannot be used by the strict prospective declaration runner.

## Search-tool bridge

For an agent host with a general internet search tool, use `--search-backend stdio`. This replaces the RSS provider with a fresh query/response bridge. The research agent still decides what to search and which candidate IDs to investigate. The host executes the search rather than inventing results.

The process prints one JSON line per query:

```json
{"event":"web_search_request","request_id":"REQUEST_ID","query":"agent-generated query","cutoff_utc":"2026-01-03T22:59:00+00:00","kind":"social"}
```

The host calls its search tool with that query and writes a matching line to stdin:

```json
{"request_id":"REQUEST_ID","results":[{"url":"https://publisher.example/original-article","title":"Actual search result title","snippet":"Actual search result snippet"}]}
```

Return an empty results list when no results exist. Other stdout lines report statuses and summaries; dispatch on `event`. End-of-input and malformed/mismatched replies become research failures. Python callers can instead supply `Explorer(..., search_provider=callable)` with signature `(query, cutoff, kind) -> list[dict]`. Search titles/snippets are visible only to the researcher; they cannot become evidence. This bridge was exercised with live host web-search calls in `runs/web_social_agent_smoke` and `runs/web_social_agent_smoke_v2`; neither run admitted evidence, and their malformed forecasts remain excluded.

## Sources and temporal decisions

The researcher fetches the actual article or individual post. Supported public social adapters include X public oEmbed, Bluesky public post records, and Telegram public post embeds. Other accessible dated article/post HTML can be extracted, including public Facebook/Instagram pages when available. Login walls, challenges, deleted pages, rate limits, inaccessible media and undated profiles remain unavailable. Video/audio is not transcribed. The engine does not bypass access controls.

Every source records the original URL, fetched text hash, actual observation time, date claims and extraction path, and its research target. Public HTTPS redirects are bounded and destination-checked; historical archive-capture redirects are rejected. Publisher extraction excludes related-news teaser dates and site widgets.

The two provenance policies are below; the separate exploratory content policy is described above:

- **Strict:** pre-cutoff live observation or an exact pre-cutoff Wayback capture. Fetching an old-looking article today is insufficient.
- **Publisher-dated:** accepts a supported explicit publication date, with all supported update dates checked too. The latest date must precede the cutoff. Date-only claims use the end of that date in Europe/Madrid. Missing timezone information is not invented. The receipt states that unchanged historical text/edit history has not been independently verified. These runs are not certified strict backtests.

Search date operators only guide discovery. Code-owned provenance checks cannot be overridden by judges. Earlier completed races can inform a later forecast. A preview mentioning a planned future race goes to semantic review; it is not automatically discarded solely for that date. Clear realized future outcomes are blocked. Only the outcome judge may receive confidential known winners in retrospective runs; its reasoning and labels never reach the predictor.

All three judges must allow a passage. A veto, missing reply, malformed reply or error blocks it. At most eight paragraphs are admitted and five exact sentence selections reach the forecaster, with the full admitted paragraph attached as context. The predictor receives neither raw search results, rejected text, judge prose nor browsing tools.

## Audit and output

Each run writes `run_manifest.json`, hash-chained `ledgers/`, fetched source receipts, `research_reports.jsonl`, forecasts, scores and `audit_report.json`. Coverage distinguishes attempted searches, fetched sources and actually approved passages for each entity. Research reports can contain discovery metadata and should stay outside the predictor's input boundary.

For local-model output, short IDs `r1`, `r2`, etc. have an audited one-to-one mapping to benchmark runner IDs. Probabilities are passed through unchanged. At most two complete model attempts are permitted; the second receives only validation feedback, including an invalid total when applicable. Both replies are retained. A malformed distribution after both attempts is excluded, never normalized or completed. The audit verifies the exact mapped values against the actual model response.

`runs/web_social_agent_final` demonstrates valid forecasts with zero admitted evidence and a passing data-flow audit. `runs/web_social_small_field_handoff` completes the live seeded evidence path on a four-runner development race: two dated prior-performance paragraphs unanimously admitted, one exact sentence selected, a valid first-attempt forecast and a passing audit. The unrelated public post was retrieved but contributed no selected evidence. An eight-runner check in `runs/web_social_evidence_handoff_v5` admitted two paragraphs and selected one sentence but emitted invalid probability totals twice; it remains excluded. These checks and deterministic fixtures are implementation validation, not evidence of forecasting skill. All 97 deterministic tests and the four synthetic real-model leakage probes passed; see `data/web_research_validation.json`. The documentation in `FORECASTING_ENGINE.md` describes the remaining process-isolation boundary.

## Event-grounded experimental policy

`--research-policy event-grounded` adds a separate event identity/chronology resolver and code-owned sentence citations. It remains optional. See [EVENT_GROUNDED_REVIEW.md](EVENT_GROUNDED_REVIEW.md) for the full protocol and fresh evaluation.
