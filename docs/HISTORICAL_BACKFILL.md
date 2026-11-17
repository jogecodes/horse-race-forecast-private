# Historical Spanish results backfill

The initial two official meetings were a parser seed. The expanded corpus follows the public [Masdehipódromos seasonal results indexes](https://www.masdehipodromos.com/articulo.cfm?idarticulo=14430&idhipodromo=180), including the linked prior seasons. Seventeen index pages exposed 1,598 distinct race-result URLs in the initial discovery. The completed import loaded **1,593 valid result pages**. Four linked pages return empty result templates, and one linked 1960 race is excluded by date. There are no missing downloads. The 12 original JCE races overlap these events and remain the preferred official versions, so the combined corpus still has **1,593 distinct races**, not 1,605.

## Reproduction

Use the study's `.venv`, or install the project with `python -m pip install -e '.[test]'` in another environment. From the project root:

```bash
python scripts/discover_mdh.py --cache data/raw/mdh --max-indexes 30
python scripts/download_mdh.py --cache data/raw/mdh --interval 0.5
python -m horse_racing import-mdh-cache --cache data/raw/mdh \
  --start-date 2022-01-01 --end-date 2026-11-05 \
  --report data/mdh_import_report.json
python -m horse_racing coverage --out data/coverage_summary.json
```

`--db` is a global option and goes before the subcommand. To rebuild a separate database with both sources, replay the JCE seed first, then the historical cache:

```bash
python -m horse_racing --db /tmp/rebuilt.sqlite seed
python -m horse_racing --db /tmp/rebuilt.sqlite import-mdh-cache
```

The discovery script follows only same-provider archive links with results labels and records unique public `jidPremio` links. It is bounded by the maximum number of indexes. The download script uses one HTTP request at a time, at least 0.5 seconds between request starts, and stops on authentication/forbidden/rate-limit responses. Cached files are not requested again. Transient failures are logged; rerunning retries only missing files. There is no exhaustive race-ID scan or account access.

Each downloaded page has immutable raw HTML and a sidecar with URL, actual observation time, HTTP status, content type, byte count and SHA-256. Parsing/import verifies that hash. The original bytes remain in the cache; the database snapshot body is decoded HTML with its own content hash. Replaying the same cache preserves its timestamps and does not duplicate rows.

## What is included

These are **post-race results**, with source horse, jockey, trainer and owner/stable IDs, positions/statuses, weight strings, stall/draw, margins or winner's time, DG/dividend strings, race conditions, distance, category, surface and going. Stable IDs connect a horse's appearances despite spelling/display-name changes. Provider-local IDs are not official registry identifiers; cross-provider horse identities are left distinct pending explicit reconciliation.

Historical result pages lack saddlecloth numbers in the imported layout. `results.cloth` therefore remains null. The `CS` field becomes draw; it is not a replacement saddlecloth. Result pages do not create declaration entries, and there is no invented pre-race field or start list. Source time-of-day strings are retained but are not yet verified enough to relax the conservative day-based forecast cutoff.

The source's weight column can contain a pair such as `59,5-58`. Both raw text and its two numeric components are retained. A missing second component remains missing, rather than assuming the first was carried. Invalid components, such as a five-kilogram carried weight, are not corrected by guesswork; they are null and flagged. Source numeric status codes such as 95 or 98, and positions exceeding the reported field size, are preserved with null position; their precise meaning remains unverified. They must not be treated as 95th/98th finishers or automatically classified as withdrawals.

There is no independent official cross-check for every historical result. Official and historical versions can share a canonical key when venue/date, annual number, displayed order and distance all match. Distinct provider race-page IDs remain separate even when the source repeats an annual number or displayed race-order number; both types of conflict are flagged. `latest_results` prefers official JCE results where available, then the latest result snapshot. This avoids double-counting source versions in the coverage report while preserving them all in the underlying tables.

## Coverage and omissions

`data/coverage_summary.json` contains measured canonical race counts, selected runner rows, all source result rows, date range, annual/venue breakdowns, stable horse-ID count, quality issues and integrity checks.

`data/mdh_import_report.json` lists every rejected or excluded page and every discovered ID without a downloaded page. An old 1960 race linked from a newer seasonal index is excluded by the requested date range. Some public result links return empty template pages; these are rejected rather than counted as races. Missing pages and index omissions mean this is a multi-season archive, not certified complete national coverage.

The original `data/seed_summary.json` continues to describe only the two-meeting JCE seed; it is not the expanded-corpus summary.

## Temporal limitation

Newly downloaded historical results are useful for labels, histories and testing the research system. Their historical event date does not establish historical document availability. Every new snapshot retains its actual collection time, so the gate rejects it at earlier forecast cutoffs. For a faithful historical researched forecast, obtain an independently verified pre-cutoff archived document; for prospective forecasts, collect histories and declarations now and freeze the evidence before the target race.

## Measured completed coverage

| Year | Distinct races | Selected runner-result rows |
|---|---:|---:|
| 2022 (from late November) | 43 | 305 |
| 2023 | 422 | 3,410 |
| 2024 | 334 | 2,757 |
| 2025 | 432 | 3,436 |
| 2026 (through 1 November) | 362 | 2,964 |
| **Total** | **1,593** | **12,872** |

Venues are La Zarzuela, San Sebastián/Lasarte, Dos Hermanas, Sanlúcar de Barrameda, Pineda, Vila-seca, Zahara de los Atunes and Loredo. Result rows include the provider's preserved withdrawal/disqualification/nonfinisher status records; they should not all be counted as completed starts. There are 1,609 distinct Masdehipódromos horse IDs, with JCE provisional identities kept separate.

The final audit checks the complete cache replay, all 1,595 database snapshot hashes, the unchanged original official snapshot provenance, agreement on all 12 overlapping official/provider winners, SQLite integrity and foreign keys. See `data/validation_summary.json`. Four empty pages are IDs 58093, 59842, 59910 and 59964; the excluded old race is ID 53637.
