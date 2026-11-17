# T-60 market disagreement detector

The user subsequently requested whole-dataset **historical T-60** prices rather
than final/closing odds. See [coverage audit and archive lead](HISTORICAL_T60_COVERAGE_20261111.md).

Update: a standard rendered-browser pilot subsequently captured a complete UK
market from Sportium without login. See [capture report](PUBLIC_CAPTURE_PILOT_20261111.md).
Spanish T-60 coverage and a live collector remain unverified/unconnected. Earlier
ordinary-HTTP findings below are retained as the investigation history.

The user retained a strict scheduled-start-minus-60-minute decision time. This
implementation prepares receipt-backed fixed-odds inputs and outcome-blind flags.
It does not fetch bookmaker prices or place bets. No live collector is scheduled.

## Provider investigation

Ordinary public requests on November 11:

- bet365.es: HTTP 403. No anti-bot workaround attempted.
- Sportium home/racing pages: HTTP 200, but the ordinary responses did not expose
  usable runner-level quotes. Fixed-odds coverage of our Spanish races at T-60
  remains unverified. A marketing page is not a verified collection interface.
- Betfair documents an account/application-key API and delayed testing data.
  It is an exchange, not the same product as bookmaker fixed odds. No account,
  key, activation or payment was made; Spanish-race coverage is unverified.

Public references:

- https://www.sportium.es/apuestas/sports/horse_racing
- https://www.bet365.es/
- https://betfair-developer-docs.atlassian.net/wiki/spaces/1smk3cen4v3lu3yomq5qye0ni/pages/2687105/Application+Keys

Probe bodies are in `data/provider_probe_20261111/`; their hashes and conclusions
are in `runs/market_watch_20261111/provider_review.json`. No automatic provider
has been selected. The user was asked whether an existing feed/export is available.

## Implemented boundary

`horse_racing/market_watch.py` accepts a complete, single-provider fixed-price win
market and an independently saved model probability distribution. It requires:

- Race, provider, market and verified runner mapping; matching complete fields.
- Scheduled start, schedule source and when that schedule was known.
- Original quote time, capture time, raw-response hash and capture receipt ID.
- Open pre-race market state, explicit fixed odds, finite decimal prices above 1.
- Model version, training-data boundary, creation time and matching T-60 cutoff.

Quote, capture and prediction must be no later than T-60. Quotes older than five
minutes at the cutoff are rejected by the initial staleness policy. Late, stale,
pool/SP, suspended, in-play and incomplete inputs produce no candidates. Missing
runner prices are not filled in and model probabilities are never repaired or
renormalized to fit a different field. Updated withdrawal information requires a
separately valid field/prediction, not automatic deletion of a horse.

Within a complete market, proportional de-vig computes
`(1 / decimal_odds) / sum(1 / decimal_odds)`. This is an assumption, not a proven
market probability. Each row records this estimate, raw break-even `1 / odds`,
model probability, difference and `model_probability * odds - 1`.

Initial research-watchlist defaults require both a three-percentage-point gap
and at least 5% model-implied return **before costs/deductions**. These thresholds
are development defaults, not selected or validated on betting outcomes. They
prevent a difference from the de-vigged market alone being mistaken for positive
value at the actual price. There is no calibrated probability interval, execution
guarantee, stake sizing, settlement/ROI calculator or profitability claim.

Every decision uses a new directory; existing decisions cannot be overwritten.
Input/report hashes and detector source hash are recorded. Imported receipt IDs
and timestamps still require trustworthy original evidence: this code does not
authenticate an arbitrary feed. The local export capture mode records the actual
current ingestion time and cannot backdate a file using its supplied timestamp.
It captures an existing export, not an authenticated HTTP provider response.

## Commands and verification

Capture an already available provider-adapter export now:

```bash
.venv/bin/python scripts/market_watch.py --capture-export \
  --snapshot /path/to/provider-export.json --out runs/capture_NEW
```

Evaluate a receipt-backed snapshot against a saved prediction:

```bash
.venv/bin/python scripts/market_watch.py \
  --snapshot /path/to/snapshot.json --prediction /path/to/prediction.json \
  --out runs/market_check_NEW
```

The contracts and a fully invented example are in
`runs/market_watch_20261111/synthetic_demo/`. That example flags one invented
selection; it is not an actual discovered opportunity or historical replay.

Ten new tests cover timing, staleness, price type, field identity, margin effects,
backdating prevention and non-overwriting decisions. Full default suite:
150 passed, one optional shared-engine module skipped.

## Historical coverage

`scripts/audit_t60_odds.py` reads the existing odds DB without outcomes. Audit:
1,379 post-result rows excluded; 236 PMU pool estimates across 14 races; zero
quote timestamps at/before T-60. The earliest saved quote is about 34.9 minutes
before scheduled start. No historical fixed-odds T-60 replay is possible from
those records, and late prices were not substituted. No validation/test outcomes
were inspected or scored for this work.

Next required input: an accessible feed or export covering the same Spanish
races with fixed win prices before T-60. Validate price meaning, access, runner
mapping and actual capture receipts before scheduling prospective collection.

## Additional provider check

The user confirms they have no API/feed/export. Codere was also checked with ordinary requests: home returned HTTP 403; sportsbook/robots hosts returned connection errors from this environment. This does not establish that the operator has no data or that access is impossible elsewhere. Receipts are in `data/provider_probe_20261111/additional_access_receipts.json`. No account was created and no paid service was enabled. A small manually captured full-race T-60 fixed-price pilot remains an option if a public operator page is accessible in the user browser; none has been performed.
