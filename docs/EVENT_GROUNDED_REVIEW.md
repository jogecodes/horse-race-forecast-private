# Event identity and temporal grounding

`--research-policy event-grounded` is a separate experimental policy. It preserves the original `exploratory` policy and its failed November 5 baseline. The default remains `publisher-dated`; strict prospective declarations are unchanged.

The protocol version is `event-grounded-v1`, implemented in `horse_racing/engine/events.py`. A separate stateless local resolver reviews every code-generated sentence ID before the existing three judge roles assess the full passage. The resolver is another role using the same installed llama3.1:8b weights, not an independent trained model.

For each sentence, the resolver classifies the most leakage-sensitive completed claim (when mixed with plans), or marks it as plan, opinion, timeless background or uncertain. It explicitly compares realized race identity against the target, records listed runner IDs, assesses before/after/unknown time, and cites code-owned temporal anchor IDs. Context supplies the target date, venue, distance and exact declared field. A later preview can disclose the target as earlier form relative to that later publication; a different distance alone cannot establish earlier timing.

Code requires complete sentence coverage, valid IDs and classifications. A model-classified target result or later completed event vetoes admission. An unsupported assertion that something happened before cutoff leaves the passage uncertain. Before-cutoff grounding requires cited explicit date anchors or source-date claims before cutoff; same-day text dates without clocks remain uncertain. URL/title dates are labeled clues rather than historical availability proof. The classifier can still choose a wrong event kind, match the wrong race or misuse a genuine anchor; mechanical checks are not semantic proof.

All three judges independently review the full passage and the untrusted resolver proposal. They return sentence IDs rather than copied quotations. Code renders the exact quotations from those IDs, retaining offsets and paragraph context. A resolver veto or uncertainty cannot be overridden by three allows. Unsupported/malformed output remains excluded, with no repair or retries. Publication/availability stays null when unknown. Existing source-date hard blocks remain active.

The audit reconstructs the sentence/anchor context from the source and task, matches the resolver to its actual model request and response, recomputes the structural gate, and checks judge IDs against code-rendered quotes. Resolver reasoning and judge prose stay outside selector/forecaster inputs; confidential winners, if used retrospectively, go only to the outcome judge.

## Fresh comparison

`data/event_grounded_review_v1/dataset.json` freezes 18 scenarios from six new January publisher snapshots: six useful, six leakage, four ambiguous, two unrelated. All source URLs and complete case texts differ from the previous 24-case corpus. Four ambiguous cases reuse report paragraphs against different future targets, so scenario counts are dependent. The assistant assigned labels/rationales before model evaluation; there is no independent human adjudication. The protocol was designed using the earlier corpus failures, then frozen for this fresh comparison. No post-result tuning is part of this run.

Two acquisition attempts did not enter the case set: TodoTurf yielded no attributable body, and Giralda failed TLS certificate verification. Their gaps and original acquisition receipts are preserved; certificate checks were not bypassed.

```bash
.venv/bin/python scripts/evaluate_semantic_review.py \
  --dataset data/event_grounded_review_v1/dataset.json \
  --out runs/NEW_EVENT_GROUNDED_COMPARISON \
  --ollama-base http://127.0.0.1:11438 \
  --policies publisher-dated exploratory event-grounded
```

Use an already running installed local model. The script does not start a service or download models. `--resume` verifies frozen inputs, engine hashes, model digest and completed ledgers; incomplete-case ledgers remain preserved. The November 6 run uses `runs/event_grounded_review_v1_20261106`. It scores all failures and disagreements, runs no forecasts, and supplies no review labels or confidential winners to the models.

## Completed comparison

See [EVENT_GROUNDED_RESULTS_20261106.md](EVENT_GROUNDED_RESULTS_20261106.md). Version v2 corrects the no-anchor schema defect; v1 remains frozen. Corrected Llama and Gemma replays admitted no useful cases and no leakage cases, so the policy is still unsuitable for forecasts. Evaluator `--model` selects an installed local judge/resolver model without downloads.
