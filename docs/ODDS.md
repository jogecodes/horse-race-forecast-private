# Historical betting prices

**Updated:** actual-start recovery now identifies 32 nominally last-minute quotes across three races. See [the recovery section below](#actual-start-recovery-updated-coverage); the initial collection figures are retained for provenance.

The collected dataset is `data/odds_h1_2026.sqlite`, with a readable export at `data/odds_h1_2026.csv` and coverage/provenance report at `data/odds_h1_2026_report.json`. It joins the frozen benchmark using `race_id` and `runner_id`. The original racing database and benchmark hashes are unchanged.

| Source field | Observations | Races | Timing established |
| --- | ---: | ---: | --- |
| PMU `dernierRapportReference` | 118 | 14 | Provider quote timestamp before scheduled start |
| PMU `dernierRapportDirect` | 118 | 14 | Provider quote timestamp at/after scheduled start |
| Masdehipódromos result-table `DG` | 1,379 | 158 | Post-result field; no quote timestamp |
| Verified quote in last 60 seconds before actual off | 0 | 0 | Not established |

There are 161 benchmark races. These observations provide partial market data, **not a complete closing-odds series**. PMU prices are probable win returns from its `SIMPLE_GAGNANT` market, not guaranteed fixed bookmaker odds or exchange traded prices. The `DG` field's exact market/timing semantics are not independently verified, so it is retained separately and never promoted to pre-race odds.

## Acquisition and identity

```bash
source .venv/bin/activate
python scripts/collect_benchmark_odds.py
```

The collector downloads PMU daily programmes for benchmark dates, follows Spanish meetings and maps races using venue, distance and an exact normalized starter-name set. Ambiguous matches fail; unmatched races are recorded. It preserves raw JSON and URL/observation-time/SHA-256 receipts under `data/raw/pmu_h1_2026/`. Replaying the cache is idempotent. Quotes are append-only in the separate database; they do not alter the frozen master database.

Primary source example: [PMU participants for San Sebastián, 16 April 2026, R2C1](https://online.turfinfo.api.pmu.fr/rest/client/1/programme/16042026/R2/C1/participants). Each quoted runner includes `rapport`, `dateRapport` in epoch milliseconds and `typePari`; the [meeting programme](https://online.turfinfo.api.pmu.fr/rest/client/1/programme/16042026) supplies the scheduled `heureDepart`.

For ECLAIRLANE in that race, the stored reference return is 6.2 at 19 minutes 55 seconds before the scheduled start; the latest direct return is 5.7 at 72 seconds after the scheduled start. A delayed actual start could explain that timing, but the retrieved source does not establish the actual off. Neither quote is certified as the last pre-off price. Provider timestamps retrieved retrospectively also do not certify historical publication/availability of every response field.

Every observation includes its raw value, decimal value where parseable, quote time, scheduled start, actual start (currently null), collection time, original URL, source hash, market, timing class and proof basis. Missing values remain missing. SQL example:

```sql
SELECT race_id,runner_id,decimal_value,quote_at,scheduled_start_at,timing_class
FROM observations
WHERE source='pmu' AND quote_kind='dernierRapportReference';
```

## What would establish “right before the race”

A complete closing benchmark needs timestamped preplay market ticks, verified actual-start or market-suspension records, a consistent market definition and exact runner mappings. A provider export or independently verifiable archived feed could supply these. The current collector does not have those inputs and does not invent them from result dividends or scheduled times.

[Betfair's historical-data guide](https://betfair-datascientists.github.io/data/usingHistoricDataSite/) describes historical downloads and their access process. No account, purchase or export was used here; Spanish race coverage has not been established, so it is a possible additional source rather than a promised solution.

The H1 forecast deadline is the previous evening. Even genuine same-day pre-off prices arrive **after that deadline**. Keep them as a later-information market comparator, outside agent inputs. Adding a market baseline should use a separately declared horizon, exact market semantics and complete quote coverage; this release does not silently normalize these heterogeneous fields into a betting baseline.

## Actual-start recovery: updated coverage

The original odds database/report above describe the initial collection and remain intact. The newer `data/odds_actual_start_comparison.json`, `data/odds_with_actual_starts.sqlite` and `data/odds_preoff_last60s.csv` add actual-start evidence.

Official San Sebastián photo-finish PDFs contain an explicit **Hora de la Salida** clock. Their text gives the start to hundredths of a second. The collector follows the official result page's photo link, matches its full arrival horse set to a PMU market, checks the date and converts the printed local start using Europe/Madrid timezone rules. It preserves source PDFs, hashes, headers, text and receipt times. This recovered actual starts for **all 14 PMU-covered benchmark races**.

| PMU quotes compared against actual start | Observations | Races with a last-minute quote |
| --- | ---: | ---: |
| Timestamped within 60 seconds before actual start | 32 | 3 |
| Earlier than 60 seconds before actual start | 118 | — |
| Timestamped at or after actual start | 86 | — |

All 32 last-minute quotes are from 29 April. The three complete recorded-starter vectors have timestamps **0.43, 1.86 and 2.03 seconds before the corresponding official start clock**. They are the latest stored direct probable-return quotes, with explicit start evidence. Independent synchronization between PMU and the photo-finish clocks has not been measured; hundredth-second printing precision does not establish clock accuracy or public dissemination latency. These data establish nominal timestamp relationships, not a guarantee that no later price existed or that the quote reached a user before the start.

[Official example result page](https://www.hipodromoa.com/temporada/reunion/16-04/_IqQzNPbID9iDeySwjJMhudBPsbZjR25yK1Du_LQTM0ESAXrCnFJdqXRgxTsqDErw0FpmgXNKbyk) links its [photo-finish PDF](https://www.hipodromoa.com/files/303-23707-carr_foto_finish/1%20PREMIO%20ANDATZA%20TABERNA%20-%201400%20M.pdf). That PDF reports an actual start at 11:06:02.59 local time. This resolves the earlier ECLAIRLANE example: its 11:06:12 direct quote is nominally **9.41 seconds after actual start**, so it is excluded from the pre-off subset. Its earlier reference quote stays separately labeled.

```bash
python scripts/recover_actual_starts.py
python scripts/export_verified_odds.py
```

The comparison SQLite file has append-only `start_evidence` and `comparisons` tables. It links original observation IDs to actual-start proof; it does not update original odds rows. The CSV `data/odds_actual_start_comparison.csv` includes all 236 quote comparisons, while `data/odds_preoff_last60s.csv` contains only the 32 nominally pre-off observations.

A normalized inverse-price market comparator is written to `data/market_comparators/`. It covers three complete recorded-starter fields in v1 and two complete declared fields in v2. One v2 field contains an additional declared horse without a matching price; that race is excluded rather than imputing a price or retrospectively removing the horse. Reports identify the small validation-only subset and full-split coverage. These same-day prices remain forbidden as inputs for the previous-evening forecasting task.
