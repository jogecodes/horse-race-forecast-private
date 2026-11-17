#!/usr/bin/env python3
"""Study-owned weekend lifecycle. Imports, never installs/copies, the sibling engine."""
from __future__ import annotations
import argparse
import asyncio
from dataclasses import asdict
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from horse_racing.shared_forecast import (SYSTEM_ROOT, declaration_sources, digest,
    environment_for, public_packet, question_for, write_json)
from forecast_system import ForecastSystem, JsonlTrace, RunConfig, Source
from forecast_system.ollama import OllamaClient
import requests

BUNDLE = ROOT / 'benchmarks/h1_2026_v2'
CONFIG = RunConfig()
MODELS = ('llama3.1:8b', 'gemma3:4b')


def now():
    return datetime.now(timezone.utc).isoformat()


def code_paths():
    return sorted((SYSTEM_ROOT / 'forecast_system').glob('*.py')) + [
        ROOT / 'horse_racing/shared_forecast/__init__.py', Path(__file__).resolve(),
        ROOT / 'scripts/score_shared_weekend.py']


def prepare(out):
    out.mkdir(parents=True, exist_ok=False)
    packets = []
    for task in (BUNDLE / 'diagnostic/tasks.jsonl').read_text().splitlines():
        task = json.loads(task)
        if task['split'] == 'development':
            packet = json.loads((BUNDLE / 'diagnostic/packets' / (task['race_id']+'.json')).read_text())
            packets.append(public_packet(packet))
    packets.sort(key=lambda p: (p['date'], p['race_id']))
    # Twelve evenly spaced chronological development races, chosen without outcomes.
    selected = [packets[round(i*(len(packets)-1)/11)] for i in range(12)]
    sources = declaration_sources(ROOT / 'data/declarations_h1_2026.sqlite')
    write_json(out / 'public/packets.json', selected)
    write_json(out / 'public/sources.json', [asdict(s) for s in sources])
    cases = []
    for seed in (0, 1):
        for packet in selected:
            for model in MODELS:
                for runner in packet['runners']:
                    for arm in ('declaration_only', 'declaration_research'):
                        cases.append(dict(case_id=f'case_{len(cases):05d}',
                            race_id=packet['race_id'], runner_id=runner['runner_id'],
                            field_size=len(packet['runners']), model=model, seed=seed, arm=arm))
    write_json(out / 'public/cases.json', cases)
    hashes = {str(p): digest(p) for p in code_paths()}
    # Source snapshots document exact bytes; execution still imports the sibling.
    for p in code_paths():
        target = out / 'source_snapshot' / ('upstream' if p.is_relative_to(SYSTEM_ROOT) else 'study') / p.name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(p.read_bytes())
    inputs = [BUNDLE/'manifest.json', BUNDLE/'protocol.json', BUNDLE/'diagnostic/tasks.jsonl',
              BUNDLE/'supervisor/labels.jsonl', ROOT/'data/declarations_h1_2026.sqlite',
              ROOT/'data/racing.sqlite']
    inputs += [BUNDLE/'diagnostic/packets'/(p['race_id']+'.json') for p in selected]
    inputs += sorted((out/'public').glob('*.json'))
    manifest = dict(created_at=now(), engine_root=str(SYSTEM_ROOT), code_hashes=hashes,
        input_hashes={str(p): digest(p) for p in inputs}, config=asdict(CONFIG),
        python=sys.executable, models=list(MODELS), seeds=[0,1], gpu=3, api='http://127.0.0.1:11439',
        deadline_utc=None, case_timeout_seconds=900,
        selection='12 evenly spaced indices of chronological 48-race development list; no outcome selection',
        race_ids=[p['race_id'] for p in selected], cases=len(cases),
        assumptions=['Publisher-documented availability, not certified historical captures',
            'Binary official-winner events; dead heats count YES for each winner',
            'Independent binary outputs are never normalized into race distributions',
            'Same full current declaration in both arms; research adds searchable declarations',
            'No internet, market odds, paid models, downloads, or held-out questions',
            'Models share roles; fresh contexts do not prove statistical independence'])
    write_json(out/'manifest.json', manifest)
    write_json(out/'status.json', dict(status='prepared', planned=len(cases), completed=0, updated_at=now()))
    print(json.dumps(dict(out=str(out), cases=len(cases), races=len(selected), sources=len(sources))))


def worker(out, index, attempt):
    case = json.loads((out/'public/cases.json').read_text())[index]
    packet = next(p for p in json.loads((out/'public/packets.json').read_text()) if p['race_id']==case['race_id'])
    source_rows = json.loads((out/'public/sources.json').read_text())
    sources = [Source(**s) for s in source_rows]
    trace = JsonlTrace(attempt/'trace.jsonl')
    client = OllamaClient(case['model'], api='http://127.0.0.1:11439', seed=case['seed'], trace=trace)
    environment = environment_for(sources, packet['cutoff_utc'], case['arm'])
    try:
        result = asyncio.run(ForecastSystem(client, environment, config=CONFIG, trace=trace).forecast(
            question_for(packet, case['runner_id'])))
        write_json(attempt/'result.json', dict(case=case, result=asdict(result), finished_at=now()))
    except Exception as exc:
        write_json(attempt/'result.json', dict(case=case, error=repr(exc), probability=None, finished_at=now()))
        raise


def changed(hashes):
    return [p for p, sha in hashes.items() if not Path(p).exists() or digest(p)!=sha]


