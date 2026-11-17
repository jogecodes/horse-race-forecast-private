#!/usr/bin/env python3
"""Shared research API -> grounded racing features; sequential GPU 3 worker."""
import argparse
import asyncio
from dataclasses import asdict
from datetime import datetime,timezone
import fcntl
import json
import os
from pathlib import Path
import signal
import socket
import sqlite3
import subprocess
import sys
import time
from bs4 import BeautifulSoup
import requests

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from horse_racing.shared_forecast import SYSTEM_ROOT,write_json,digest
from horse_racing.agent_features import extract
from forecast_system import ForecastSystem,ResearchRequest,Source,HistoricalEnvironment,RunConfig,JsonlTrace
from forecast_system.ollama import OllamaClient

API='http://127.0.0.1:11440';MODEL='llama3.1:8b'
CONFIG=RunConfig(research_rounds=1,tasks_per_round=2,max_queries=2,max_sources=4,
    fetches_per_task=2,search_hits_per_task=4,max_source_chars=1800,max_model_calls=12)


def now():return datetime.now(timezone.utc).isoformat()


def source_paths():
    return list((SYSTEM_ROOT/'forecast_system').glob('*.py'))+[Path(__file__).resolve(),
        ROOT/'horse_racing/agent_features.py',ROOT/'horse_racing/forecast_comparison.py',
        ROOT/'horse_racing/statistical.py',ROOT/'horse_racing/shared_forecast/__init__.py',
        ROOT/'scripts/evaluate_agent_features.py']


def prepare(out):
    out.mkdir(parents=True,exist_ok=False);bundle=ROOT/'benchmarks/h1_2026_v2'
    tasks=[json.loads(l) for l in (bundle/'diagnostic/tasks.jsonl').read_text().splitlines()]
    paths=[bundle/'diagnostic/packets'/(t['race_id']+'.json') for t in tasks if t['split']=='development']
    packets=sorted((json.loads(p.read_text()) for p in paths),key=lambda p:(p['date'],p['race_id']))
    inputs=paths+[bundle/'supervisor/labels.jsonl',bundle/'supervisor/cases.jsonl',ROOT/'data/racing.sqlite',
        ROOT/'data/declarations_h1_2026.sqlite',ROOT/'runs/statistical_baselines_20261111/linear_race_calibrated_predictions.jsonl']
    write_json(out/'public/packets.json',packets)
    base=[json.loads(l) for l in inputs[-1].read_text().splitlines()]
    write_json(out/'public/baseline_predictions.json',base)
    sources=[];omissions=[]
    specs=[('prior_november',None,'2025-11-16'),('jan11_preview','2026-01-11',None),('feb1_preview','2026-02-01',None)]
    for name,target,past in specs:
        file=ROOT/'data/semantic_leakage_review_v1'/(name+'.json');inputs.append(file)
        d=json.loads(file.read_text());claims=d['date_claims'];extra={}
        if name=='jan11_preview':
            cached=ROOT/'data/semantic_leakage_review_v1/cache/32f12cd33ca74244d906c0f609a812fa.json'
            raw=json.loads(cached.read_text());text=BeautifulSoup(raw['text'],'html.parser').get_text(' ',strip=True)
            assert raw['url']==d['url'] and 'viernes, 9 de enero de 2026' in text
            claims=[dict(kind='published',value='2026-01-09T22:59:59.999999+00:00',
                path='preserved visible publisher date: viernes, 9 de enero de 2026',precision='local_day_upper_bound')]
            extra=dict(supplemental_date_receipt=str(cached),receipt_sha256=digest(cached));inputs.append(cached)
        if not claims:omissions.append(dict(source=name,reason='undated'));continue
        available=max(c['value'] for c in claims)
        for i,paragraph in enumerate(d['paragraphs']):
            if not paragraph.strip():continue
            if len(paragraph)>CONFIG.max_source_chars:omissions.append(dict(source=name,paragraph=i,reason='oversized'));continue
            meta=dict(source_type='publisher_article',target_event_date=target,historical_event_date=past,
                url=d['url'],body_sha256=d['body_sha256'],observed_at=d['observed_at'],claims=claims,
                paragraph_index=i,context='Complete extracted article paragraph; title from preserved source metadata',
                availability_assumption='Publisher-dated retrospective source, not independently archived bytes',**extra)
            sources.append(Source(id=name+':'+str(i),title=d['metadata']['title']+' [paragraph '+str(i)+']',
                text=paragraph,url=d['url'],available_at=available,kind='archive',provenance=json.dumps(meta,ensure_ascii=False)))
    write_json(out/'public/sources.json',[asdict(s) for s in sources]);write_json(out/'public/source_omissions.json',omissions)
    write_json(out/'evaluation_inputs/verified_closing_markets.json',{})
    code={str(p):digest(p) for p in source_paths()}
    for p in source_paths():
        target=out/'source'/('upstream' if p.is_relative_to(SYSTEM_ROOT) else 'study')/p.name
        target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(p.read_bytes())
    inputs+=list((out/'public').glob('*.json'))+[out/'evaluation_inputs/verified_closing_markets.json']
    manifest=dict(created_at=now(),code_hashes=code,input_hashes={str(p):digest(p) for p in inputs},
        model=MODEL,gpu=3,api=API,research_config=asdict(CONFIG),cases=len(packets),corpus_sources=len(sources),
        extractor_token_budget=4096,extractor_calls_per_case=1,case_timeout=900,
        evaluation='January 20 races fit new offset weights; February 28 races evaluation. Fixed ridge 1.0; no February tuning.',
        controls='Existing frozen baseline; deterministic literal-form control; research+agent extraction.',
        strict_historical_validity=False,actual_input_cutoff='Existing day-before publisher-documented inputs, not T-60 snapshots',
        outcome_boundary='Labels and closing-market data are evaluator-only; worker reads only public packets/corpus',
        closing_benchmark='Verified closing set empty; reported result-price proxy scored separately and never relabeled verified',
        lifecycle='Run all cases, checkpoint failures, no calendar stop; stop on source drift; no automatic retries/downloads')
    write_json(out/'manifest.json',manifest);write_json(out/'status.json',dict(status='prepared',planned=len(packets),completed=0))
    print(json.dumps(dict(out=str(out),cases=len(packets),sources=len(sources))))


