#!/usr/bin/env python3
"""Bounded local extraction component test. Never reads target results/odds."""
import argparse
import asyncio
from collections import Counter
from datetime import datetime,timezone
import fcntl
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
import requests
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from horse_racing.shared_forecast import write_json,digest,SYSTEM_ROOT
from horse_racing.article_features import candidates_for,extract_article,normalized_name
from forecast_system import JsonlTrace
from forecast_system.ollama import OllamaClient
API='http://127.0.0.1:11440';MODEL='llama3.1:8b'


def now():return datetime.now(timezone.utc).isoformat()
def read(p):return json.loads(p.read_text())


def prepare(out):
    out.mkdir(parents=True,exist_ok=False);source=ROOT/'runs/agent_features_20261111_v2/public'
    packets=read(source/'packets.json');sources=read(source/'sources.json');tasks=[]
    for p in packets:
        for r in p['runners']:
            tasks.append(dict(race={k:p[k] for k in ['race_id','date','venue','cutoff_utc']},
                runner={k:r[k] for k in ['runner_id','horse_name']},candidates=candidates_for(p,r,sources)))
    assert len({t['runner']['runner_id'] for t in tasks})==len(tasks)
    eligible=sum(bool(t['candidates']) for t in tasks)
    if eligible>40:raise ValueError('Component inference budget exceeded')
    # Source-reviewed development references authored by the coding assistant.
    # This is NOT independent human annotation or an unseen generalization set.
    jan=['SOMETHING','IFACH','JUSTCALLMESERGIO','SOFUNNY','PARTY ZONE','LUNA ROSSA','PASAPALABRA','AFRICAN STAR','WHITE BAY','FLIGHT LEADER']
    feb=['DUKES OF HAATHER','IMONFIRE','XMAS','MUSIC HISTORY','FIJI GOLD','SOUND OF FREEDOM','BORN TO BRIGHT','ROMEO','HAYA TAAL']
    refs=[]
    specifications=[('2026-01-11',n,'selected') for n in jan]+[('2026-02-01',n,'selected') for n in feb]
    specifications += [('2026-02-01',n,'opposed') for n in ['JUDGE ME NOT','NUMBER','SOMETHING']]
    specifications += [('2026-02-01',n,'unknown') for n in ['SHUTTERWOOD','BE TRUE','SIR GEOFF MORGAN']]+[('2026-01-11','SHAMRAN','unknown')]
    for day,name,expected in specifications:
        matches=[t for t in tasks if t['race']['date']==day and normalized_name(t['runner']['horse_name'])==normalized_name(name)]
        if len(matches)!=1:raise ValueError('Ambiguous reference identity '+name)
        t=matches[0];c=t['candidates']
        if expected!='unknown' and not c:raise ValueError('Reference has no eligible source')
        # Final numbered picks are clearest for February positive references.
        cited=next((s for s in c if s['id']=='feb1_preview:9'),c[0] if c else None) if expected!='unknown' else None
        refs.append(dict(runner_id=t['runner']['runner_id'],horse=t['runner']['horse_name'],date=day,
            expected=expected,source_id=cited['id'] if cited else None,source_quote=cited['text'] if cited else '',
            reviewer='coding_assistant_source_review; independent human review pending'))
    write_json(out/'tasks.json',tasks);write_json(out/'references.json',refs)
    code=[Path(__file__).resolve(),ROOT/'horse_racing/article_features.py',ROOT/'horse_racing/shared_forecast/__init__.py']+list((SYSTEM_ROOT/'forecast_system').glob('*.py'))
    write_json(out/'manifest.json',dict(created_at=now(),input_hashes={str(p):digest(p) for p in [source/'packets.json',source/'sources.json',out/'tasks.json',out/'references.json']},
        code_hashes={str(p):digest(p) for p in code},model=MODEL,gpu=3,api=API,runner_rows=len(tasks),eligible_model_calls=eligible,
        maximum_model_calls=40,call_timeout=90,max_output_tokens=256,reference_rows=len(refs),
        scope='Controlled-source article recommendation extraction; no shared-engine retrieval run, no outcomes/odds as inputs.',
        reference_caveat='Assistant-reviewed development references selected before this inference run; not independent human annotation. Existing development outcomes were previously exposed but were not consulted to select claims.',
        no_source='Unknown without inference; missing news does not imply neutral or adverse publisher opinion',
        publication='PROHIBITED. All artifacts local. No website export or deployment.'))
    write_json(out/'status.json',dict(status='prepared',planned=len(tasks),eligible_calls=eligible))
    print(json.dumps(dict(runners=len(tasks),eligible_calls=eligible,references=len(refs))))


