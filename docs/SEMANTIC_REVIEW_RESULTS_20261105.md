# Semantic leakage review results — 5 November 2026

The optional exploratory policy is implemented, but the first local-model evaluation does not support using it for forecasting. It gained access to undated previews and also admitted target outcomes.

| Measure | Publisher-dated baseline | Exploratory semantic review |
|---|---:|---:|
| Useful scenarios admitted | 4 / 8 | 3 / 8 |
| Leakage scenarios admitted | 0 / 8 | 2 / 8 |
| Ambiguous scenarios admitted | 0 / 6 | 1 / 6 |
| Unrelated controls admitted | 0 / 2 | 0 / 2 |
| Judge calls on completed cases | 18 | 66 |
| Invalid supporting-quote responses | 0 | 17 |

The baseline generally blocked missing publication metadata before semantic review. Exploratory review admitted two naturally undated preview passages which the baseline excluded. It also lost useful evidence through false outcome vetoes and failures to copy exact quotes. Uncertain/error cases remained outside predictor inputs; they are not silently counted as correct semantic rejections.

Two clear misses require attention:

- `r05_target_stewards_incident`: all three roles allowed the [January 11 result report](https://www.abc.com.py/deportes/polideportivo/2026/01/11/triplete-del-preparador-argentino-anaya-en-dos-hermanas-espana/?outputType=amp), including the Spanish Ruler/Sweet Wish finish and stewards incident for the target field. The temporal judge asserted a pre-cutoff date without supporting evidence; the outcome judge failed to identify the matching race.
- `r08_later_preview_reveals_target_result`: all three roles allowed the [January 29 preview](https://almirantecuatro.com/2026/01/29/dos-hermanas-domingo-01-02-2026/) describing Madame Caracol's earlier Madrid 1200m victory, which was the January 4 target being forecast. This is a genuine later-source disclosure when date metadata is withheld, not harmless earlier history relative to that target.

The dataset was frozen before model execution: 24 assistant-reviewed scenarios from six genuine publisher snapshots, using development target packets. Some scenarios deliberately withhold date metadata while retaining original URLs/titles; they are recorded ablations. Repeated sources/excerpts are dependent probes. These are not independent human labels or population accuracy estimates. No prompts or labels were tuned to the observed results.

The evaluation process received an unexpected SIGTERM after 34 completed assessments. Cause is unconfirmed. Recovery verified dataset, source, engine and completed-ledger hashes, reused the 34 results, and preserved the partial next-case ledger before rerunning that case. All 48 policy/scenario pairs occur exactly once in the scored results; the interrupted attempt remains separate. All 49 ledgers passed the mechanical audit, which verifies data flow and integrity rather than semantic correctness.

Artifacts: `runs/semantic_leakage_review_v1_20261105/report.json`, `results.jsonl`, `audit_report.json`, frozen source snapshots and model ledgers. The dataset is `data/semantic_leakage_review_v1/dataset.json`. Commands and policy details are in [SEMANTIC_REVIEW.md](SEMANTIC_REVIEW.md); `--resume` verifies identity and preserves incomplete-case attempts.

Validation: 112 deterministic tests passed. Both frozen benchmarks verified; master database SHA256 stayed unchanged. The evaluation-only GPU 0 / port 11437 service was unloaded and stopped. The GPU 2 sibling service and its files were untouched. No forecasting pilot or monitor was started.

Next: separate explicit event identity and temporal reasoning from final verdicts, and select code-owned sentence IDs to avoid unreliable quote copying. Freeze the next protocol and test fresh independently reviewed passages. Keep this failed baseline intact and the exploratory policy optional.
