# Spain H1 2026 race benchmark, v1

The frozen bundle is [`benchmarks/h1_2026_v1/`](../benchmarks/h1_2026_v1/). It contains **161 races and 1,395 runner records** from January–June 2026, with winners and full recorded fields cross-checked between the existing database and TodoTurf. There are no remaining field or winner-name disagreements among included races.

**This is a runnable retrospective diagnostic, not a certified leakage-free historical agent experiment.** Its field lists were reconstructed from post-race results collected in November 2026. Histories contain only events before 2026, but their historical publication times are unverified. Every case therefore fails strict historical input admission. No model/judge agent calls have been run or fabricated. The existing evidence gate has not been relaxed.

## Selection and coverage

TodoTurf's public Spain-2026 results filter lists 180 H1 races across 36 meetings. The primary database contains 170 of those races. The benchmark uses every candidate satisfying the same rules, without sampling on model performance:

- Match the race date, venue and displayed order across sources, with a unique primary race identity.
- Require at least three recorded runners and an identified winner.
- Require identical normalized horse-name sets and first-place horse-name sets across sources.
- Exclude a race if either source has an unresolved runner status. A code such as 95/98/99 is not guessed to mean withdrawal or disqualification.
- Preserve all exclusion reasons and the primary/secondary comparison rows in supervisor audit files.

The exclusions are **10 missing primary races**, all at La Zarzuela on **18 and 25 June**, and **9 races with unresolved statuses**. These are 19 distinct races; the status reason is recorded separately for each provider. Both providers may share upstream information, so agreement is a consistency check, not proof of independent reporting or official adjudication.

TodoTurf declares conflicting legacy and UTF-8 encodings, while its actual payload is UTF-8. The result parser decodes UTF-8 explicitly; a regression test covers names containing Ñ/ñ. No manually selected horse-name aliases or outcome-dependent exceptions were used.

| Split | Date range | Races |
|---|---|---:|
| Development | 1 January–28 February 2026 | 48 |
| Validation | 1 March–30 April 2026 | 57 |
| Test | 1 May–30 June 2026 | 56 |

| Venue | Races |
|---|---:|
| La Zarzuela | 99 |
| Dos Hermanas | 40 |
| San Sebastián | 19 |
| Vila-seca | 3 |

Whole meetings remain in the same split. Reappearing horses are allowed: the task measures forecasting later races, not generalization to entirely unseen horses. Venue/season distributions differ between splits, and the missing June meetings limit representativeness. This is not a claim of complete national coverage.

## Forecast task and input boundary

For each race, produce a probability distribution over the listed runners, keyed by the supplied opaque `runner_id`. Probabilities must be finite numbers in [0,1], cover exactly the listed runners, and sum to one within 1e-6. Booleans, missing/extra runners, NaN, negative values and duplicate race predictions are invalid. The scorer does not normalize or impute replies.

The nominal cutoff is **23:59 Europe/Madrid on the previous calendar day**, converted to UTC with DST handling. This is earlier than the target race day and does not depend on unverified start-time strings.

Each diagnostic packet contains only whitelisted fields: race/date/venue/distance, split/cutoff/track, runner IDs and horse names, and pre-2026 history counts. Runner order is a deterministic hash independent of finishing position. No positions, statuses, result-row order, target-race weights, margins, times, going, dividends, prize payments, source URLs or judge replies are exported in the packet.

History features are **frozen through 31 December 2025 for every split**. They count recorded appearances and fractional win shares in earlier races whose runner statuses are all interpretable. No development, validation or test outcomes update these features. The supervisor history file preserves the source observation times, showing why the history is event-time reconstructed rather than certified pre-cutoff evidence.

Mount **only the current race's packet** in the forecaster process. Keep all other packets, `supervisor/`, the master DB and raw HTML inaccessible. Disable the forecaster's network access. Internet research belongs in a separate process and must pass the existing timestamp checks and required provenance/outcome/relevance judges before anything reaches the forecaster. Judges cannot override a deterministic rejection. The benchmark's admission audit records the rejection and `judge_votes: not_run` for every reconstructed packet.

Tune prompts and parameters on development, then validation. Reserve test for the final comparison; do not tune to its labels or baseline results. Changing the population, features, rules or protocol requires a new benchmark version.

## Labels and scoring

The target is a one-hot distribution on the first-place horse. For a dead heat, equal target mass is assigned to every first-place horse; this rule is tested even if a particular bundle contains no such case.

The primary score is the mean **multiclass Brier score**, with each race weighted equally:

`Brier(race) = sum_over_runners((prediction - target)^2)`