def run(out, smoke=False):
    lock = (out/'run.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    manifest = json.loads((out/'manifest.json').read_text())
    drift = changed({**manifest['code_hashes'], **manifest['input_hashes']})
    if drift:
        raise RuntimeError(f'Frozen code/input changed: {drift}')
    deadline = (datetime.fromisoformat(manifest['deadline_utc']).timestamp()
                if manifest['deadline_utc'] is not None else float('inf'))
    if time.time() >= deadline:
        raise RuntimeError('Experiment deadline already passed')
    cases = json.loads((out/'public/cases.json').read_text())
    gpu = subprocess.check_output(['nvidia-smi','--id=3','--query-gpu=uuid,memory.used',
                                  '--format=csv,noheader,nounits'], text=True).strip()
    uuid, memory = [v.strip() for v in gpu.split(',')]
    if int(memory)>100:
        raise RuntimeError('GPU 3 is occupied; refusing to compete')
    sock = socket.socket()
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(('127.0.0.1',11439))
    sock.close()
    service_env = {**os.environ, 'CUDA_VISIBLE_DEVICES':uuid,
        'OLLAMA_HOST':'127.0.0.1:11439', 'OLLAMA_MODELS':'/app/.local/ollama/models',
        'OLLAMA_NUM_PARALLEL':'1', 'OLLAMA_MAX_LOADED_MODELS':'1', 'OLLAMA_KEEP_ALIVE':'15m'}
    service_log = (out/'ollama.log').open('a')
    service = subprocess.Popen(['/app/.local/ollama/bin/ollama','serve'], env=service_env,
        stdin=subprocess.DEVNULL, stdout=service_log, stderr=subprocess.STDOUT, start_new_session=True)
    stop = []
    signal.signal(signal.SIGTERM, lambda *_: stop.append('requested_stop'))
    signal.signal(signal.SIGINT, lambda *_: stop.append('requested_stop'))
    state = dict(status='starting_service', controller_pid=os.getpid(), service_pid=service.pid,
                 gpu=3, gpu_uuid=uuid, api=manifest['api'], planned=len(cases), updated_at=now())
    write_json(out/'status.json', state)
    reason = 'completed'
    try:
        for _ in range(60):
            if service.poll() is not None:
                raise RuntimeError('Dedicated Ollama service exited')
            try:
                response = requests.get(manifest['api']+'/api/tags',timeout=2)
                response.raise_for_status()
                tags = response.json()['models']
                break
            except requests.RequestException:
                time.sleep(1)
        else:
            raise RuntimeError('Dedicated service not ready')
        installed = {m['name']:m for m in tags}
        if any(m not in installed for m in MODELS):
            raise RuntimeError('Required local models missing; no downloads allowed')
        write_json(out/'runtime.json', dict(gpu_uuid=uuid, models={m:installed[m] for m in MODELS},
                   service_pid=service.pid, controller_pid=os.getpid(), started_at=now()))
        for i, case in enumerate(cases):
            if smoke:
                first_gemma = next(j for j,c in enumerate(cases) if c['model']=='gemma3:4b')
                if i not in {0,1,first_gemma,first_gemma+1}:
                    continue
            if stop or time.time() >= deadline:
                reason = stop[0] if stop else 'deadline_reached'
                break
            drift = changed(manifest['code_hashes'])
            if drift:
                reason = 'source_changed'
                state['changed_paths'] = drift
                break
            case_dir = out/'cases'/case['case_id']
            if (case_dir/'outcome.json').exists():
                continue
            attempt = case_dir/f'attempt_{len(list(case_dir.glob("attempt_*")))+1:03d}'
            attempt.mkdir(parents=True)
            state.update(status='running', current=case, completed=sum(
                (out/'cases'/c['case_id']/'outcome.json').exists() for c in cases), updated_at=now())
            write_json(out/'status.json',state)
            with (attempt/'worker.log').open('a') as log:
                try:
                    proc = subprocess.run([sys.executable, str(Path(__file__).resolve()),
                        '--out',str(out),'--worker',str(i),'--attempt',str(attempt)],
                        stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                        timeout=min(manifest['case_timeout_seconds'], max(1,deadline-time.time())))
                    error = None if proc.returncode==0 else f'worker_exit_{proc.returncode}'
                except subprocess.TimeoutExpired:
                    error = 'case_timeout'
            result_path = attempt/'result.json'
            result = json.loads(result_path.read_text()) if result_path.exists() else dict(
                case=case, error=error or 'missing_result', probability=None)
            if error:
                result['worker_error'] = error
            write_json(case_dir/'outcome.json', result)
            # Recompute evaluator-only reports in a separate process after each race block.
            if i==len(cases)-1 or cases[i+1]['race_id']!=case['race_id']:
                subprocess.run([sys.executable,str(ROOT/'scripts/score_shared_weekend.py'),'--out',str(out)],check=True)
        state.update(status=reason, completed=sum((out/'cases'/c['case_id']/'outcome.json').exists()
                     for c in cases), updated_at=now())
        if smoke and reason=='completed':
            state['status']='smoke_completed'
    except BaseException as exc:
        state.update(status='controller_error', error=repr(exc), updated_at=now())
        raise
    finally:
        if service.poll() is None:
            os.killpg(service.pid, signal.SIGTERM)
            try:
                service.wait(timeout=15)
            except subprocess.TimeoutExpired:
                os.killpg(service.pid, signal.SIGKILL)
                service.wait()
        state['service_stopped'] = True
        state['input_drift'] = changed(manifest['input_hashes'])
        write_json(out/'status.json',state)
        subprocess.run([sys.executable,str(ROOT/'scripts/score_shared_weekend.py'),'--out',str(out)],check=False)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--prepare', action='store_true')
    parser.add_argument('--smoke', action='store_true')
    parser.add_argument('--worker', type=int)
    parser.add_argument('--attempt', type=Path)
    args = parser.parse_args()
    out = args.out.resolve()
    if args.prepare:
        prepare(out)
    elif args.worker is not None:
        worker(out,args.worker,args.attempt)
    else:
        run(out,smoke=args.smoke)
