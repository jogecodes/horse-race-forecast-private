> Website withdrawn at user request. All routes return HTTP 410. Do not publish or recreate it without a new explicit instruction. Research evaluation results below remain local and valid.

# Corrected evaluation and Turf showcase — November 12, 2026

The first website release lives in `website/dist/`. Its derived research dataset
comes from the new CPU-only release `runs/research_release_20261112`. Earlier
experiment outputs and benchmark datasets are preserved.

## Correction implemented

`horse_racing/research_release.py` computes deterministic declaration-form
features for every race, regardless of the saved extraction outcome. Article
features are optional: accepted saved outputs contribute their five semantic
columns; failed extraction means unavailable article evidence. Existing
preview-known and trouble-known columns encode availability. Failure statuses
remain in the audit and are not predictor variables. Rejected replies remain
rejected and are never repaired.

Both feature arms train on the same 20 January races and evaluate all 28 February
races. Their training/evaluation IDs are saved in `models.json`. Regularization
and optimizer choices stay fixed at ridge 1.0 and 1,000 Adam steps. Frozen
baseline predictions remain offsets. No new GPU inference was run.

The release was developed after inspecting the January–February results. This
is a corrected development evaluation, not a new blind test. March–June
validation/test races remain unscored by this release.

| February forecast | Races | Brier | Log loss |
|---|---:|---:|---:|
| Frozen baseline | 28 | 0.8148060984 | 1.8551627894 |
| Baseline + deterministic form | 28 | 0.8146028981 | 1.8445552143 |
| Form + optional agent evidence | 28 | 0.8146028898 | 1.8445551932 |

All accepted semantic columns are zero. The two feature models are effectively
identical: maximum probability difference 8.42e-8 arises from numerical fitting
with extra constant columns. The tiny score difference is not article value.
This resolves the misleading earlier comparison that trained on 20 versus 16
January races. The prior session's same-16-race diagnostic likewise reproduced
the old agent fit using deterministic form alone.

## Uncertainty and reliability

The new paired intervals resample whole meetings 4,000 times with seed 20261112,
keeping all races within a sampled meeting and weighting races equally. February
contains only six meeting clusters. Intervals are exploratory percentile
intervals for these fixed forecasts, excluding uncertainty from fitting models.

Deterministic-form minus baseline Brier difference: -0.0002032002, 95% interval
[-0.0087518377, 0.0061206614]. Log-loss difference: -0.0106075750, interval
[-0.0412942496, 0.0153625959]. Both include zero. No clear improvement established.

Fixed ten-bin pooled-runner reliability diagnostics cover 214 February runners.
Descriptive ECE is 0.0266278520 for baseline and 0.0182336623 for form. These
small-sample descriptions do not certify calibration or give per-horse
probability intervals. The baseline's 2025 temperature scaling is unchanged;
new feature arms have no separate fitted calibration.

On 17 February races with complete reported-price proxies, form Brier is
0.8275699978 versus proxy 0.7994988332. Paired difference +0.0280711646 favours
the proxy on this cohort. Saved report includes paired intervals and log loss.
Verified closing coverage and certified historical T-60 coverage remain zero.

## Extraction audit

48 saved attempts: 33 accepted, 15 rejected. Among 251 accepted runner vectors,
zero had nonzero article features. Twelve races had reviewed evidence (22
admitted items), so review admission alone did not produce usable extraction.
Eight failures lacked exact admitted-source quotations; six disagreed with
literal form; one quotation did not explicitly name the horse.

Next model work should audit those traces and build a small manually checked
article-extraction set. The website identifies this as the next experiment.
The independent article-only inference adapter is still future work; this
release consumes existing accepted outputs and fixes evaluation coverage.

## Site implementation and validation

Turf is a dependency-free static research site with a local racetrack SVG,
interactive score metrics/cohorts, all 28 February races, three model selectors,
optional result reveal, market proxy markers, ten-bin calibration diagnostics,
methodology, correction/audit notes, and three downloadable artifacts.

The source is the dedicated Git checkout `website/`; `.openai/hosting.json`
stores Site identity. Reuse that ID for updates. Do not commit raw databases,
article text, private traces, handover details or credentials into the site.
Only explicitly exported research facts, derived forecasts and source links
are served. The site is initially owner-private, as required by the Sites
workflow; widening access is a separate audience decision.

Validation: 169 repository tests passed, one optional shared integration skip.
22 targeted statistical/extraction/release tests also passed in the existing
research interpreter. JavaScript syntax passed. Installed-browser checks covered
all 28 races × three model views, winner reveal, both score metrics, 17-race
market comparison, all calibration models, all three downloads, and widths
1440/768/390/320. No horizontal overflow, browser exceptions or HTTP errors.
Desktop and mobile screenshots were inspected. No packages were installed.

Regenerate with the existing research interpreter:

```
OPENBLAS_NUM_THREADS=1 /app/more_studies/forecast-cal-private/.venv/bin/python \
  scripts/build_research_release.py --out runs/research_release_NEW
```

The exporter refuses to overwrite an existing release. It records input and code
SHA-256 receipts and writes new website data exports. Publishing uses the Sites
source helper to push the exact source and package the static directory. See
`_agent_state/website_release_20261112.json` for verified hosting identifiers and
the current URL. No ongoing background model job was created for this release.