The secondary score is cross entropy/natural-log loss. A fixed **1e-15** floor avoids non-JSON infinity for zero winner probabilities; the report separately counts those cases. Probability vectors are not otherwise adjusted. The top-1 diagnostic averages target mass over runners tied for maximum probability, so tied forecasts and dead heats receive explicit fractional credit.

Reports include coverage, parsing rate, invalid/missing reply reasons, Brier skill and log-loss improvement against a uniform forecast on exactly the same scored races, plus month and venue breakdowns. Invalid replies are excluded from the metrics and remain in the coverage denominator. A run is marked `leaderboard_eligible` only at full coverage with no malformed lines; do not compare partial-coverage scores as if they were full benchmark results.

Confidence intervals use **1,000 bootstrap resamples of whole meetings**, seed 2026, with percentile 95% intervals. Races within a meeting are not treated as independent resampling units. Groups with fewer than two meetings have no interval. The test set has only 12 meetings, so intervals remain limited.

## Frozen baselines and measured test results

- **Uniform:** each runner gets 1/N probability.
- **Frozen history:** weight each runner by `(pre_2026_win_share + 1) / (pre_2026_starts + 10)`, then normalize over this field. These smoothing constants were fixed before running the baselines and were not tuned on test outcomes. An unseen horse has the prior weight 1/10.

Both prediction files cover all 161 cases; the table below scores only the 56 test races.

| Baseline | Test Brier ↓ | Test log loss ↓ | Prediction coverage |
|---|---:|---:|---:|
| Uniform | 0.873249 | 2.117036 | 100% |
| Frozen history | 0.862110 | 2.097035 | 100% |

The history baseline's Brier skill against uniform is about 1.28%, with a meeting-bootstrap 95% interval of approximately **−0.72% to +3.74%**, which includes zero. These are measured diagnostic baselines, not a finding of reliable or leakage-free forecasting skill.

Exact predictions, scores and confidence intervals are in `baselines/`. No market baseline is included because the collected post-race dividends do not establish pre-cutoff odds.

## Commands

From the study root, activate `.venv` first. The public TodoTurf collector caches the filtered index, 36 meeting pages and 180 linked race pages sequentially with request spacing and byte hashes:

```bash
source .venv/bin/activate
python scripts/collect_todoturf_benchmark.py
python -m horse_racing build-benchmark --out benchmarks/h1_2026_v1
```

The delivered bundle already exists; the builder refuses to overwrite it. To check a rebuild, use a different output directory and compare manifests.

```bash
python -m horse_racing benchmark-baseline --kind uniform \
  --out /tmp/uniform_predictions.jsonl
python -m horse_racing benchmark-baseline --kind history \
  --out /tmp/history_predictions.jsonl
python -m horse_racing score-benchmark \
  --predictions /tmp/history_predictions.jsonl --split test \
  --out /tmp/history_test_scores.json
```

Prediction files are JSONL records containing `race_id` and a `probabilities` object mapping the packet's runner IDs to numbers. The scorer defaults to `--split test`; development, validation and all-race diagnostics can be selected explicitly. It verifies all frozen core artifact hashes before evaluation and refuses to overwrite score/prediction outputs.

## Bundle files and provenance

- `manifest.json`: population counts and SHA-256 hashes for the builder, master DB, TodoTurf collection manifest and every frozen core artifact.
- `protocol.json`: versioned split, cutoff, label, scoring, baseline and exclusion rules.
- `diagnostic/tasks.jsonl`: task index without labels.
- `diagnostic/packets/*.json`: one whitelisted diagnostic input per race.
- `supervisor/labels.jsonl`: gold targets; never mount for forecasters.
- `supervisor/cases.jsonl`: internal runner/race mappings and both providers' source hashes, URLs and acquisition times.
- `supervisor/secondary_audit.jsonl`: full source comparison for all 180 indexed races.
- `supervisor/exclusions.jsonl`: excluded population and explicit reasons.
- `supervisor/admission_audit.jsonl`: strict temporal rejection and required judge roles; no invented votes.
- `supervisor/history_before_2026.jsonl`: frozen historical records and availability metadata.
- `baselines/`: generated predictions and measured held-out scores.

The master database is opened read-only by the builder. Raw TodoTurf pages and acquisition sidecars live in `data/raw/todoturf_h1_2026/`. Generated benchmark data remains local and private by default. Input authenticity ultimately relies on the trusted collector; hashes establish reproducibility, not independently certified publication times.

A future strict historical track needs archived pre-race declarations and independently verified pre-cutoff history/research snapshots. Pretrained model memorization remains a separate concern even with such archives; model cutoff evidence and closed-book controls will be needed before interpreting agent/model results.