def worker(out,index):
    packet=json.loads((out/'public/packets.json').read_text())[index];dest=out/'cases'/packet['race_id']
    if (dest/'result.json').exists():raise FileExistsError('Attempt already exists')
    dest.mkdir(parents=True,exist_ok=False)
    trace=JsonlTrace(dest/'trace.jsonl');client=OllamaClient(MODEL,api=API,timeout=180,trace=trace)
    env=HistoricalEnvironment([Source(**s) for s in json.loads((out/'public/sources.json').read_text())],as_of=packet['cutoff_utc'])
    request=ResearchRequest(id=packet['race_id'],target='Pre-race evidence for declared horses at '+packet['venue']+' on '+packet['date'],
        forecast_time=packet['cutoff_utc'],context=json.dumps(dict(date=packet['date'],venue=packet['venue'],runners=[r['horse_name'] for r in packet['runners']]),ensure_ascii=False),
        information_needs=(f'Find publisher preview opinions explicitly about the horses in the target race on {packet["date"]}.',
            'Find explicit trouble-in-running reports about these horses in earlier races. Missing facts must remain unknown.'))
    try:
        research=asyncio.run(ForecastSystem(client,env,config=CONFIG,trace=trace).research(request))
        write_json(dest/'research.json',asdict(research))
        result=asyncio.run(extract(client,packet,research,trace))
        write_json(dest/'result.json',dict(status='complete',race_id=packet['race_id'],**result,
            research_evidence=len(research.evidence),research_usage=asdict(research.usage),finished_at=now()))
    except Exception as exc:
        write_json(dest/'result.json',dict(status='failed',race_id=packet['race_id'],error=repr(exc),finished_at=now()))
        raise


