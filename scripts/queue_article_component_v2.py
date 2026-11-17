#!/usr/bin/env python3
"""Wait for GPU 3; gate extraction quality before optional local scoring."""
import argparse
from collections import Counter
from datetime import datetime,timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


def read(p):return json.loads(p.read_text())
def now():return datetime.now(timezone.utc).isoformat()
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write_json(p,value):
    p.parent.mkdir(parents=True,exist_ok=True);temporary=p.with_suffix('.tmp')
    temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n');temporary.replace(p)


def quality_gate(out):
    manifest=read(out/'manifest.json');summary=read(out/'extraction_summary.json')
    rows=summary['reference_rows'];policy=manifest['quality_gate']
    critical=[r for r in rows if r['date']=='2026-02-01' and r['horse'] in ['SHUTTERWOOD (FR)','BE TRUE (FR)']]
    if len(critical)!=2:raise ValueError('Missing critical reference cases')
    correct_opposed=sum(r['correct'] and r['expected']=='opposed' and r['date']<'2026-02-01' for r in rows)
    checks=dict(all_references_scored=summary['reference_scored']==summary['reference_expected'],
        reference_accuracy=summary['reference_accuracy']>=policy['minimum_reference_accuracy'],
        no_critical_false_recommendations=sum(not r['correct'] for r in critical)<=policy['critical_false_current_recommendations'],
        no_failed_extractions=summary['statuses'].get('failed',0)<=policy['maximum_schema_failures'],
        january_opposition_supported=correct_opposed>=policy['minimum_correct_january_opposed_references'])
    tasks=read(out/'tasks.json');training=Counter()
    for t in tasks:
        if t['race']['date']<'2026-02-01':
            r=read(out/'runners'/(t['runner']['runner_id']+'.json'));training[r.get('assessment','failed')]+=1
    groups={}
    for group in ['existing_regression','additional_source_review']:
        subset=[r for r in rows if r.get('reference_group')==group]
        groups[group]=dict(cases=len(subset),correct=sum(r['correct'] for r in subset))
    report=dict(passed=all(checks.values()),checks=checks,reference_accuracy=summary['reference_accuracy'],groups=groups,
        correct_january_opposed_references=correct_opposed,training_assessments=dict(training),
        incorrect_references=[r for r in rows if not r['correct']],
        policy=policy,caveat='Assistant-reviewed, selected development source cases; not independent human validation.',updated_at=now())
    write_json(out/'quality_gate.json',report);return report


def main(out,evaluation):
    lock=(out/'queue.lock').open('a');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    if evaluation.exists():raise FileExistsError('Evaluation path already exists')
    manifest=read(out/'manifest.json');stop=[]
    signal.signal(signal.SIGTERM,lambda *_:stop.append(True))
    state=dict(status='waiting_for_gpu3',queue_pid=os.getpid(),component_run=str(out),evaluation_out=str(evaluation),
        publication='PROHIBITED',poll_seconds=30,calendar_stop=None,updated_at=now())
    try:
        while not stop:
            for p,h in {**manifest['code_hashes'],**manifest['input_hashes']}.items():
                if digest(p)!=h:raise RuntimeError('Frozen source/input drift: '+p)
            used=int(subprocess.check_output(['nvidia-smi','--id=3','--query-gpu=memory.used','--format=csv,noheader,nounits'],text=True).strip())
            port_free=True;sock=socket.socket()
            try:sock.bind(('127.0.0.1',11440))
            except OSError:port_free=False
            finally:sock.close()
            state.update(gpu3_memory_mib=used,model_port_free=port_free,updated_at=now())
            write_json(out/'queue_status.json',state)
            if used<=100 and port_free:break
            time.sleep(30)
        if stop:state['status']='stopped_before_inference';return
        state.update(status='extracting',updated_at=now());write_json(out/'queue_status.json',state)
        with (out/'worker_controller.log').open('a') as log:
            child=subprocess.Popen([sys.executable,str(ROOT/'scripts/run_article_component_v2.py'),'--out',str(out)],
                stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT)
            state['worker_controller_pid']=child.pid;write_json(out/'queue_status.json',state)
            while child.poll() is None:
                if stop:child.terminate();child.wait();break
                time.sleep(1)
            if child.returncode!=0:raise RuntimeError('Component controller failed; inspect preserved logs')
        status=read(out/'status.json')
        if status['status']!='completed':state['status']='extraction_stopped';return
        gate=quality_gate(out)
        if not gate['passed']:state['status']='completed_quality_gate_failed';return
        if stop:state['status']='stopped_before_outcome_evaluation';return
        state.update(status='evaluating_fixed_protocol',updated_at=now());write_json(out/'queue_status.json',state)
        with (out/'evaluation.log').open('a') as log:
            subprocess.run([sys.executable,str(ROOT/'scripts/evaluate_article_component.py'),'--component',str(out),'--out',str(evaluation)],
                check=True,stdout=log,stderr=subprocess.STDOUT,env={**os.environ,'OPENBLAS_NUM_THREADS':'1'})
        state['status']='completed_and_evaluated'
    except BaseException as exc:state.update(status='error',error=repr(exc));raise
    finally:state['updated_at']=now();write_json(out/'queue_status.json',state)


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--evaluation-out',type=Path,required=True);a=p.parse_args()
    main(a.out.resolve(),a.evaluation_out.resolve())