def summarize(out):
    tasks=read(out/'tasks.json');refs=read(out/'references.json');results={}
    for t in tasks:
        f=out/'runners'/(t['runner']['runner_id']+'.json')
        if f.exists():results[t['runner']['runner_id']]=read(f)
    scored=[]
    for ref in refs:
        r=results.get(ref['runner_id'])
        if r is not None:scored.append(dict(**ref,predicted=r.get('assessment'),status=r['status'],correct=r.get('assessment')==ref['expected']))
    report=dict(processed=len(results),planned=len(tasks),statuses=dict(Counter(r['status'] for r in results.values())),
        assessments=dict(Counter(r.get('assessment','failed') for r in results.values())),
        model_calls=sum(r.get('model_calls',0) for r in results.values()),reference_scored=len(scored),reference_expected=len(refs),
        reference_accuracy=sum(r['correct'] for r in scored)/len(scored) if scored else None,
        reference_rows=scored,updated_at=now(),caveat='Selected assistant-reviewed development cases; not independent extraction precision or generalization evidence.')
    write_json(out/'extraction_summary.json',report)
    return report


def run(out,extractor=extract_article):
    lock=(out/'run.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    manifest=read(out/'manifest.json');tasks=read(out/'tasks.json')
    for p,h in {**manifest['input_hashes'],**manifest['code_hashes']}.items():
        if digest(p)!=h:raise ValueError('Frozen input/code drift: '+p)
    uuid,used=[s.strip() for s in subprocess.check_output(['nvidia-smi','--id=3','--query-gpu=uuid,memory.used','--format=csv,noheader,nounits'],text=True).strip().split(',')]
    if int(used)>100:raise RuntimeError('GPU 3 is occupied')
    sock=socket.socket();sock.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1);sock.bind(('127.0.0.1',11440));sock.close()
    env={**os.environ,'CUDA_VISIBLE_DEVICES':uuid,'OLLAMA_HOST':'127.0.0.1:11440','OLLAMA_MODELS':'/app/.local/ollama/models','OLLAMA_NUM_PARALLEL':'1','OLLAMA_MAX_LOADED_MODELS':'1'}
    logfile=(out/'ollama.log').open('a');service=subprocess.Popen(['/app/.local/ollama/bin/ollama','serve'],env=env,stdin=subprocess.DEVNULL,stdout=logfile,stderr=subprocess.STDOUT,start_new_session=True)
    stop=[];signal.signal(signal.SIGTERM,lambda *_:stop.append(True))
    status=dict(status='starting',controller_pid=os.getpid(),service_pid=service.pid,gpu=3,gpu_uuid=uuid,planned=len(tasks),updated_at=now())
    write_json(out/'status.json',status)
    try:
        for _ in range(60):
            if service.poll() is not None:raise RuntimeError('Owned service exited')
            try:response=requests.get(API+'/api/tags',timeout=2);response.raise_for_status();tags=response.json()['models'];break
            except requests.RequestException:time.sleep(1)
        else:raise RuntimeError('Model service unavailable')
        model=next((m for m in tags if m['name']==MODEL),None)
        if model is None:raise RuntimeError('Installed model missing; downloading forbidden')
        write_json(out/'runtime.json',dict(model=model,gpu_uuid=uuid,api=API))
        for t in tasks:
            if stop:status['status']='stopped';break
            for p,h in manifest['code_hashes'].items():
                if digest(p)!=h:raise ValueError('Source code drift')
            rid=t['runner']['runner_id'];f=out/'runners'/(rid+'.json')
            if f.exists():continue
            trace=JsonlTrace(out/'traces'/(rid+'.jsonl'))
            client=OllamaClient(MODEL,api=API,timeout=90,context=8192,trace=trace)
            try:record=asyncio.run(extractor(client,t['race'],t['runner'],t['candidates'],trace))
            except Exception as exc:record=dict(status='failed',error=repr(exc),model_calls=1)
            write_json(f,dict(runner_id=rid,race_id=t['race']['race_id'],**record,finished_at=now()))
            status.update(status='running',current_horse=t['runner']['horse_name'],updated_at=now())
            report=summarize(out);status['processed']=report['processed'];write_json(out/'status.json',status)
        else:status['status']='completed'
    except BaseException as exc:status.update(status='error',error=repr(exc));raise
    finally:
        if service.poll() is None:
            os.killpg(service.pid,signal.SIGTERM)
            try:service.wait(timeout=15)
            except subprocess.TimeoutExpired:os.killpg(service.pid,signal.SIGKILL);service.wait()
        summarize(out);status.update(service_stopped=True,updated_at=now());write_json(out/'status.json',status)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--prepare',action='store_true');a=p.parse_args()
    if a.prepare:prepare(a.out.resolve())
    else:run(a.out.resolve())