def run(out,smoke=False):
    lock=(out/'run.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    manifest=json.loads((out/'manifest.json').read_text());packets=json.loads((out/'public/packets.json').read_text())
    def drift(hashes):return [p for p,h in hashes.items() if not Path(p).exists() or digest(p)!=h]
    if drift({**manifest['code_hashes'],**manifest['input_hashes']}):raise RuntimeError('Frozen sources/inputs changed')
    uuid,memory=[x.strip() for x in subprocess.check_output(['nvidia-smi','--id=3','--query-gpu=uuid,memory.used','--format=csv,noheader,nounits'],text=True).strip().split(',')]
    if int(memory)>100:raise RuntimeError('GPU 3 occupied')
    sock=socket.socket();sock.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);sock.bind(('127.0.0.1',11440));sock.close()
    env={**os.environ,'CUDA_VISIBLE_DEVICES':uuid,'OLLAMA_HOST':'127.0.0.1:11440','OLLAMA_MODELS':'/app/.local/ollama/models',
        'OLLAMA_NUM_PARALLEL':'1','OLLAMA_MAX_LOADED_MODELS':'1','OLLAMA_KEEP_ALIVE':'15m'}
    log=(out/'ollama.log').open('a');service=subprocess.Popen(['/app/.local/ollama/bin/ollama','serve'],env=env,
        stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    stop=[];signal.signal(signal.SIGTERM,lambda *_:stop.append(True));signal.signal(signal.SIGINT,lambda *_:stop.append(True))
    state=dict(status='starting',controller_pid=os.getpid(),service_pid=service.pid,gpu=3,gpu_uuid=uuid,api=API,planned=len(packets),updated_at=now())
    write_json(out/'status.json',state);reason='completed'
    evaluator=[sys.executable,str(ROOT/'scripts/evaluate_agent_features.py'),'--out',str(out)]
    try:
        for _ in range(60):
            if service.poll() is not None:raise RuntimeError('Owned model service exited')
            try:
                response=requests.get(API+'/api/tags',timeout=2);response.raise_for_status();tags=response.json()['models'];break
            except requests.RequestException:time.sleep(1)
        else:raise RuntimeError('Service unavailable')
        installed={m['name']:m for m in tags}
        if MODEL not in installed:raise RuntimeError('Model missing; downloads forbidden')
        write_json(out/'runtime.json',dict(model=installed[MODEL],gpu_uuid=uuid,controller_pid=os.getpid(),service_pid=service.pid))
        for i,p in enumerate(packets):
            if smoke and i>0:break
            if stop:reason='requested_stop';break
            if drift(manifest['code_hashes']):reason='source_changed';break
            dest=out/'cases'/p['race_id']
            if (dest/'result.json').exists():continue
            if dest.exists():reason='incomplete_attempt_requires_review';break
            state.update(status='running',current_race=p['race_id'],completed=sum((out/'cases'/r['race_id']/'result.json').exists() for r in packets),updated_at=now())
            write_json(out/'status.json',state)
            with (out/('worker_'+str(i)+'.log')).open('a') as workerlog:
                try:
                    subprocess.run([sys.executable,str(Path(__file__).resolve()),'--out',str(out),'--worker',str(i)],
                        stdin=subprocess.DEVNULL,stdout=workerlog,stderr=subprocess.STDOUT,timeout=manifest['case_timeout'])
                except subprocess.TimeoutExpired:
                    write_json(dest/'result.json',dict(status='failed',race_id=p['race_id'],error='case_timeout',finished_at=now()))
            if not (dest/'result.json').exists():write_json(dest/'result.json',dict(status='failed',race_id=p['race_id'],error='worker_missing_result',finished_at=now()))
            if (i+1)%6==0:subprocess.run(evaluator,check=True,stdout=subprocess.DEVNULL,env={**os.environ,'OPENBLAS_NUM_THREADS':'1'})
        state.update(status='smoke_completed' if smoke and reason=='completed' else reason,updated_at=now())
    except BaseException as exc:
        state.update(status='controller_error',error=repr(exc),updated_at=now());raise
    finally:
        if service.poll() is None:
            os.killpg(service.pid,signal.SIGTERM)
            try:service.wait(timeout=15)
            except subprocess.TimeoutExpired:os.killpg(service.pid,signal.SIGKILL);service.wait()
        state.update(service_stopped=True,completed=sum((out/'cases'/r['race_id']/'result.json').exists() for r in packets),input_drift=drift(manifest['input_hashes']))
        result=subprocess.run(evaluator,stdout=subprocess.DEVNULL,env={**os.environ,'OPENBLAS_NUM_THREADS':'1'})
        state['evaluation_exit_code']=result.returncode;write_json(out/'status.json',state)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',required=True,type=Path);parser.add_argument('--prepare',action='store_true');parser.add_argument('--smoke',action='store_true');parser.add_argument('--worker',type=int)
    args=parser.parse_args();out=args.out.resolve()
    if args.prepare:prepare(out)
    elif args.worker is not None:worker(out,args.worker)
    else:run(out,args.smoke)
