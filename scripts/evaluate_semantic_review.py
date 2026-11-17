"""Compare semantic and publisher-dated policies on frozen, reviewed real excerpts.

No forecasts, outcome database reads, hosted models, downloads, or dataset-label prompts.
"""
import argparse,collections,hashlib,json,shutil,sys,time
from dataclasses import asdict
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from horse_racing.benchmark import digest,read_jsonl
from horse_racing.engine.model import Audit,Ollama
from horse_racing.engine.publications import publisher_source
from horse_racing.engine.leakage import JudgePanel,deterministic_gate
from horse_racing.engine.run import audit_run

p=argparse.ArgumentParser()
p.add_argument('--dataset',default='data/semantic_leakage_review_v1/dataset.json')
p.add_argument('--out',required=True)
p.add_argument('--model',default='llama3.1:8b',help='Installed local model for all judge/resolver roles; no automatic download')
p.add_argument('--ollama-base',default='http://127.0.0.1:11434')
p.add_argument('--policies',nargs='+',choices=['publisher-dated','exploratory','event-grounded'],default=['publisher-dated','exploratory'])
p.add_argument('--resume',action='store_true',help='Resume only after verifying frozen inputs and completed ledgers')
a=p.parse_args();dataset_path=Path(a.dataset);data=json.loads(dataset_path.read_text());out=Path(a.out)
if out.exists() and not a.resume:raise FileExistsError(out)
if a.resume and not out.exists():raise FileNotFoundError(out)
if len(a.policies)!=len(set(a.policies)):raise ValueError('Duplicate policy')
# Verify the independent record before labels are separated from model inputs.
snapshots={}
for key,record in data['snapshots'].items():
    path=dataset_path.parent/record['file']
    if digest(path)!=record['sha256']:raise ValueError('Source snapshot hash mismatch')
    snapshots[key]=json.loads(path.read_text())
for case in data['cases']:
    source=snapshots[case['source_snapshot']]
    exact='\n\n'.join(source['paragraphs'][i] for i in case['paragraph_indices'])
    if exact!=case['text'] or hashlib.sha256(exact.encode()).hexdigest()!=case['text_sha256']:raise ValueError('Excerpt changed')
    if case['task'].get('split')!='development':raise ValueError('Only development tasks permitted')
