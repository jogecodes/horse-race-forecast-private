"""Deterministic time gate; independent judge votes can only further restrict it."""
from __future__ import annotations
import hashlib
import json
import sqlite3
from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from .db import insert, now, uid, utc

POLICY = 'observed-before-cutoff-unanimous-v1'


def day_start(race_date, timezone):
    return datetime.combine(date.fromisoformat(race_date),time(),ZoneInfo(timezone)).isoformat()


def create_run(conn, target_race_id, cutoff, judges):
    cutoff = utc(cutoff)
    if len(judges)<3 or len(judges)!=len(set(judges)) or any(not j.strip() for j in judges):
        raise ValueError('At least three distinct nonempty judge IDs are required')
    row = conn.execute('SELECT m.* FROM races r JOIN meetings m ON m.id=r.meeting_id WHERE r.id=?',(target_race_id,)).fetchone()
    if row is None:
        raise ValueError('Unknown target race')
    # Seed has no verified start times: use the beginning of the local race day.
    if cutoff>=utc(day_start(row['race_date'],row['timezone'])):
        raise ValueError('Cutoff must precede local race day; start time is unverified')
    if cutoff>now():
        raise ValueError('Cutoff cannot be in the future')
    rid = uid(target_race_id,cutoff,judges,now())
    with conn:
        insert(conn,'forecast_runs',id=rid,target_race_id=target_race_id,cutoff=cutoff,created_at=now(),
               required_judges_json=json.dumps(judges),policy_version=POLICY)
    return rid


def record_vote(conn, run_id, evidence_id, judge_id, response, model, prompt):
    run = conn.execute('SELECT * FROM forecast_runs WHERE id=?',(run_id,)).fetchone()
    if run is None or judge_id not in json.loads(run['required_judges_json']):
        raise ValueError('Unknown run or judge not on this run’s panel')
    try:
        parsed = json.loads(response)
        if (not isinstance(parsed,dict) or parsed.get('verdict') not in ('allow','drop')
                or not isinstance(parsed.get('reason'),str) or not parsed['reason'].strip()):
            raise ValueError('Expected verdict and nonempty reason')
        verdict,reason = parsed['verdict'],parsed['reason']
    except (ValueError,TypeError):
        verdict,reason = 'error','Unparseable judge reply; excluded from admission'
    with conn:
        # Plain INSERT: a second vote cannot replace a prior rejection or parse error.
        conn.execute('''INSERT INTO judge_votes
          (run_id,evidence_id,judge_id,verdict,reason,model,prompt_text,prompt_sha256,raw_response,created_at)
          VALUES (?,?,?,?,?,?,?,?,?,?)''',(run_id,evidence_id,judge_id,verdict,reason,model,prompt,
          hashlib.sha256(prompt.encode()).hexdigest(),response,now()))
    return verdict


def decision(conn, run_id, evidence_id, log=True):
    run = conn.execute('SELECT * FROM forecast_runs WHERE id=?',(run_id,)).fetchone()
    evidence = conn.execute('SELECT e.*,s.observed_at FROM evidence e JOIN snapshots s ON s.id=e.snapshot_id WHERE e.id=?',(evidence_id,)).fetchone()
    if run is None or evidence is None:
        raise ValueError('Unknown run or evidence')
    reasons = []
    if run['policy_version']!=POLICY:
        reasons.append('unsupported_policy_version')
    if utc(evidence['observed_at'])>run['cutoff']:
        reasons.append('snapshot_observed_after_cutoff')
    if evidence['kind']=='result':
        if evidence['related_race_id'] is None:
            reasons.append('result_without_race_context')
        elif evidence['related_race_id']==run['target_race_id']:
            reasons.append('target_race_outcome')
        else:
            m = conn.execute('SELECT m.* FROM races r JOIN meetings m ON m.id=r.meeting_id WHERE r.id=?',(evidence['related_race_id'],)).fetchone()
            # No precise finish time: prior performance is usable only after the whole local day.
            end_date = (date.fromisoformat(m['race_date'])+timedelta(days=1)).isoformat()
            if utc(day_start(end_date,m['timezone']))>run['cutoff']:
                reasons.append('historical_race_not_finished_by_cutoff')
    votes = {v['judge_id']:v['verdict'] for v in conn.execute('SELECT * FROM judge_votes WHERE run_id=? AND evidence_id=?',(run_id,evidence_id))}
    for judge in json.loads(run['required_judges_json']):
        if votes.get(judge)!='allow':
            reasons.append(f'judge:{judge}:{votes.get(judge,"missing")}')
    outcome = 'drop' if reasons else 'allow'
    if log:
        with conn:
            conn.execute('INSERT INTO gate_decisions(run_id,evidence_id,decision,reasons_json,decided_at) VALUES(?,?,?,?,?)',
                         (run_id,evidence_id,outcome,json.dumps(reasons),now()))
    return dict(evidence_id=evidence_id,decision=outcome,reasons=reasons)


def export_packet(conn, run_id, path):
    run = conn.execute('SELECT * FROM forecast_runs WHERE id=?',(run_id,)).fetchone()
    if run is None:
        raise ValueError('Unknown run')
    admitted = []
    for e in conn.execute('SELECT id,text FROM evidence ORDER BY id').fetchall():
        if decision(conn,run_id,e['id'])['decision']=='allow':
            admitted.append(dict(e))
    path = Path(path)
    if not admitted:
        raise ValueError('No admissible evidence; packet not created')
    path.parent.mkdir(parents=True,exist_ok=True)
    # A standalone whitelist database. No master connection, labels, raw pages, or judge replies.
    with path.open('xb'):
        pass
    try:
        packet = sqlite3.connect(path)
        with packet:
            packet.execute('CREATE TABLE task(run_id TEXT,target_race_id TEXT,cutoff TEXT,policy_version TEXT)')
            packet.execute('INSERT INTO task VALUES(?,?,?,?)',(run_id,run['target_race_id'],run['cutoff'],POLICY))
            packet.execute('CREATE TABLE evidence(id TEXT PRIMARY KEY,text TEXT NOT NULL)')
            packet.executemany('INSERT INTO evidence VALUES(:id,:text)',admitted)
        packet.close()
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        ident = uid(run_id,digest)
        with conn:
            insert(conn,'packet_exports',id=ident,run_id=run_id,created_at=now(),sha256=digest,
                   manifest_json=json.dumps(dict(evidence_ids=[e['id'] for e in admitted],policy=POLICY)))
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return dict(packet_id=ident,path=str(path),sha256=digest,evidence_count=len(admitted))
