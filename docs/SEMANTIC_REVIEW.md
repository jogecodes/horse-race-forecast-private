# Exploratory semantic leakage review

The `exploratory` research policy lets undated article passages reach semantic assessment. It preserves missing publication/availability times as `null`, and never substitutes the collection time or forecast cutoff. Existing `strict` and `publisher-dated` behavior remains available; the default is unchanged.

```bash
.venv/bin/python scripts/run_forecasting_engine.py \
  --out runs/NEW_EXPLORATORY_RUN --split development --limit 3 \
  --research-policy exploratory --search-backend stdio \
  --ollama-base http://127.0.0.1:11437
```

Use an already running local endpoint and an active host-search bridge. This command does not start a model server. The strict track and prospective declaration runner cannot use exploratory research.

Code still rejects inconsistent receipts and explicit source publication/update times after the cutoff. In exploratory mode, date/tense patterns inside article text become clues for the judges rather than lexical hard vetoes. The temporal judge reasons about when events occurred; the outcome judge reasons about the identity of the target race and later realized facts; the relevance judge assesses the requested entity or declared conditions. Earlier wins and season totals can be useful when their temporal context is anchored. Unanchored “today”, “this season”, career totals and ambiguous result narratives should produce uncertainty.

Each role returns `allow`, `drop`, or `uncertain`, a reason, and up to three exact supporting quotations from the supplied passage. Allow/drop require at least one quotation. Code rejects invented quotations and malformed responses. Only three allows admit evidence; uncertainty/errors remain excluded. Judge prose and labels remain outside selector/forecaster inputs. The forecaster receives an explicit exploratory dating notice, and extractive evidence retains its unknown availability time. The audit supports these null times only through the recorded exploratory policy and verifies exact supporting quotes.

This is a content-leakage assessment. Semantic approval does not certify historical publication or edit history. All three roles currently share the installed local `llama3.1:8b` weights.

## Reviewed development diagnostic

`data/semantic_leakage_review_v1/dataset.json` freezes 24 scenarios from six genuine publisher snapshots. It includes useful earlier results and previews, target-result disclosures, known later sources, ambiguous time contexts and unrelated controls. Each scenario preserves exact paragraph indices, excerpt hashes, a frozen development task, and an assistant-written label and rationale assigned before local-model evaluation. There is no independent human adjudication. Repeated excerpts are paired context/date-metadata probes, not independent observations.

`publisher` cases retain source date claims. `natural` cases genuinely lack a supported date in the current parser. `withheld` cases deliberately remove date claims as an evaluation ablation; this does not assert that the original article lacked dates. Original URLs and titles remain visible and can themselves supply temporal clues. The full original dates and snapshots remain in the supervisor review record.

```bash
.venv/bin/python scripts/evaluate_semantic_review.py \
  --out runs/NEW_SEMANTIC_REVIEW \
  --ollama-base http://127.0.0.1:11437
```

The evaluator verifies snapshot/excerpt hashes and development-only tasks, snapshots its code and data, runs both policies, and saves every decision, exact model request/response, timings and errors. Labels/rationales and confidential winners are not supplied to the judges. It reports three-way confusion, leakage admissions, useful-evidence rejections/uncertainty, ambiguous admissions, and role errors. It produces no forecasts and reads no outcome database.

The first run is `runs/semantic_leakage_review_v1_20261105`. Its `report.json`, `results.jsonl` and `audit_report.json` are the canonical measurements; they include disagreements rather than silently relabeling or excluding them. Freeze any subsequent prompt revision as a new experiment and use independently reviewed new passages before claiming improvement.

## First results

See [SEMANTIC_REVIEW_RESULTS_20261105.md](SEMANTIC_REVIEW_RESULTS_20261105.md). The exploratory panel admitted two of eight leakage scenarios and only three of eight useful scenarios; it remains experimental. There were 17 invalid supporting-quote responses across 66 completed exploratory judge calls. The completed run retains its interruption/recovery history and all disagreements. To resume an interrupted evaluation, pass `--resume` with the exact original dataset, output, endpoint and policies; it refuses changed engine/input hashes and preserves incomplete-case ledgers.

## Event identity and sentence IDs

The next separately versioned experimental policy is described in [EVENT_GROUNDED_REVIEW.md](EVENT_GROUNDED_REVIEW.md). It preserves this baseline and adds per-sentence event/target/time assessment plus code-rendered citations. Its fresh comparison uses new source URLs and pre-annotated passages.
