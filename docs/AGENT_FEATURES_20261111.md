# Agent-extracted features and paired forecast evaluation

Current run: `runs/agent_features_20261111_v2`. The existing sibling `forecast_system`
research API is imported directly; no upstream engine code is changed or copied
into the study implementation. The run's source snapshots are audit receipts.

## Experiment

All 48 January–February development races are processed. January's 20 races fit
only the added feature weights; February's 28 races evaluate them. March–June
held-out races are untouched. This is a small development experiment, not final
out-of-sample certification or evidence of betting profitability.

Three arms:

1. Existing calibrated statistical baseline, frozen through 2025.
2. Baseline plus deterministic literal declaration-form features.
3. Baseline plus agent-parsed form and source-supported opinion/trouble features.

The new model is a conditional softmax with the frozen baseline log probability
as an offset. Features are standardized on January only. Ridge strength 1.0 and
1,000 Adam steps are fixed in advance. February is not used to tune the feature
weights or temperature. Reports refresh during execution without changing this
protocol. Baseline and deterministic comparisons on the agent's successful
February cases are included; extraction failure coverage must be read alongside
scores. Failures are not filled with invented features or repaired responses.

The agent extracts features, not probabilities. Literal printed codes retain
leading zeros. Zero and nonnumeric codes have unknown placing. No unverified
ordering of the printed form sequence is assumed. The six form features cover
known form, debutant declaration, reciprocal numeric placing, win fraction, code
count and unknown-code fraction. Five text features cover favourable/unfavourable
preview opinion, opinion availability, earlier trouble and trouble availability.
Unknown is distinct from a supported negative statement.

## Source and temporal boundaries

Workers receive development declarations and a bounded 29-paragraph corpus from
three existing preserved articles. They do not read labels, result tables, market
prices or evaluation reports. Shared research retrieves and reviews evidence;
the extractor sees reviewed sources and must supply exact quotations naming the
horse. Target preview claims must concern the target event date; trouble must
concern an earlier event. Literal form extraction must exactly match its source.
Schema validation and quote checks do not certify the truth or interpretation
of a publisher statement; saved outputs support manual inspection.

The November 2025 article supplies earlier-race context; January 11 and February
1 previews supply sparse target opinions. January's source date is supplemented
from its existing preserved raw HTML, which visibly states Friday, January 9,
2026. A conservative Madrid day-end bound is recorded with the cache hash.
No new network fetch is used to create that receipt.

These are publisher-dated retrospective reconstructions, captured in November
2026, with the existing day-before declaration cutoffs. They are not certified
archived T−60 observations. Model pretraining memory cannot be excluded; the
extractor is instructed to use supplied evidence only. The corpus is small and
does not constitute a validated general race-comment dataset.

## Two evaluations

**A — actual outcomes:** race-level multiclass Brier score is
`sum((p_i - y_i)^2)`, averaged equally across races. Lower is better. Log loss is
also reported. The outcome vector uses the frozen benchmark's winning shares,
including dead heats. Preserve the full declared field, including later
nonstarters, consistently with the benchmark.

**B — market comparison:** on identical races and runner sets, score both the
model and market probability vectors against the same outcomes. Report model
error, market error and model-minus-market error; negative differences favour
the model. Separately report squared model–market distance. Disagreement alone
does not establish which forecast was correct.

No independently verified exact closing quote set currently exists for this
cohort. `evaluation_inputs/verified_closing_markets.json` is explicitly empty,
and the verified closing report has zero coverage and null metrics.

A separate provisional report uses post-result DG fields, interpreted as decimal
gross return and converted by normalized inverse prices. This is a declared
assumption, not proof of their semantics or exact last available pre-off price.
Non-numeric values, values below one, suspected duplicated margin/time fields,
and any missing declared-runner price exclude the whole race. Do not drop runners
or fill their prices. Source URLs, capture hashes and missing quote timestamps
are saved. Price filters do not use the race winner. These proxies cannot support
T−60 trading or executable-return claims.

## Preliminary CPU control results

Before agent extraction, February's 28 races score:

| Arm | Brier | Log loss |
|---|---:|---:|
| Frozen baseline | 0.814806 | 1.855163 |
| Baseline + deterministic form | 0.814603 | 1.844555 |

The change is small; this is not a demonstrated material improvement. The earlier
48-race baseline remains 0.823292 Brier, a different evaluation cohort.

Thirty of the 48 development races have complete usable reported-price proxies;
17 are in February. On those 17 identical races, the baseline Brier is 0.827836,
the deterministic-form arm is 0.827570, and the price-proxy forecast is 0.799499.
The proxy is currently better on that subset. Do not compare these numbers to
the 28-race numbers as if their cohorts were identical. Agent results remain
pending until the extraction queue and evaluator finish.

## Execution and receipts

Use the existing `/app/more_studies/forecast-cal-private/.venv/bin/python`.
GPU 3 only, dedicated Ollama port 11440, installed `llama3.1:8b`, one sequential
worker. GPU 2 and existing model services are untouched. No downloads, paid APIs,
or calendar deadline. Per-case timeout is 900 seconds; preserve failed attempts.
Service ownership, singleton lock, code/input hashes and UUID checks guard the
run. A source-code change stops subsequent cases. The controller stops its own
model service at completion, then writes a final evaluation.

Prepare once with `scripts/run_agent_features.py --prepare --out RUN_DIR`.
Run `scripts/run_agent_features.py --out RUN_DIR`; `--smoke` limits execution to
the first case. A completed smoke case is reused by the full queue. Do not run
two controllers. Resume skips every recorded complete or failed attempt; an
interrupted directory without a result requires inspection. Do not overwrite it.

Read `status.json`, per-case `result.json`, `research.json`, `trace.jsonl`, and
`evaluation/summary.json`. The evaluator also saves model weights, full race
probabilities and market-price receipts. Rerun only the CPU evaluator with
`scripts/evaluate_agent_features.py --out RUN_DIR` to refresh reports.

Validation: final repository suite 165 passed, one optional shared-integration skip;
27 targeted tests passed using the existing
sibling environment, including shared-engine integration, statistical and
ablation regression tests. The sibling interpreter cannot collect the entire
repository suite because it lacks `pypdf`; the repository environment supplies
that dependency. No packages were installed.

The initial `runs/agent_features_20261111` smoke attempt failed: the agent wrote
invented commentary into `form_quote` and unsupported opinions with no article
evidence. Its validator rejected the whole race; no features or predictions were
accepted. All raw output is preserved. Version 2 restricts `form_quote` to supplied
literal values in the native output schema and restricts semantic features to
unknown when no reviewed article exists. This is a new recorded inference
protocol, not a repair or silent retry of the failed run. The initial run should
not be resumed with the revised source code.

Version 2's first real-model smoke case succeeded for all eight declared runners;
input drift was empty and its evaluator exited successfully. The full queue was
launched detached on November 11 at 14:29 UTC, controller PID 2562094. Its live
`status.json` is authoritative; do not treat these launch details as a claim that
the full experiment has finished.
