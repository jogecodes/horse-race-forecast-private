"""Development-first paired runs with exact prompt ledgers and frozen code snapshots."""
import json,hashlib,shutil
from pathlib import Path
from ..db import utc,uid
from ..benchmark import verify,read_jsonl,write_jsonl,digest,validate_prediction
from ..recovered_benchmark import score
from .model import Audit,Ollama,json_reply
from .sources import Researcher,Source
from .discovery import Explorer
from .leakage import JudgePanel,deterministic_gate
from .pipeline import strict_roster,forecast,public_task
from . import ENGINE_VERSION


def run_benchmark(bundle,out,db='data/racing.sqlite',split='development',limit=2,track='strict',
                  model_name='llama3.1:8b',rounds=2,cache='data/research_cache',seed_urls=(),known_answers_for_judge=True,research_policy='auto',search_backend='builtin',max_search_queries=12,max_research_pages=12,race_ids=None,ollama_base='http://127.0.0.1:11434'):
    manifest=verify(bundle);root=Path(bundle);out=Path(out)
    if out.exists():raise FileExistsError(out)
    if track not in ('strict','diagnostic','publisher-documented'):raise ValueError('Unknown track')
    if track=='publisher-documented' and manifest.get('track')!='publisher_documented':raise ValueError('Publisher-documented track requires a declaration-based bundle')
    if track=='diagnostic' and manifest.get('track')=='publisher_documented':raise ValueError('Use --track publisher-documented for this bundle')
    if split not in ('development','validation','test'):raise ValueError('Unknown split')
    if type(limit) is not int or limit<1:raise ValueError('Positive race limit required')
    tasks=[t for t in read_jsonl(root/'diagnostic/tasks.jsonl') if t['split']==split]
    if race_ids is not None:
        if not race_ids or len(set(race_ids))!=len(race_ids):raise ValueError('Race IDs must be nonempty and unique')
        available={t['race_id']:t for t in tasks}
        if any(rid not in available for rid in race_ids):raise ValueError('Requested race is outside selected split')
        tasks=[available[rid] for rid in race_ids]
    else:tasks=tasks[:limit]
    if not tasks:raise ValueError('No races in selected split')
    cases={c['race_id']:c for c in read_jsonl(root/'supervisor/cases.jsonl')}
    labels={c['race_id']:c['target'] for c in read_jsonl(root/'supervisor/labels.jsonl')} if known_answers_for_judge else {}
    out.mkdir(parents=True);predictions={'closed_book':[],'researched':[]};statuses=[];ledger_paths=[]
    code=Path(__file__).parent
    for path in code.glob('*.py'):
        dest=out/'source'/path.name;dest.parent.mkdir(exist_ok=True);shutil.copyfile(path,dest)
    policy=('strict' if track=='strict' else 'publisher-dated') if research_policy=='auto' else research_policy
    if policy not in ('strict','publisher-dated','exploratory','event-grounded'):raise ValueError('Unknown research policy')
    if track=='strict' and policy!='strict':raise ValueError('Strict runs require strict research provenance')
    model_tags=[];research_reports=[]
    run_spec=dict(engine_version=ENGINE_VERSION,benchmark_version=manifest['version'],benchmark_manifest_sha256=digest(root/'manifest.json'),
      ollama_base=ollama_base,track=track,research_policy=policy,search_backend=search_backend,max_search_queries=max_search_queries,max_research_pages=max_research_pages,split=split,requested_race_ids=[t['race_id'] for t in tasks],model=model_name,rounds=rounds,
      judges=dict(provenance='llama3.1:8b',outcome='llama3.1:8b',relevance='llama3.1:8b'),
      contexts='Stateless separate requests; judge roles share one local weight set; not independent trained models',
      options=dict(temperature=0,seed=0,num_ctx=8192,forecast_attempts=2),known_answers='outcome judge only' if known_answers_for_judge else 'not supplied',
      source_hashes={p.name:digest(p) for p in code.glob('*.py')},seed_urls=list(seed_urls))
    (out/'run_manifest.json').write_text(json.dumps(run_spec,ensure_ascii=False,indent=2)+'\n')
    for task_ref in tasks:
        rid=task_ref['race_id'];packet=json.loads((root/f'diagnostic/packets/{rid}.json').read_text())
        if track=='strict':
            check=strict_roster(db,cases[rid]['source_race_id'],packet)
            if not check['verified']:
                statuses.append(dict(race_id=rid,status='strict_blocked',reason=check['reason']));continue
            packet=check['task']
        known=None
        if rid in labels:known=[r['horse_name'] for r in packet['runners'] if labels[rid][r['runner_id']]>0]
        for arm in ('closed_book','researched'):
            ledger=out/'ledgers'/f'{rid}_{arm}.jsonl';audit=Audit(ledger);ledger_paths.append(ledger)
            model=Ollama(audit,base=ollama_base)
            if track=='strict':audit.log('declaration_proof',proof=check['proof'],task=packet)
            elif track=='publisher-documented':audit.log('publisher_declaration_proof',proof=cases[rid]['declaration'])
            if not model_tags:
                model_tags=model.tags();run_spec['installed_models']=model_tags
                needed={model_name,'llama3.1:8b'}
                if not needed.issubset({m['name'] for m in model_tags}):raise ValueError('Required local models are not installed; no automatic download or hosted fallback')
            researcher=Explorer(out/'research_cache'/rid,audit,model,public_task(packet),policy=policy,search_backend=search_backend,max_queries=max_search_queries,max_pages=max_research_pages,research_model=model_name)
            panel=JudgePanel(model,audit,policy=policy)
            try:
                result=forecast(packet,model,researcher,panel,audit,planner_model=model_name,
                                selector_model=model_name,forecaster_model=model_name,rounds=rounds,
                                known_winners=known,seed_urls=seed_urls,research=arm=='researched')
                if result['prediction']:predictions[arm].append(result['prediction'])
                if arm=='researched':research_reports.append(dict(race_id=rid,**result['research_report']))
                statuses.append(dict(race_id=rid,arm=arm,status='valid' if result['prediction'] else 'parse_failure',
                                     error=result['error'],forecast_attempts=result['forecast_attempts'],invalid_attempts=result['invalid_attempts'],approved_items=result['approved_items'],selected_items=result['selected_items']))
            except Exception as e:
                audit.log('sample_error',error=str(e));statuses.append(dict(race_id=rid,arm=arm,status='model_or_research_error',error=str(e)))
            print(json.dumps(statuses[-1]),flush=True)
    write_jsonl(out/'research_reports.jsonl',research_reports)
    summaries={}
    for arm,rows in predictions.items():
        path=out/f'{arm}_predictions.jsonl';write_jsonl(path,rows)
        report=score(bundle,path,split)
        (out/f'{arm}_scores.json').write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
        summaries[arm]=dict(valid=len(rows),attempted=sum(s.get('arm')==arm for s in statuses),
                            requested=len(tasks),full_split_coverage=report['coverage'],metrics_on_valid_subset=report['overall'])
    common={p['race_id'] for p in predictions['closed_book']} & {p['race_id'] for p in predictions['researched']}
    # Keep a reproducible paired subset rather than compare different successful parse subsets.
    paired={}
    for arm,rows in predictions.items():
        path=out/f'{arm}_paired_predictions.jsonl';write_jsonl(path,[r for r in rows if r['race_id'] in common])
        paired[arm]=score(bundle,path,split)['overall']
    verdict=dict(engine_version=ENGINE_VERSION,track=track,research_policy=policy,strict_mode_enforced=track=='strict',
      strict_historical_validity=track=='strict' and bool(predictions['researched']),
      requested_races=len(tasks),strict_blocked=sum(s['status']=='strict_blocked' for s in statuses),
      statuses=statuses,arms=summaries,paired_valid_races=len(common),paired_metrics=paired,
      caveat='A limited smoke is not a full benchmark result. Official declaration inputs rely on publisher dating in publisher-documented mode; diagnostic v1 fields are post-race reconstructions. Neither certifies strict historical availability.')
    (out/'summary.json').write_text(json.dumps(verdict,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    run_spec['ledger_sha256']={str(p.relative_to(out)):digest(p) for p in ledger_paths}
    (out/'run_manifest.json').write_text(json.dumps(run_spec,ensure_ascii=False,indent=2)+'\n')
    return verdict


def audit_run(out):
    out=Path(out);manifest=json.loads((out/'run_manifest.json').read_text());checks=[]
    for name,expected in manifest.get('source_hashes',{}).items():
        if digest(out/'source'/name)!=expected:raise ValueError('Frozen engine source hash mismatch')
    for relative,expected in manifest.get('ledger_sha256',{}).items():
        path=out/relative
        if digest(path)!=expected:raise ValueError('Ledger file hash mismatch')
        previous='0'*64;approved={};selected={};sources={};final_payload=None;finals=0;model_calls=0;runner_map=None;original_task=None;forecast_raw=None
        event_resolutions={};resolver_request=None;resolver_response=None
        def check_extract(e):
            original=approved.get(e['item_id'])
            if original is None or e['paragraph_context']!=original['text'] or e['source_id']!=original['source_id']:
                raise ValueError('Evidence does not match admitted paragraph')
            if e['paragraph_context'][e['start']:e['end']]!=e['text']:
                raise ValueError('Non-extractive evidence')
            if e['sentence_id']!='s'+uid(e['item_id'],e['start'],e['end']):
                raise ValueError('Invented sentence identity')
        for row in read_jsonl(path):
            claimed=row.pop('event_sha256')
            if row['previous_sha256']!=previous:raise ValueError('Audit chain is broken')
            computed=hashlib.sha256(json.dumps(row,ensure_ascii=False,sort_keys=True,allow_nan=False).encode()).hexdigest()
            if computed!=claimed:raise ValueError('Audit event hash mismatch')
            previous=claimed
            if row['event']=='source' and 'source' in row:sources[row['source']['source_id']]=Source(**row['source'])
            if row['event']=='forecast_runner_map':
                original_task=row['original_task'];runner_map=row['mapping']
                if public_task(original_task,strict=original_task.get('track')=='strict')!=original_task:
                    raise ValueError('Runner mapping task contains unapproved fields')
                expected={f'r{i+1}':r['runner_id'] for i,r in enumerate(original_task['runners'])}
                if runner_map!=expected or len(set(runner_map.values()))!=len(runner_map):
                    raise ValueError('Invalid runner alias mapping')
            if row['event']=='model_response' and row['role']=='forecaster':forecast_raw=row['text']
            if row['event']=='model_response' and row['role']=='event_resolver':resolver_response=row['text']
            if row['event']=='event_resolution':
                from .events import context,resolution_gate
                source=sources.get(row['source_id'])
                if source is None:raise ValueError('Missing event-resolution source')
                if public_task(row['task'],strict=row['task'].get('track')=='strict')!=row['task']:raise ValueError('Event-resolution task contains unapproved fields')
                expected=context(row['task'],source,row['text'],protocol=row['payload'].get('protocol'))
                if row['payload']!=expected or resolver_request!=expected:raise ValueError('Altered event-resolution context')
                if resolver_response is None or json_reply(resolver_response)!=row['resolution']:raise ValueError('Event resolution differs from model reply')
                if resolution_gate(expected,row['resolution'])!=row['gate']:raise ValueError('Altered event-resolution gate')
                event_resolutions[row['item_id']]=row
            if row['event']=='forecast_valid' and runner_map is not None:
                value=json_reply(forecast_raw)
                if set(value)!={'race_id','probabilities'} or value['race_id']!=original_task['race_id'] or validate_prediction(value['probabilities'],list(runner_map)):
                    raise ValueError('Committed forecast has invalid model probabilities')
                mapped=dict(race_id=value['race_id'],probabilities={runner_map[k]:v for k,v in value['probabilities'].items()})
                if row['prediction']!=mapped:raise ValueError('Committed forecast differs from model probabilities')
            if row['event']=='model_request':
                model_calls+=1
                messages=row['request']['messages']
                if row['role']!='judge_outcome' and 'confidential_known_winners' in json.dumps(messages):raise ValueError('Judge label leaked into another role')
                payload=json.loads(messages[-1]['content'])
                if row['role']=='event_resolver':resolver_request=payload;resolver_response=None
                if row['role']=='forecaster' and payload!=final_payload:raise ValueError('Actual forecast prompt differs from audited input')
                if row['role']=='selector':
                    for e in payload['candidates']:check_extract(e)
            if row['event']=='judge_panel' and row['allow']:
                if not row['hard']['allow'] or len(row['votes'])!=3 or any(v['verdict']!='allow' for v in row['votes']):raise ValueError('Invalid passage admission')
                if {v['role'] for v in row['votes']}!={'provenance','outcome','relevance'}:raise ValueError('Missing judge role')
                policy=row['hard'].get('policy','strict')
                if manifest.get('research_policy',policy)!=policy:raise ValueError('Judge policy differs from run manifest')
                if policy=='exploratory':
                    for vote in row['votes']:
                        quotes=vote.get('supporting_quotes')
                        if (not isinstance(quotes,list) or not 1<=len(quotes)<=3
                            or any(not isinstance(q,str) or not q.strip() or len(q)>600 or q not in row['text'] for q in quotes)):
                            raise ValueError('Exploratory admission lacks exact supporting quotes')
                if policy=='event-grounded':
                    resolved=event_resolutions.get(row['item_id'])
                    if (not resolved or resolved['text']!=row['text'] or resolved['source_id']!=row['source_id']
                        or not resolved['gate']['allow']):raise ValueError('Admission lacks an allowing event resolution')
                    byid={s['id']:s['text'] for s in resolved['payload']['sentences']}
                    for vote in row['votes']:
                        ids=vote.get('support_ids')
                        if (not isinstance(ids,list) or not 1<=len(ids)<=3 or len(set(ids))!=len(ids)
                            or any(not isinstance(i,str) or i not in byid for i in ids)
                            or vote.get('supporting_quotes')!=[byid[i] for i in ids]):
                            raise ValueError('Grounded admission has altered sentence support')
                if row['source_id'] not in sources:raise ValueError('Missing admitted source receipt')
                approved[row['item_id']]=row
            if row['event']=='selected_evidence':
                for e in row['selected']:
                    check_extract(e)
                    selected[e['sentence_id']]=e
            if row['event']=='final_forecaster_input':
                finals+=1;final_payload=row['payload']
                task=final_payload['task']
                if runner_map is not None:
                    expected=json.loads(json.dumps(original_task))
                    for i,r in enumerate(expected['runners']):r['runner_id']=f'r{i+1}'
                    if task!=expected:raise ValueError('Runner aliases changed forecast task')
                if public_task(task,strict=task.get('track')=='strict')!=task:raise ValueError('Forecast task contains unapproved fields')
                for e in row['payload']['approved_evidence']:
                    if selected.get(e['sentence_id'])!=e:raise ValueError('Unselected or altered evidence reached forecaster')
                    source=sources[e['source_id']]
                    availability_matches=(e['available_at'] is None and source.available_at is None) or (e['available_at'] is not None and source.available_at is not None and utc(e['available_at'])==utc(source.available_at))
                    if not availability_matches or not deterministic_gate(source,e['paragraph_context'],task['cutoff_utc'],approved[e['item_id']]['hard'].get('policy','strict'))['allow']:
                        raise ValueError('Admitted source fails provenance recheck')
                    if e['available_at'] is not None and utc(e['available_at'])>utc(row['payload']['task']['cutoff_utc']):raise ValueError('Post-cutoff evidence reached forecaster')
        checks.append(dict(ledger=relative,hash_chain=True,model_calls=model_calls,final_inputs=finals,admitted_passages=len(approved)))
    report=dict(ledgers=checks,checked=len(checks),status='passed',limitations='Prompt/data-flow audit, not OS sandboxing or proof that judges never miss implicit leakage')
    (out/'audit_report.json').write_text(json.dumps(report,indent=2)+'\n');return report
