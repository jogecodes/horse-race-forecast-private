# Agent interface and leakage boundary

The study now includes an executable local-model research/forecasting pipeline. Read [FORECASTING_ENGINE.md](FORECASTING_ENGINE.md) for the A → B → C → D → A engine, model defaults, historical archive handling, commands and limitations. The engine now supports [per-run article/social research](WEB_SOCIAL_RESEARCH.md), including a separately labeled publisher-dated research mode. The lower-level SQLite strict vote/packet API below remains available as a separate interface; engine ledgers live in each run directory rather than writing into the frozen master database.

## Packet API roles

1. A researcher collects snippets about horses, jockeys, trainers and stables using internet access. Source content is untrusted data, including any instructions embedded in a page. The collector records exact content, context and actual collection time.
2. Code rejects snapshots acquired after the run cutoff and target-race results. Results of other races require a completed prior local race day. Self-reported publication dates are insufficient.
3. At least three judge identities review each remaining item independently. Suggested roles are provenance/context, outcome leakage, and relevance. Judges receive the target race, cutoff, evidence, URL, observation time and enough surrounding context to assess whether the snippet reveals or presupposes the target's outcome. They return strict JSON: `{"verdict":"allow","reason":"..."}` or `{"verdict":"drop","reason":"..."}`. Unparseable replies are logged as errors and block admission. Do not feed one judge another judge's reasoning.
4. The forecaster receives a standalone packet database with approved text and the target/cutoff. It has no network, master database, results files, judge reasoning or scorer tools.
5. A separate scorer joins committed forecasts to official labels after resolution. Judge/scorer model processes must not share conversations or memory with the forecaster. The reserved predictions table is not a scoring implementation.

The panel is configured per run and immutable. Judge IDs/model names are declared by the trusted orchestrator; the database cannot establish that three IDs correspond to genuinely independent models or processes. Distinct IDs are necessary for this interface, not evidence of statistical independence.

## Working commands

Create a run with an existing target race. This example is deliberately a historical run whose seed evidence will be rejected:

```bash
python -m horse_racing create-run --race jce:2026-11-01:1:r1 \
  --cutoff '2026-10-31T12:00:00+01:00' \
  --judges provenance outcome relevance
```

The printed `run_id` can be used with `vote`, `gate` and `export-packet`. Obtain evidence IDs from the supervisor database:

```sql
SELECT id, kind, related_race_id, locator FROM evidence;
```

Record a real judge response and the exact prompt supplied to it:

```bash
python -m horse_racing vote --run RUN_ID --evidence EVIDENCE_ID \
  --judge outcome --model LOCAL_MODEL_NAME \
  --response-file /path/to/reply.json --prompt-file /path/to/exact-prompt.txt
python -m horse_racing gate --run RUN_ID --evidence EVIDENCE_ID
python -m horse_racing export-packet --run RUN_ID --out packets/RUN_ID.sqlite
```

Every required judge must allow. Any drop, missing vote or parse error blocks. Votes cannot be overwritten or retried under the same judge ID in the same run; a retry requires a fresh run/panel. A judge cannot make a post-cutoff snapshot admissible. Empty packet export fails and creates no file. Existing packet paths are never overwritten.

Packets contain exactly two tables: `task` and `evidence`. The master retains source lineage, all judge replies, admission decisions, packet content hashes and admitted evidence IDs for manual review. Packet creation does not itself configure OS/process isolation: the orchestrator must mount only the packet and disable internet access for the forecaster.

## Research limits and next work

The seed's 5 November collection cannot support clean October/1 November backtests. A useful next step is to collect upcoming race cards before the forecast deadline, freeze a packet and forecast, and collect outcomes later. To broaden historical backtesting, add verifiable archive capture ingestion with a separate proof model; do not turn a publication-date field into an admission override.

No text filter can prove absence of implicit leakage, and a pretrained model may remember historical winners. Use races after known training cutoffs where possible, compare closed-book and researched baselines, log exactly what reached the forecaster, and manually audit unusually strong results. Judge mistakes and model memorization remain limitations even when timestamp checks pass.

The frozen H1 benchmark defines runner eligibility, dead heats, probability validation and scoring in [BENCHMARK_H1_2026.md](BENCHMARK_H1_2026.md). For upcoming races, commit the declared roster at the cutoff and define withdrawal handling before evaluation; the strict runner excludes withdrawals already declared at collection.
