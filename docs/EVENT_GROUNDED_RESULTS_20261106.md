# Event review status — 6 November 2026

The event/race/time resolver and code-owned sentence citations are implemented as an optional policy. It is not ready for forecasting: both installed models excluded all six useful cases.

| Policy/model | Useful admitted | Leakage admitted |
|---|---:|---:|
| Publisher-dated / Llama | 3/6 | 0/6 |
| Earlier exploratory / Llama | 2/6 | 2/6 |
| Corrected event review / Llama | 0/6 | 0/6 |
| Corrected event review / Gemma | 0/6 | 0/6 |

The first comparison used 18 fresh assistant-reviewed scenarios from six new source URLs, with labels frozen before execution. The corrected model comparisons replayed this now-exposed development corpus; they are not independent holdout measurements. Repeated paragraphs with different target contexts are dependent probes. There is no independent human adjudication.

The original schema mistakenly offered NO_ANCHOR as an ID when no anchor existed, causing nine validation errors. Version v2 permits only an empty list in that case; the original failed trial remains preserved. No semantic prompt or label changes were made for the corrected model comparison.

Llama explicitly matched five of six leakage cases, leaving one uncertain; Gemma matched four, leaving two uncertain. Both also confused useful previews or earlier performances with target results. Zero admitted leakage therefore comes with zero useful coverage. Remaining resolver errors were two duplicate/invented sentence-identity responses for Llama and one for Gemma. Remaining judge output errors were three for Llama and six for Gemma. Errors and uncertain cases remain in the denominators.

133 deterministic tests passed. All 90 recorded assessment ledgers passed their mechanical audits; audit compatibility covers both protocol versions. Frozen benchmark bundles and master database were verified unchanged. Temporary GPU 0 / port 11438 service was stopped; GPU 2 and sibling studies were untouched. No forecasting pilot or monitor was launched.

Canonical artifacts: data/event_grounded_review_v1/comparison_summary.json and the three run directories named there. The source corpus, original failed schema trial, corrected replays, raw model outputs and all disagreements remain saved. See [protocol details](EVENT_GROUNDED_REVIEW.md).

Next: first validate a simpler Spanish distinction between completed events and plans/opinions, then compare event identity. Supply code-owned literal runner matches to reduce alias mistakes. Evaluate those stages on reviewed sentence pairs before restoring the full unanimous panel or starting the 20-race pilot.
