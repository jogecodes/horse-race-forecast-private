# H1 2026 benchmark rebuilt from pre-race declarations

The new frozen bundle is `benchmarks/h1_2026_v2/`. It contains **155 races and 1,404 declared runner records**, built directly from 33 official declaration PDFs. It retains **54 additional declared horses absent from the old result-derived fields**. The original 161-race bundle and master database remain unchanged.

| Split | Races |
| --- | ---: |
| Development, January–February | 48 |
| Validation, March–April | 52 |
| Test, May–June | 55 |

Venues: La Zarzuela 98, Dos Hermanas 40, Vila-seca 3, San Sebastián 14. This is a documented subset of v1; its national-coverage and original population-selection limitations remain.

## What changed

Race inputs now come from actual declarations: horse, saddlecloth number, age, declared weight, draw, jockey, trainer, stable and the literal printed prior-form string. They do not use the result-page roster or reconstructed career aggregates. Parsing does not consult winner labels or use result horse names to discover PDF rows. The mapping to existing race identities subsequently requires a unique field match and matching distance/date/venue. Rendering normalization handles spaces, accents and apostrophe variants, preserves country codes and rejects ambiguous identities.

Every declared horse remains in the forecast distribution. If a horse is absent from v1's result field, that fact stays in supervisor records; it is not sent to the predictor. Its target win mass is zero because the identified winner is another horse, without inferring why it was absent. There is no post-hoc removal of horses or probability renormalization. Already printed annotations remain in their original source documents; ambiguous parsing blocks inclusion.

The six remaining exclusions are explicit in `supervisor/exclusions.jsonl`: five races from San Sebastián on 22 April lack a recovered declaration PDF, and one La Zarzuela race on 14 June has `LIBERTY BLEU (FB)` in the declaration versus `LIBERTY BLEU (FR)` in the result sources. No unproven country-code correction was applied. The JCE April-22 document page is discoverable, but its access verification prevented recovery through the available route. Other public official sources were used wherever available.

## Evidence strength

These are **publisher-documented pre-race inputs**, a stronger reconstruction than a result-derived roster. PDF creation/modification dates, and HTTP Last-Modified where supplied, consistently precede the forecast cutoff. URLs, raw bytes, hashes, headers, actual retrieval times and parsed text are preserved under `data/raw/h1_recovery/` and in the recovery manifests.

Publisher dates remain publisher claims. They do not prove that today's exact bytes were publicly accessible at that historical deadline. This bundle is therefore not labeled a strict independently archived backtest. The engine requires the explicit `publisher-documented` track to use this assumption; the strict track has not been relaxed.

`data/h1_archive_checks.json` records the archive checks. There is no independently verified pre-cutoff capture in this pass. Wayback rate-limited part of the work; the collector now stops fresh requests after a rate limit and can still inspect cached receipts. Deferred checks are distinct from completed searches with no capture. Three targeted Common Crawl checks are also recorded in `data/h1_commoncrawl_checks.json`; none supplied a usable capture. Archive failures are not evidence that a document was historically unavailable.

## Sources

- [La Zarzuela historical meeting page, 5 April](https://www.hipodromodelazarzuela.es/carreras/jornada/20260405), linking its actual declaration PDF and programme. Recovered 21 meetings / 42 documents, comprising 21 declarations and 21 programmes.
- [Gran Hipódromo de Andalucía](https://www.granhipodromodeandalucia.es/), whose public event archive links eight historical full declaration PDFs on Google Drive. The public event JSON and original links are retained.
- Official JCE document links for San Sebastián [16 April](https://jockey-club.es/jornada/1a-jornada-primavera26-ss/), [29 April](https://jockey-club.es/jornada/3a-jornada-primavera26-ss/) and [11 June](https://jockey-club.es/jornada/1a-jornada-verano26-ss/), with the PDFs fetched through their public download links. Browser-discovered seeds are explicit in `data/h1_document_seeds.json`.
- [Vila-seca municipal organizer](https://vila-seca.cat/es/actualidad-ayuntamiento/noticias-actualidad/tradicional-cos-de-sant-antoni-2026), linking the revised 8 February declaration after the January postponement. The revised PDF's own date is checked; the old January declaration is not silently relabeled.

## Use

```bash
source .venv/bin/activate
python scripts/run_forecasting_engine.py --bundle benchmarks/h1_2026_v2 \
  --track publisher-documented --split development --limit 2 --rounds 1 \
  --out runs/my-v2-development-run
python scripts/score_recovered_benchmark.py --bundle benchmarks/h1_2026_v2 \
  --predictions runs/my-v2-development-run/researched_predictions.jsonl \
  --split development --out /tmp/my-v2-scores.json
```

Use a new output directory for each run. The generic v1 scorer has a hard-coded report version; use the v2 scoring script or `horse_racing.recovered_benchmark.score` so the report identifies the correct population and track. Metrics and validation reuse the frozen scoring implementation. Uniform predictions cover all 155 cases, with separate split reports in `data/recovered_baselines/`. No v1 history baseline is silently reused with these different fields.

`runs/h1_v2_publisher_smoke/` records one development race with valid closed-book and researched forecasts, exact prompts, model digests and passing audit reports. No historical research passage was admitted in that smoke. It verifies execution with declaration fields; it is not a full benchmark result or a demonstrated research advantage. Model memorization and judge limitations remain as previously documented.

The queryable, append-only database `data/declarations_h1_2026.sqlite` has `documents`, `races` and `entries`, containing only declaration data and timing claims, with no outcome table. It is a research database spanning multiple deadlines; do not mount the entire database as a single race's predictor input. Use the exported per-race packet.

To reproduce collection and build another version:

```bash
python scripts/recover_h1_documents.py
python scripts/recover_gha_declarations.py
python scripts/recover_seed_documents.py
python scripts/check_historical_archives.py
python scripts/build_recovered_benchmark.py --out benchmarks/h1_2026_v2_rebuild
python scripts/export_recovered_declarations.py
```

Cached error receipts are retained. Archive reruns respect cached rate limits rather than automatically retrying them; a later collection pass should use a new cache directory after the provider cooldown. No accounts, subscriptions, contacts or purchases were used.
