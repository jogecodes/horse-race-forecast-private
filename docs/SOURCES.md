# Spanish racing sources checked on 5 November 2026

| Source | Evidence and use |
|---|---|
| [Jockey Club Español](https://jockey-club.es/) | Official regulator. Public meeting pages include declaration stages and results/stewards' reports. Implemented source. |
| [25 October meeting](https://jockey-club.es/datos-de-jornada/?date=20261025&id=1) | La Zarzuela, six races; declarations and official results imported. |
| [1 November meeting](https://jockey-club.es/datos-de-jornada/?date=20261101&id=1) | La Zarzuela, six races; declarations and official results imported. |
| [Masdehipódromos](https://www.masdehipodromos.com/articulo.cfm?idarticulo=14430&idhipodromo=180) | Its own help article describes programmes, results and horse histories, including video links. A plausible site the user remembers. Historical HTML importer implemented; public seasonal index links drive the backfill. |
| [Gaceta Hipódromo](https://www.gacetahipodromo.com/mapa-web) | Its site map advertises Spanish results since the 2005 reopening of La Zarzuela and horse, jockey, trainer, stable and breeder records; much of that content requires registration. Candidate only; no account access. |

Direct urllib access to the official page returned HTTP 403 in this environment. The seed therefore uses the browsing tool's rendered page extracts, not a hidden endpoint or a bypass. Original tool responses and normalized numbered excerpts are preserved locally. The original JCE seed used no paid services, login attempts or bulk crawl. The subsequent public historical backfill is described below. A source being publicly readable is not an open-data licence; no bulk redistribution permission was established. The later Masdehipódromos backfill uses its directly accessible public HTML, collected sequentially with caching; no authentication or access-control bypass is used.

The public Masdehipódromos archive provides a working collection path and stable horse/connection IDs. Its seasonal indexes are not a guarantee of complete national coverage; missing and invalid pages are reported explicitly. Collection instructions are in `HISTORICAL_BACKFILL.md`. A current horse profile can contain its entire later career: it must never be treated as a historical profile merely because the target race is old. Capture future declarations and profile/news snapshots prospectively to obtain reliable availability timestamps.

## TodoTurf benchmark audit

The [TodoTurf results filter](https://www.todoturf.net/resultados.php), submitted with year 2026 and Spain, exposes 180 H1 races across 36 meetings. The benchmark collector preserves that index, meeting pages and linked race-result pages under `data/raw/todoturf_h1_2026/`. This source is used for cross-checking the H1 benchmark, not silently merged into the master historical database. See [BENCHMARK_H1_2026.md](BENCHMARK_H1_2026.md) for the measured selection, missing primary meetings, and temporal limitations.

## Betting-price collection

[PMU's public historical programme JSON](https://online.turfinfo.api.pmu.fr/rest/client/1/programme/16042026) and its [runner quote response](https://online.turfinfo.api.pmu.fr/rest/client/1/programme/16042026/R2/C1/participants) supply the separate price dataset. Matching requires venue, distance and an exact normalized starter set. Actual-off timing remains unverified; see [ODDS.md](ODDS.md) for coverage, field semantics and the distinction between quotes and result dividends.

[Betfair's official historical-data guide](https://betfair-datascientists.github.io/data/usingHistoricDataSite/) describes account-based downloads. It is a candidate source only: no account/export was accessed and Spanish coverage is not established.

## Recovered declarations and actual starts

The [declaration benchmark v2](RECOVERED_BENCHMARK_H1_2026.md) uses 33 official PDFs from La Zarzuela, Gran Hipódromo de Andalucía, JCE-linked San Sebastián documents and the Vila-seca municipal organizer. It distinguishes consistent publisher dates from independently archived availability.

San Sebastián's official photo-finish PDFs contain an explicit actual-start clock, enabling the [odds timing comparison](ODDS.md#actual-start-recovery-updated-coverage). Source PDFs, full arrival identity checks and quote/start joins are preserved locally.
