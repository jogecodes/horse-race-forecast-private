# Race-level statistical experiments, November 11

Completed run: `runs/statistical_baselines_20261111/`. CPU only; no new services,
model downloads, network research, or shared-engine modifications. This establishes
the baseline against which future research-only API features can be compared.
No LLM evidence-to-feature experiment has been run yet.

## Protocol

Fit on 799 races from 2022–2024. Select L2 regularization from 0.01, 0.1 and 1 on
343 January–September 2025 races, then refit on those combined 1,142 races. Select
temperature from 0.5, 0.75, 1, 1.5, 2 and 3 on the separate 89 October–December
2025 races. Selected regularization: 0.1; temperature: 0.75. Selection minimizes
mean race log loss. No 2026 outcome determines these settings.

Evaluate all 48 January–February 2026 development races, retaining all 368
declared runners, including later nonstarters. Pre-2026 histories match 318 runners;
50 have no matched history and retain explicit missing-history features.

Six features: log smoothed win rate, log recorded appearances, recent mean finish
strength, distance-weighted smoothed win rate, capped log days since last recorded
appearance, and missing-history indicator. Unknown/nonfinishing positions have
fixed neutral strength 0.5, an explicit baseline assumption rather than an inferred
last-place finish. Historical appearances may include nonstarters/status codes.

Historical training features use strictly earlier calendar days, withholding all
other same-day results. Evaluation histories freeze at the end of 2025. No target
result weights, draw, going, odds, post-race text or 2026 results enter features.
The linear race model uses race-level cross entropy, L2 regularization and
training-only standardization. Softmax is its declared statistical link, not a
repair of malformed LLM outputs. Temperature scaling does not itself prove calibration.

## Results

| Variant | Race Brier | Log loss | Brier skill vs uniform |
|---|---:|---:|---:|
| Equal chance | 0.858198 | 1.996261 | 0% |
| Smoothed history | 0.835218 | 1.906383 | 2.68% |
| Learned race model | 0.826025 | 1.880716 | 3.75% |
| Learned model + temperature scaling | 0.823292 | 1.870464 | 4.07% |

Lower is better. These are multiclass Brier scores summed over runners, averaged
over 48 races. Neither the metric scaling nor population matches the old pooled
binary experiment, so their raw values are not directly comparable.

The 48 races form ten meeting clusters. For the temperature-scaled model, paired
Brier difference versus uniform is -0.034906, descriptive 95% meeting-cluster
bootstrap interval [-0.088046, 0.001722], including zero. Log-loss difference is
-0.125796, interval [-0.256709, -0.025228]. Bootstrap: 2,000 resamples, seed 2026.
These are exposed development results, not validated market edge. The field
`summary.independent_development_races` means unique races, not statistical
independence; `analysis.json` reports the actual meeting clusters.

## Verification and limitations

All 192 distributions preserve exact runner sets and sum to one. The established
benchmark scorer independently reproduces the temperature-scaled model's scores,
48/48 coverage and zero zero-probability winners. Input/code hashes were unchanged
during the run and audit. No validation/test packets are used or scored.

Default tests: 140 passed, one optional shared-engine module skipped. The sibling
interpreter passes seven new statistical checks and all five shared integration
checks. Tests cover future/same-day exclusion, missing-history runners, frozen
history boundaries, held-out rejection, learning a known signal and invalid outputs.

Historical pages were collected retrospectively; training fields are reconstructed
from results. Declarations retain publisher-documented availability assumptions.
This is the existing day-before benchmark, **not** a historical T-60 experiment.
Scheduled-start-minus-60-minute production remains the agreed target and needs
timestamped snapshots. There is no odds comparison or profitability claim.

## Reproduction

Use a new output directory:

```bash
OPENBLAS_NUM_THREADS=1 /app/more_studies/forecast-cal-private/.venv/bin/python \
  scripts/run_statistical_baselines.py --out runs/statistical_baselines_NEW
/app/more_studies/forecast-cal-private/.venv/bin/python \
  scripts/analyze_statistical_baselines.py --out runs/statistical_baselines_NEW
```

Artifacts include exact source snapshots, input hashes, selected model/scaler,
selection/calibration comparisons, outcome-free features, predictions, per-race
scores, uncertainty analysis and existing-scorer check. NumPy was already installed.

Next: retain this baseline, define a small source-grounded extraction schema and
validate the shared research-only API's evidence-to-feature mapping on development
cases. Do not claim live T-60 validity or rerun held-out evaluations from these results.
