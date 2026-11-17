"""Summarize frozen comparisons without changing model judgments or review labels."""
import collections,json
from pathlib import Path
RUNS={
 'original_llama_comparison':'runs/event_grounded_review_v1_20261106',
 'corrected_llama_replay':'runs/event_grounded_v2_llama_replay_20261106',
 'corrected_gemma_replay':'runs/event_grounded_v2_gemma_replay_20261106'}
summary={}
for label,directory in RUNS.items():
 root=Path(directory);report=json.loads((root/'report.json').read_text());manifest=json.loads((root/'run_manifest.json').read_text())
 details={}
 for policy,metrics in report['policies'].items():
  rows=[r for r in report['results'] if r['policy']==policy];leaks=[r for r in rows if r['category']=='target_leakage']
  details[policy]=dict(metrics,
   leakage_explicitly_matched_by_resolver=sum(any(reason.endswith(':target_realized_event') for reason in r['assessment'].get('resolution_gate',{}).get('reasons',[])) for r in leaks),
   leakage_rejected=sum(r['decision']=='reject' for r in leaks),leakage_uncertain=sum(r['decision']=='uncertain' for r in leaks),
   resolver_error_reasons=dict(collections.Counter(r['assessment']['resolution_error'] for r in rows if 'resolution_error' in r['assessment'])),
   judge_error_reasons=dict(collections.Counter(v['reason'] for r in rows for v in r['assessment']['votes'] if v['verdict']=='error')),
   complete_case_seconds=sum(r['seconds'] for r in rows),useful_admitted_ids=[r['id'] for r in rows if r['expected']=='allow' and r['allow']],
   leakage_admitted_ids=[r['id'] for r in leaks if r['allow']])
 summary[label]=dict(run=directory,model=manifest.get('judge_model','llama3.1:8b'),dataset_sha256=manifest['dataset_sha256'],policies=details,audit=json.loads((root/'audit_report.json').read_text())['status'])
a=json.loads((Path(RUNS['corrected_llama_replay'])/'run_manifest.json').read_text());b=json.loads((Path(RUNS['corrected_gemma_replay'])/'run_manifest.json').read_text())
assert a['source_hashes']==b['source_hashes'] and a['dataset_sha256']==b['dataset_sha256']
result=dict(comparisons=summary,corrected_models_share_engine_and_dataset=True,
 scope='Original fresh development comparison, then corrected-schema replays and an installed-model comparison on the now-exposed corpus. No independent human labels or unbiased holdout gain claim.',
 schema_correction='v1 offered NO_ANCHOR when no date anchor existed; v2 permits only [] in that case. Both versions and all failures retained. No semantic prompt or label changes in the corrected comparison.')
Path('data/event_grounded_review_v1/comparison_summary.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(result,indent=2))
