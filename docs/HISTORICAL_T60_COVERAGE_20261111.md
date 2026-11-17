# Whole-dataset historical T-60 coverage

The user explicitly clarified that "final quotas" means odds available at
scheduled start minus 60 minutes for the historical flagging experiment, not
closing odds. Post-result fields and closing prices must not replace that input.

Read-only inventory: `runs/historical_t60_inventory_20261111/race_coverage.csv`.
All 1,593 historical races are represented; currently stored verified T-60 market
coverage is 0/1,593. This describes our stored observations, not proof that an
external historical archive cannot cover some races. The master DB hash was
unchanged. No outcome scores, historical candidate flags or returns were computed.

Existing PMU snapshots are too late for T-60 and are pool estimates. Stored
post-result DG fields, including fields populated on 11,970 selected runner rows,
remain excluded. Full-race numeric post-result coverage does not establish
availability an hour before the race. The public Sportium browser capture proves
one current UK market can be observed; it does not recover past Spanish markets.

## Potential historical archive

Betfair's official historical service documents time-stamped Exchange data and
registered-customer download access. Its official data-science guide lists a free
BASIC tier sampled at one-minute intervals. The provider forum explains that
BASIC contains last-traded-price changes, not a full executable back/lay ladder.

- https://betfair-datascientists.github.io/modelling/dataSources/
- https://support.developer.betfair.com/hc/en-us/articles/360000402211-How-do-I-download-and-view-Betfair-Historical-Data
- https://historicdata.betfair.com/Betfair-Historical-Data-Feed-Specification.pdf
- https://forum.developer.betfair.com/forum/developer-program/historical-data/36504-horse-races-how-to-sort-horses-by-odds-in-a-simple-manner

A normal public browser visit confirmed the historical portal renders and lists
Horse Racing BASIC as free. Its HTML, text, screenshot and access receipt are in
the inventory run directory. No login, account creation, checkout, purchase or
download was performed. Exact coverage of our Spanish dates, venues and race
fields remains unverified. No user feed or API was available.

## Next acceptance checks

Before any dataset-wide acquisition, identify an exact Spanish race in the
archive and inspect one sample. Require source-native market/race and runner
mapping; a schedule known before the cutoff; and a quote observation at or before
T-60, with explicit age and missingness rules. For stream files, reconstruct state
only through messages at/before the cutoff; do not expose later settlement or
winner fields to signal generation. Later archive-download time is provenance,
not a substitute for the provider's historical event timestamps; archive trust
must be explicit and different from our own prospective captures.

BASIC last-traded prices can be an indicative disagreement benchmark where
coverage exists. They must not be relabeled as executable fixed bookmaker odds
or passed into the fixed-odds detector without a distinct market-type contract.
Profit simulation would require evidence of available prices, liquidity,
commission and settlement rules. One-minute snapshot frequency does not prove a
recent trade on every runner. Snapshot/update age and last-trade age differ.

Use only the supported subset if data is found, report exact exclusions and retain
unknowns. Do not promise coverage of all 1,593 races. Forward T-60 capture is the
alternative for races without a recoverable archive, not a historical backfill.
