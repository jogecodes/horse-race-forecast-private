# Database and ingestion

## Tables

| Table | Purpose |
|---|---|
| `sources` | Official and candidate providers, access and rights notes |
| `snapshots` | Immutable collected text, URL, observation time, hash, acquisition method; publication time is nullable and never trusted by the gate |
| `entities` | Horses, jockeys, trainers, stables/owners, breeders; provisional source-local identity |
| `meetings`, `races` | Stable meeting and race keys, local race date and timezone |
| `race_versions` | Declaration and result versions tied to their source snapshot |
| `entries` | Declared horse, jockey, trainer, stable, weight, draw and withdrawal marking |
| `results` | Separate official positions, original statuses, margins, connections and breeders |
| `quality_issues` | Differences between declarations and results, retained for review |
| `evidence` | Individual race-contextualized snippets with source locator; not automatically safe |
| `forecast_runs` | Target race, UTC cutoff, required judge identities, frozen policy version |
| `judge_votes` | Verdict, reason, raw response, model identity, exact prompt and its hash, timestamp |
| `gate_decisions` | Every admission check and its rejection reasons |
| `packet_exports` | Packet hashes and the exact admitted evidence IDs |
| `predictions` | Storage reserved for later probability forecasts; no forecast runner yet |

Schema version 3 is in `horse_racing/schema.sql`. Opening a v1 database applies a transactional migration that preserves its rows and source hashes while permitting null result saddlecloth numbers. The v3 migration removes the uniqueness assumption on displayed race order, because source errors can repeat that label for different races. New tables store provider identities and historical field details. After migration, source and audit tables are append-only, and new acquisitions produce new snapshots and versions. Replaying identical text with the same acquisition timestamp does not duplicate rows.

All timestamps accepted by the application require an explicit offset and are normalized to UTC. Meeting dates use `Europe/Madrid`. Seed start times were unavailable and remain unspecified: a forecast cutoff must precede the start of the target's local calendar day. A prior result cannot be used until the prior race's entire local day has ended. These conservative restrictions can be refined when verified scheduled/actual start times are collected.

## Inspect with SQL

Use any SQLite client, or Python's `sqlite3` module:

```sql
-- Stable race keys for future run configuration.
SELECT r.id, m.race_date, m.venue, r.race_number
FROM races r JOIN meetings m ON m.id = r.meeting_id
ORDER BY m.race_date, r.race_number;

-- Official labels (supervisor/scorer only).
SELECT r.id, e.name AS horse, z.position, z.status_raw
FROM results z
JOIN entities e ON e.id = z.horse_id
JOIN race_versions v ON v.id = z.race_version_id
JOIN races r ON r.id = v.race_id
ORDER BY r.id, z.position;

SELECT code, detail FROM quality_issues;
PRAGMA integrity_check;
PRAGMA foreign_key_check;
```

Multiple snapshots yield multiple versions. Do not aggregate all result versions as independent starts; choose a version under an explicit availability policy. Likewise, never calculate an entire-career win rate and reuse it at earlier cutoffs. Entity display names and race metadata in the master DB are not independently approved historical features.

The `Dist.` result column is retained as `margin_raw` with its original fractional/Spanish notation. No conversion to seconds or cumulative beaten lengths is assumed. `RET` has a null position; dead heats retain the raw status (`8 (EMP)` in the seed). No synthetic odds, pedigrees, start times, ages, weather or finishing times were inserted into structured fields. The raw header retains surface, going and time where provided; structured parsers for those fields are future work.

## Rebuild the delivered database

The delivered local `data/raw/seed_manifest.json` records the acquisition time and input files. `data/raw/jce_browser_extracts.json` preserves the original browsing responses. The numbered extracts cover all declarations/results for both meetings, with no gaps in the selected source regions. `prepare_browser_seed` in `horse_racing/ingest.py` reconstructs those inputs and reports conflicting overlaps.

```bash
python -m horse_racing --db /tmp/rebuilt-racing.sqlite seed
```

The raw files are ignored by Git, so copying only tracked code does not copy the corpus. Transfer `data/raw/` privately to replay this exact seed.

## Import another official meeting

Collect the public JCE meeting page through an authorized browser/collector and save its rendered, pipe-delimited text. The importer accepts plain text or the browsing tool's `L123:` line prefixes. It expects JCE's declaration and result headings and table column order; it does not parse HTML or PDFs and does not download pages itself.

```bash
python -m horse_racing import-jce \
  --file /path/to/meeting.txt \
  --date 2026-10-18 --venue-id 1 --venue 'La Zarzuela' \
  --observed-at '2026-11-05T11:00:00+01:00'
```

The example timestamp is illustrative: supply the **actual time the exact content was acquired**, never the race date or a claimed publication date. Metadata is supplied by a trusted collector/operator. The application does not attest arbitrary imported timestamps or verify an archive capture. The official URL is derived from the date and venue identifier; the collector must verify they describe the saved page.

Imports reject duplicate cloth numbers, malformed rows, empty tables and mismatched declaration/result cloth sets when both phases are present. Results-only or declaration-only pages are supported; full-field completeness cannot be established without a second source or expected count. A browser extract is not a byte-for-byte HTML snapshot, and completeness checks cannot attest the source's accuracy.

## Add agent research evidence

For a snippet collected now, from a registered provider:

```bash
python -m horse_racing add-evidence --source jce \
  --url 'https://jockey-club.es/actuaciones-2/' \
  --file /path/to/snippet.txt --kind context --locator 'horse profile, selected paragraph'
```

This records the local ingestion time, which is a conservative upper bound on availability, and stores exactly the supplied snippet. The trusted collector must preserve any broader page separately and accurately describe the locator. For a result snippet use `--kind result --race <race-id>`; a result without race context is rejected by the gate. Collector-supplied labels are not proof that content is safe: independent judges must assess its meaning in context.

## Historical source extensions (v2/v3)

`entity_identifiers` maps provider IDs to entities. `race_identifiers` maps result-page IDs to canonical races. `race_details` stores the source category, surface, going, time-of-day, prize and dividend strings per version. `result_details` retains source weight strings and components, dividends and the original time-or-margin field.

The `results.cloth` field may be null when absent from the provider. It is never populated from the result position or stall number. Provider status codes of 90 or above retain `status_raw` but have a null finishing position and a quality flag; their precise semantics have not been established. An impossible weight remains raw and its invalid numeric component remains null. Post-race DG/dividend fields are labels/context, never assumed to be pre-race market odds.

`latest_results` is a supervisor/scorer view selecting a single result version for each canonical race, preferring official JCE results, then the newest snapshot. Use this view to avoid double-counting starts across source versions. It is **not** an as-of feature query. `coverage` reports both all source rows and selected runner rows, plus annual/venue coverage and quality issue counts.

`races.race_number` retains the source-displayed order but is not a unique identity key. Historical pages sometimes reuse that order for distinct events with different annual race numbers. Stable provider page IDs identify historical races; annual numbers, displayed ordinals and distance are cross-checks when matching official versions; conflicting displayed ordinals produce a quality issue. Never group races by date/venue/order alone without checking this flag.
