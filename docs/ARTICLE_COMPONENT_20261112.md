# Local article extraction experiment — November 12, 2026

Publication is prohibited by the user's current instruction. This experiment
and all outputs stay in the research workspace. No website files were generated
and no hosting calls were made. The rejected website's takedown remains in place.

## Changes and scope

`horse_racing/article_features.py` separates article extraction from deterministic
form. Each inference concerns one horse and only the publisher's current
recommendation: selected, opposed, or unknown. Candidate passages must name the
whole horse, concern the target event date, and have a publisher availability
claim before the existing cutoff. Historical comparator mentions and withdrawn
former favourites should remain unknown. Exact name matching is a coverage
filter, not proof that the passage is about that horse's current prospects.

The agent chooses a supplied evidence ID. The corresponding complete paragraph
is copied from the source by code, so the agent cannot invent a quotation.
This guarantees quote identity only; it does not certify the interpretation.
Unknown claims must use a null evidence ID. No trouble, form, probability or
result fields are requested. Unsupported outputs fail and remain in raw traces.

This is a controlled-source component test using the preserved 29-paragraph
corpus, not an end-to-end evaluation of the shared engine's research/retrieval.
It borrows the sibling engine's existing local model adapter. No upstream
orchestration code was duplicated or changed. The corpus has just two target
preview dates (January 11 and February 1). Dates remain publisher-documented
retrospective assumptions; historical cutoffs are day-before, not certified T-60.

The runner does not read race outcomes or odds. Only the later CPU evaluator
loads labels. Reference labels were made from source text before this inference
run by the coding assistant. They are development references, not independent
human annotation. January–February outcomes were exposed earlier in the project;
this whole exercise is development work, not a fresh blind test.

## Execution and extraction results

`runs/article_component_20261112`: completed 368 runner rows, GPU 3's owned
service stopped normally. Installed llama3.1:8b, dedicated port 11440, 8,192-token
context, 256 output-token maximum, 90-second call timeout, at most 40 inference
calls. GPU 2 and unrelated services were untouched. No packages/models downloaded.

- 34 rows had eligible named-horse source passages and received inference.
- 334 had no eligible passage and remained unknown without inference.
- Of 34 model calls, 30 passed validation, four failed. The failed replies
  classified the horse as unknown but supplied a non-null evidence ID. They were
  rejected without repair or retry.
- 26 rows gained nonzero article features: 20 selected and six opposed.
- All failed/unavailable article rows retain their original deterministic form
  in the downstream forecast. No training/evaluation race was removed.

The selected source-reviewed reference set scored 20/26 correct (76.9%). Four
current picks appearing only in the compact final tip list were missed: Imonfire,
Xmas, Fiji Gold and Sound of Freedom. Shutterwood was incorrectly treated as a
current selection despite being mentioned as an earlier opponent. Be True was
labelled opposed despite the rubric requiring withdrawn former favourites to
remain unknown. These errors prevent treating the extracted features as audited
high-quality semantic data. The reference set is deliberately small and selected;
its accuracy is not an estimate of population extraction precision.

## Matched-cohort forecast evaluation

`runs/article_component_evaluation_20261112`: 20 January training races, same 28
February development races for every arm. Feature standardization and weights
use January only; ridge=1.0 and 1,000 Adam steps remain fixed. The frozen baseline
is an offset. No February hyperparameter or calibration fitting was done.

| Forecast | February races | Brier | Log loss |
|---|---:|---:|---:|
| Frozen baseline | 28 | 0.8148060984 | 1.8551627894 |
| Baseline + deterministic form | 28 | 0.8146028981 | 1.8445552143 |
| Form + optional article features | 28 | 0.8125226973 | 1.8230203950 |

Article minus form Brier difference is -0.0020802008. A 4,000-draw meeting-cluster
percentile interval is [-0.0039498597, +0.0000108313], including zero. The log-loss
difference is -0.0215348193, interval [-0.0575751230, -0.0008526708]. There are only
six February meeting clusters; these exploratory fixed-model intervals omit
training uncertainty. Relative to the frozen baseline, both intervals include
zero. The model is not promoted and no dependable performance gain is claimed.

An additional training-support issue: January contains selected recommendations
but no opposed recommendations. The learned opposed coefficient is zero, while
selected and known flags are collinear in January and receive equal positive
coefficients (~0.07693). A February opposed label can therefore receive an uplift
through the known flag, despite no learned opposition effect. Do not interpret
this as a reliable model of adverse recommendations. Future training sources
need both stances and a better justified handling of evidence availability. Do
not tune that design on these February outcomes and call it unseen validation.

On the SAME 17 February races with complete reported-price proxies, article-model
Brier is 0.8229714179 versus form 0.8275699978 and price proxy 0.7994988332. The
proxy remains better. There are zero verified exact closing or historical T-60
fields. No executable-return claim is supported.

Descriptive ten-bin pooled-runner ECE: baseline 0.0266278520; form 0.0182336623;
article model 0.0166700101. The 214-runner diagnostic is not proof of calibration;
the new model has no separate calibration fit or per-horse uncertainty interval.

## Verification, artifacts and next steps

174 repository tests passed, one optional integration skip. Twenty focused
article, cohort and extraction tests also passed. Tests cover date/entity gates,
ambiguous source identities, exact source-pointer citation, unknown handling,
no inference without sources, deterministic form preservation and cohort identity.

Inputs, code hashes, model digest, runtime, reference labels and unmodified
responses are saved in the component run. Per-runner results and traces preserve
all four failures. The evaluation saves feature assemblies with per-runner
article status, trained weights, predictions, metrics, intervals and price receipts.

Current next work:
1. Review horse-specific source scoping so comparator/withdrawal mentions are
   not mistaken for present recommendations. Decode compact tip lists reliably.
2. Add independently reviewed extraction examples and enough earlier preview
   dates to cover positive and adverse recommendations in training.
3. Measure extraction quality and actual source coverage before integrating the
   new adapter into the sibling research API's end-to-end retrieval workflow.
4. Freeze a new protocol before touching March–June validation/test outcomes.
   Do not iterate on February until a favourable score appears.
5. Keep all work local. No publication without a new explicit user instruction.

`scripts/build_research_release.py` also no longer exports website data by
default. The new article evaluator never exports website files at all.
