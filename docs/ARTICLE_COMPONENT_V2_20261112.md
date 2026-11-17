> USER HOLD: do not run or resume experiments without a new explicit instruction. The waiting queue was stopped before inference; zero new calls and no outcome evaluation. Prepared protocol below is retained for review only.

# Scoped extraction and expanded earlier evidence — November 12, 2026

All work is local. Publication remains prohibited without a new explicit user
instruction. No website content, deployment, or held-out outcome evaluation was
created by this task.

## Implemented changes

`horse_racing/article_features_v2.py` builds exact source spans for a horse's own
numbered entry. Section headings such as "Para ganar" remain available as context.
A mention inside another horse's entry carries that actual entry owner and a
distinct scope, instead of silently inheriting its recommendation. Unstructured
paragraphs remain supported; the model still decides what the text means.

Final three-digit tip codes are interpreted as race number plus cloth number and
checked against the official declaration database. Compact entries without a
space, such as `306MUGUETAJARRA`, are supported. Parent-source offsets prove every
excerpt is an exact substring. The extractor chooses one evidence-bound decision:
selected, opposed, historical, withdrawn, or unknown. Historical/withdrawn roles
produce unknown recommendation features while preserving their source evidence.
The schema no longer allows the inconsistent unknown-plus-citation pair that
caused four failures in v1. Invalid responses still fail; no repair or retries.

One real inconsistency was found in the January 4 tip list: a Fiji Gold entry
was coded 509 while the official declaration was race 4, cloth 9 (409). That tip
entry is omitted with a receipt. Its separate prose analysis remains eligible;
the source's code is never silently corrected.

## Expanded earlier corpus

The prepared corpus has 71 source paragraphs, compared with 29 before. It adds:

- Cached January 18 and January 25 previews from AlmiranteCuatro, retaining all
  original nonempty article paragraphs and their existing publisher-date claims.
- [January 4 Madrid preview](https://almirantecuatro.com/2026/01/03/madrid-domingo-04-01-2026/),
  published January 3 at 19:38:48 UTC, before the existing day-before cutoff.
- [January 11 Dos Hermanas preview](https://almirantecuatro.com/2026/01/08/dos-hermanas-domingo-11-01-2026/),
  published January 8, with latest modification January 8 at 22:31:44 UTC.
- Two previously omitted February 1 paragraphs of 1,932 and 1,421 characters,
  recovered from the existing raw HTML. The old publication parser had discarded
  paragraphs over 1,400 characters, removing useful current-race context.

Two cached official January previews without parsed publication claims were
not admitted. The new public collection used one ordinary January index request
to discover exact links, then the two article requests, all HTTP 200. HTML bodies,
capture timestamps, status codes and SHA-256 receipts are in
`data/article_expansion_20261112/`. Web-search discovery alone is not a source
availability receipt. No login, subscription, bypass, or bulk crawl was used.

Historical availability still rests on publisher-controlled dates on pages
retrieved retrospectively in November 2026. These are not certified archived
T-60 bytes. Sources were selected by dates and content coverage, not race winners.
Target results and market prices were not used to prepare extraction tasks.

Eligible source-scoped runner entries grew from 34 to 106 of 368: 77/154 January
training rows and 29/214 February rows. This is availability, not accepted feature
coverage or demonstrated extraction accuracy. Sources and extractor both changed,
so a difference from v1 is not an isolated causal measure of the schema change.

## References and precommitted quality gate

52 source-reviewed development cases were frozen before inference:

- 26 existing regression references, including the comparator and withdrawal
  errors and compact tip-list misses.
- 26 additional references across January 4, 18 and 25, including three current
  adverse January recommendations (Otto, Farnesio, Stephen Dedalus) and negation
  checks such as "no descarto". Current distrust is treated as opposition;
  historical poor form alone is not.

These were reviewed by the coding assistant. They are selected development
examples, not independent human labels or an unseen extraction benchmark. The
corpus has 42 selected, six opposed and four unknown references; accuracy must
be read with that imbalance. Independent review and broader authorship remain
necessary. Existing January–February outcome exposure is unchanged.

Before the automatic outcome evaluator is allowed to run, extraction must:

1. Score all 52 references with at least 90% classification accuracy.
2. Correctly handle both the Shutterwood comparator and Be True withdrawal cases.
3. Have zero failed/inconsistent extraction outputs.
4. Correctly classify at least two of the three January opposed references.

The queue saves `quality_gate.json`. If it fails, it terminates after extraction
without fitting/scoring another forecast model. If it passes, it runs the existing
fixed January-fit/February-score protocol, keeping all 20/28 races, deterministic
form, fixed hyperparameters and outcome-free inference. March–June remains
untouched. No performance gain is claimed before the experiment runs.

## Queue and ownership

Prepared run: `runs/article_component_v2_20261112`.
Pending evaluation: `runs/article_component_v2_evaluation_20261112`.

At launch GPU 3 was occupied by another study (~14,692 MiB). One detached queue
controller, PID 3040880, waits for GPU 3 memory <=100 MiB and free port 11440.
It does not stop or reconfigure other processes or use a different GPU. It checks
every 30 seconds, has no calendar deadline, and checks frozen input/code hashes
before starting. Do not start a second queue or change frozen inference code
without first stopping/reviewing this waiting job.

Read `queue_status.json` for current state. Once started, `status.json` describes
the component worker. The driver owns and cleans up its own local model service.
At most 106 planned model calls (hard preparation ceiling 160), installed
llama3.1:8b, 128 output tokens, 90-second call timeout; no downloads. Raw replies
are preserved. The queue evaluates outcomes only after its quality gate passes.

`scripts/run_article_component.py` received an optional extractor dependency
argument so the same bounded driver can run v2. Matching original v1 runner and
adapter bytes were saved under `runs/article_component_20261112/source_receipts`
before this change; the earlier run remains completed and must not be resumed
under changed code. V2 saves source snapshots and hashes for its own protocol.

Queue command (only if the existing controller is confirmed stopped):

```
OPENBLAS_NUM_THREADS=1 /app/more_studies/forecast-cal-private/.venv/bin/python \
  scripts/queue_article_component_v2.py \
  --out runs/article_component_v2_20261112 \
  --evaluation-out runs/article_component_v2_evaluation_20261112
```

## Verification

180 repository tests passed; one optional shared-engine integration test skipped.
15 focused scoping, article, cohort and quality-gate tests passed. Coverage
includes exact source spans, nonspaced tips, conflicting declaration codes,
another horse's entry, withdrawal context, invalid evidence pointers, and gate
failure on critical errors, failed extraction or incomplete reference coverage.
Every actual prepared span was checked against its parent source. The largest
prepared task was 3,859 bytes before fixed model instructions/schema. No new
extraction scores or outcome results exist while the queue is waiting.