if not a.resume:
    out.mkdir(parents=True);(out/'reviewed_sources').mkdir()
    shutil.copyfile(dataset_path,out/'dataset.json')
    for key,record in data['snapshots'].items():shutil.copyfile(dataset_path.parent/record['file'],out/'reviewed_sources'/record['file'])
    code=Path('horse_racing/engine');(out/'source').mkdir()
    for f in code.glob('*.py'):shutil.copyfile(f,out/'source'/f.name)
    shutil.copyfile(__file__,out/'evaluation_script.py')
    manifest=dict(scope=data['scope'],dataset_sha256=digest(dataset_path),policies=a.policies,ollama_base=a.ollama_base,
        expected_labels='Supervisor scoring only; never in judge requests',known_winners='Not supplied',judge_model=a.model,source_hashes={f.name:digest(f) for f in code.glob('*.py')},
        evaluation_script_sha256=digest(Path(__file__)),reviewed_source_hashes=data['snapshots'],ledger_sha256={})
    (out/'run_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    results=[]
else:
    manifest=json.loads((out/'run_manifest.json').read_text())
    if (manifest['dataset_sha256']!=digest(dataset_path) or digest(out/'dataset.json')!=manifest['dataset_sha256']
        or manifest['policies']!=a.policies or manifest['ollama_base']!=a.ollama_base or manifest.get('judge_model','llama3.1:8b')!=a.model):raise ValueError('Resume identity mismatch')
    for name,h in manifest['source_hashes'].items():
        if digest(Path('horse_racing/engine')/name)!=h or digest(out/'source'/name)!=h:raise ValueError('Engine changed since interruption')
    if digest(out/'evaluation_script.py')!=manifest['evaluation_script_sha256']:raise ValueError('Original evaluation script changed')
    for key,record in manifest['reviewed_source_hashes'].items():
        if digest(out/'reviewed_sources'/record['file'])!=record['sha256']:raise ValueError('Frozen source changed')
    results=read_jsonl(out/'results.jsonl') if (out/'results.jsonl').exists() else []
    completed={(r['policy'],r['id']) for r in results}
    if len(completed)!=len(results):raise ValueError('Duplicate completed assessment')
    expected={(policy,c['id']):c['expected'] for policy in a.policies for c in data['cases']}
    for r in results:
        if expected.get((r['policy'],r['id']))!=r['expected']:raise ValueError('Completed result identity mismatch')
        relative=f"ledgers/{r['policy']}_{r['id']}.jsonl"
        if digest(out/relative)!=manifest['ledger_sha256'].get(relative):raise ValueError('Completed ledger changed')
    interrupted=[]
    completed_paths={f"{policy}_{cid}.jsonl" for policy,cid in completed}
    for ledger in (out/'ledgers').glob('*.jsonl'):
        if ledger.name in completed_paths:continue
        dest=out/'interrupted_ledgers'/ledger.name;dest.parent.mkdir(exist_ok=True)
        if dest.exists():raise FileExistsError(dest)
        ledger.rename(dest);relative=str(dest.relative_to(out));manifest['ledger_sha256'][relative]=digest(dest)
        interrupted.append(relative)
    recovery=dict(reason='Resumed after process interruption; complete results reused, partial-case ledger retained and full panel attempted again',
        completed_before_resume=len(results),interrupted_ledgers=interrupted,resume_script_sha256=digest(Path(__file__)))
    manifest.setdefault('recovery_history',[]).append(recovery)
    shutil.copyfile(__file__,out/f"evaluation_resume_{len(manifest['recovery_history'])}.py")
    (out/'run_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
start=time.monotonic();installed=manifest.get('installed_models')
if a.resume and installed is not None:
    current=Ollama(None,base=a.ollama_base).tags()
    expected_digest=next(m['digest'] for m in installed if m['name']==a.model)
    if not any(m['name']==a.model and m['digest']==expected_digest for m in current):raise ValueError('Resume model digest changed')
completed={(r['policy'],r['id']) for r in results}
for policy in a.policies:
    for case in data['cases']:
        if (policy,case['id']) in completed:continue
        source=snapshots[case['source_snapshot']]
        # Withheld date metadata is a recorded test ablation. URL/title are untouched.
        claims=source['date_claims'] if case['dating_scenario']=='publisher' else []
        response=dict(observed_at=source['observed_at'],sha256=source['body_sha256'])
        s=publisher_source(source['url'],response,[case['text']],claims,allow_undated=True,**source['metadata'])
        ledger=out/'ledgers'/f"{policy}_{case['id']}.jsonl";audit=Audit(ledger);model=Ollama(audit,base=a.ollama_base)
        if installed is None:
            installed=model.tags()
            if a.model not in {x['name'] for x in installed}:raise ValueError('Requested local model is not installed; no download/fallback')
            manifest['installed_models']=installed
        audit.log('source',source=asdict(s));t=time.monotonic()
        decision=JudgePanel(model,audit,policy=policy,models={role:a.model for role in ('provenance','outcome','relevance')}).assess(case['task'],case['information_need'],s,case['text'])
        if decision['allow'] and not deterministic_gate(s,case['text'],case['task']['cutoff_utc'],policy)['allow']:raise ValueError('Admitted hard-blocked source')
        rows=read_jsonl(ledger)
        request_text=json.dumps([r['request'] for r in rows if r['event']=='model_request'])
        if 'review_rationale' in request_text or 'confidential_known_winners' in request_text or 'expected_allow' in request_text:raise ValueError('Evaluation label leaked')
        record=dict(id=case['id'],policy=policy,category=case['category'],expected=case['expected'],
            decision=decision['decision'],allow=decision['allow'],correct=decision['decision']==case['expected'],
            seconds=time.monotonic()-t,judge_calls=sum(r['event']=='model_request' for r in rows),assessment=decision)
        results.append(record)
        with (out/'results.jsonl').open('a') as f:f.write(json.dumps(record,ensure_ascii=False)+'\n')
        manifest['ledger_sha256'][str(ledger.relative_to(out))]=digest(ledger)
        (out/'run_manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
        print(json.dumps({k:record[k] for k in ('id','policy','expected','decision','judge_calls','seconds')}),flush=True)

reports={}
for policy in a.policies:
    rows=[r for r in results if r['policy']==policy]
    confusion={e:{d:sum(r['expected']==e and r['decision']==d for r in rows) for d in ('allow','reject','uncertain')} for e in ('allow','reject','uncertain')}
    leakage=[r for r in rows if r['category'] in ('target_leakage','known_postcutoff_source')]
    useful=[r for r in rows if r['expected']=='allow'];ambiguous=[r for r in rows if r['expected']=='uncertain']
    reports[policy]=dict(total=len(rows),confusion=confusion,exact_agreements=sum(r['correct'] for r in rows),
        leakage_allowed=sum(r['allow'] for r in leakage),leakage_cases=len(leakage),
        useful_allowed=sum(r['allow'] for r in useful),useful_cases=len(useful),useful_rejected=sum(r['decision']=='reject' for r in useful),useful_uncertain=sum(r['decision']=='uncertain' for r in useful),
        ambiguous_allowed=sum(r['allow'] for r in ambiguous),ambiguous_cases=len(ambiguous),
        judge_calls=sum(r['judge_calls'] for r in rows),error_votes=sum(v['verdict']=='error' for r in rows for v in r['assessment']['votes']),
        resolution_errors=sum('resolution_error' in r['assessment'] for r in rows),
        event_resolution_rejections=sum(r['assessment'].get('resolution_gate',{}).get('decision')=='reject' for r in rows),
        disagreements=[r['id'] for r in rows if not r['correct']])
report=dict(model=a.model,scope=data['scope'],review=data['review'],related_cases=data['related_cases'],policies=reports,
    current_process_seconds=time.monotonic()-start,completed_case_seconds=sum(r['seconds'] for r in results),recovery_history=manifest.get('recovery_history',[]),limitations=['Small curated development diagnostic with repeated sources and metadata ablations; no population accuracy claim',
    'Assistant annotations are not independent human labels; ambiguous cases need review',f'Judge and event-resolver roles share {a.model} weights; correlated errors remain possible',
    'Semantic allow does not establish historical availability; missed implicit leakage remains possible'],results=results)
(out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
audit=audit_run(out)
print(json.dumps(dict(policies=reports,audit=audit['status']),indent=2),flush=True)
