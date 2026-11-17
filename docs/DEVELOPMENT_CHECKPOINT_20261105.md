# Three-race development checkpoint — 5 November 2026

Run: `runs/development_checkpoint_3_20261105`. Full diagnostics: `checkpoint_report.json`; fixed selection and search rules: `checkpoint_protocol.json`.

Selected the first frozen development entries with 4, 8 and 12 declared runners using declaration metadata only. Each race used paired closed-book/researched arms, two research rounds, up to 12 fresh host-tool searches and 12 pages. No seeded URLs. Local llama3.1:8b ran on GPU 0, port 11436, separately from the sibling benchmark on GPU 2. The temporary service was unloaded and stopped after completion.

| Declared runners | Closed-book | Researched | Approved passages | Research wall time |
|---|---|---|---|---|
| 4 | Valid first attempt | Valid first attempt | 0 | 221 s |
| 8 | Invalid twice (sum 1.10) | Valid second attempt | 0 | 194 s |
| 12 | Invalid twice (sum 1.50) | Invalid twice (sum 1.20) | 0 | 188 s |

Three of six forecasts were valid. All malformed distributions remain excluded and unchanged. The valid eight-runner researched distribution assigned zero probability to four horses, including the winner; validity alone does not establish usefulness.

The 36 searches led to 33 page attempts: 25 failed for missing supported publication dates, four required unsupported PDF extraction, two exceeded the document budget, and one lacked an attributable body. One dated preview was extracted successfully but had no paragraph matching the assigned horse COGSWORTH; it never reached the judges. No judge calls occurred, so this checkpoint cannot measure judge sensitivity or approval quality.

Only the four-runner race supports a paired score: closed-book Brier 0.6750 / log loss 1.2040; researched Brier 0.6156 / log loss 1.1087; uniform Brier 0.7500 / log loss 1.3863. With zero admitted evidence and one paired race, the difference cannot establish a benefit from research. The researched arm also receives a different coverage context. Wall times include interactive bridge latency; recorded model inference totals were approximately 32, 48 and 55 seconds per paired race.

Recommendation: fix the observed bottlenecks before the 20-race pilot. Prioritize dated reporting queries with exact entity identities, reassignment of meeting previews to matching declared entities, and bounded dated-PDF support. Separately investigate complete-distribution arithmetic prompts and retry feedback while preserving the two-attempt contract and prohibition on repairing probabilities. Repeat a separately labeled development checkpoint and retain this baseline.

Validation: 100 deterministic tests passed, including three new split-selection guard tests. All six ledgers passed the data-flow audit. Both frozen bundles verified and the master database SHA256 was unchanged. No validation/test runs were started and the sibling benchmark was untouched.
