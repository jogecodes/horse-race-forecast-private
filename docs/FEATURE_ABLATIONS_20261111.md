# Feature experiments: what contributes to race forecasts?

Completed run: `runs/feature_ablations_20261111/`. Fifteen variants were compared
on four chronological 2025 folds (432 races, 85 meeting clusters), followed by
the existing 48 January–February 2026 development races (ten meeting clusters).
No GPU, LLM inference, odds collection or 2026 validation/test evaluation occurred.
The existing reference model is retained; no replacement is promoted.

## Design

`horse_racing/ablation.py` adds a prior winner-strength rating to the six existing
features. Before each race, the rating predicts a softmax distribution over the
historical field. After the entire calendar day, each horse receives
`0.5 * (win_share - expected_win_share)`. The step 0.5 is fixed in advance.
All same-day races use the earlier-day rating state. Unknown horses start at 0.

Feature groups are career form (smoothed win rate and recorded appearances),
recent form (last-three mean finish strength), distance-weighted win rate,
recency, and winner rating. Missing-history indication accompanies each single
group. Variants include uniform/smoothed-history baselines, the exact six-feature
reference, the seven-feature model, individual groups, recent form plus rating,
removal of each group from the seven-feature model, and removal of missingness.

Each outer fold uses successively later training/tuning/calibration/evaluation
periods. Tuning selects L2 strength from 0.01/0.1/1; refitting combines training
and tuning, then temperature is selected on a separate pre-evaluation period
from 0.5/0.75/1/1.5/2/3. The model coefficients stay fixed in each evaluation
period, while historical features and ratings may use strictly earlier-day
observed results, as a prequential simulation.

| Evaluation | Training ends before | Tuning | Calibration |
|---|---|---|---|
| 2025 Q1 | July 2024 | 2024 Q3 | 2024 Q4 |
| 2025 Q2 | October 2024 | 2024 Q4 | 2025 Q1 |
| 2025 Q3 | January 2025 | 2025 Q1 | 2025 Q2 |
| 2025 Q4 | April 2025 | 2025 Q2 | 2025 Q3 |

The lowest pooled 2025 outer-fold log loss selects a candidate, recorded before
2026 predictions and outcome scoring. Candidate: `recent_and_rating`, including
the missing-history indicator. All variants' 2026 models then follow the original
reference protocol: train through 2024, tune January–September 2025, refit,
temperature-scale October–December 2025, freeze all horse histories at end-2025.
Do not choose a different candidate based on the best 2026 development result.

## Findings

| Variant | 2025 race Brier | 2025 log loss | 2026 dev Brier | 2026 dev log loss |
|---|---:|---:|---:|---:|
| Uniform | 0.853208 | 2.002524 | 0.858198 | 1.996261 |
| Existing full model | 0.827652 | 1.913033 | 0.823292 | 1.870464 |
| Full model + rating | 0.829760 | 1.921183 | 0.823702 | 1.871432 |
| Recent form only + missingness | 0.826646 | 1.912012 | 0.832138 | 1.898579 |
| Recent form + rating + missingness | 0.826223 | 1.911267 | 0.823160 | 1.872065 |
| Full + rating, without recent form | 0.846719 | 1.984904 | 0.840812 | 1.936887 |

Recent form is the strongest current feature group: removing it worsens log loss
in all four 2025 folds and in 2026 development. Career form, distance and recency
have inconsistent conditional contributions. This evaluates these particular
representations, not whether distance or lifetime experience matters in racing.
Adding the new rating to every existing feature does not give a consistent gain.

The selected recent-plus-rating candidate beats the reference's log loss in
three of four 2025 folds, but its pooled gain is only 0.001766. Its descriptive
95% meeting-cluster interval for log-loss difference is [-0.008186, 0.004840].
On 2026 development, its log loss is worse by 0.001600; interval
[-0.026669, 0.025595]. Its Brier improvement there is only 0.000133. All those
intervals include zero. They are not adjusted for selection among variants.

The lowest 2026 log loss happens to be the model omitting distance form, but
that was not the candidate selected on 2025. It is an exploratory observation,
not a reason to claim successful selection or replace the reference model.

## Verification and interpretation

All 720 development distributions preserve the full declared runner set and sum
to one. The six-feature reference exactly reproduces all original probabilities
(maximum difference 0.0). The established benchmark scorer independently
reproduces the selected candidate's scores and 48/48 coverage. Original inputs,
source hashes, database and earlier-run artifacts remain unchanged.

Four new tests cover earlier-day-only rating updates, future-label invariance,
feature-removal isolation/metadata, chronological boundaries, and unknown-horse
rating behavior. New ablation/statistical tests: 11 passed. Full default suite:
154 passed, one optional shared-engine module skipped.

This remains retrospective development using result-reconstructed historical
fields and publisher-documented target declarations. No fresh held-out claim,
market edge, calibrated uncertainty guarantee, causal feature effect, or T-60
availability claim follows. Country is not a requirement for future data, but
this experiment intentionally uses only the existing dataset.

Next: improve and validate the representation of recent performance and field
strength, including unknown finishes, before adding more agent-generated inputs.
Keep the existing model as the reference and use the same chronological protocol
for incremental comparisons. Odds collection remains paused.

## Reproduction

Use a fresh output directory:

```bash
OPENBLAS_NUM_THREADS=1 /app/more_studies/forecast-cal-private/.venv/bin/python \
  scripts/run_feature_ablations.py --out runs/feature_ablations_NEW
```

Artifacts include protocol/source snapshots, per-fold models and settings,
walk-forward scores, timestamped candidate selection, outcome-free development
features, all predictions, group-removal effects, uncertainty intervals, exact
reference reproduction, and established-scorer cross-check.
