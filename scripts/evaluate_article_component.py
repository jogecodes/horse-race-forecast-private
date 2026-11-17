#!/usr/bin/env python3
"""Local-only outcome evaluation after the controlled extraction component run."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from horse_racing.agent_features import form_tokens,form_vector
from horse_racing.article_features import article_vector
from horse_racing.research_release import fit_arms,paired_interval,reliability
from horse_racing.forecast_comparison import score_predictions,reported_price_proxies,paired_model_market


def read(p):return json.loads(p.read_text())
def save(p,value):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def evaluate(component,out):
    if out.exists():raise FileExistsError('Choose a new evaluation directory')
    state=read(component/'status.json')
    if state['status']!='completed' or not state['service_stopped']:raise ValueError('Extraction queue must finish first')
    original=ROOT/'runs/agent_features_20261111_v2/public';packets=read(original/'packets.json')
    if len(packets)!=48 or any(p['split']!='development' for p in packets):raise ValueError('Development scope only')
    baseline={r['race_id']:r['probabilities'] for r in read(original/'baseline_predictions.json')}
    # Build model features before reading outcome labels. Form is independent of
    # article inference status; no case is dropped for missing/failed evidence.
    assembled={};runner_files=[];nonzero={}
    for p in packets:
        features={};statuses={}
        for r in p['runners']:
            k=r['runner_id'];file=component/'runners'/(k+'.json');record=read(file);runner_files.append(file)
            v=article_vector(record);features[k]=form_vector(*form_tokens(r['prior_form_raw']))+v
            statuses[k]=record['status'];nonzero[k]=bool(any(v))
        assembled[p['race_id']]=dict(status='complete',assembly='deterministic form plus optional article evidence',features=features,article_status_by_runner=statuses)
    ids={p['race_id'] for p in packets};bundle=ROOT/'benchmarks/h1_2026_v2/supervisor'
    labels={r['race_id']:r['target'] for r in map(json.loads,(bundle/'labels.jsonl').read_text().splitlines()) if r['race_id'] in ids}
    cases={r['race_id']:r for r in map(json.loads,(bundle/'cases.jsonl').read_text().splitlines()) if r['race_id'] in ids}
    predictions,models=fit_arms(packets,baseline,labels,assembled)
    meetings={k:c['meeting_id'] for k,c in cases.items()}
    scores={k:score_predictions(rows,labels)[0] for k,rows in predictions.items()}
    comparisons={k:paired_interval(predictions['optional_agent'],predictions[k],labels,meetings) for k in ['baseline','deterministic_form']}
    calibration={k:reliability(rows,labels) for k,rows in predictions.items()}
    markets,excluded,receipts=reported_price_proxies(ROOT/'data/racing.sqlite',cases,packets)
    markets={rid:m for rid,m in markets.items() if rid in predictions['baseline']}
    market_report={k:paired_model_market(rows,labels,markets,evidence_tier='reported_result_price_proxy_NOT_verified_closing') for k,rows in predictions.items()}
    report=dict(created_at=datetime.now(timezone.utc).isoformat(),scope='20 January training / same 28 February development races; no tuning on February',
        extraction_source='Controlled eligible named-horse articles; shared-engine retrieval NOT evaluated',
        source_timing='Publisher-documented retrospective, day-before cutoffs; no certified T-60 archive',
        extraction_summary=read(component/'extraction_summary.json'),runners_with_nonzero_article_features=sum(nonzero.values()),
        metrics=scores,agent_minus_reference=comparisons,reliability=calibration,market_proxy=market_report,verified_closing_races=0,
        caveats=['Assistant-reviewed selected reference cases; independent human review pending',
            'January-February development outcomes were previously inspected; not an unseen backtest',
            'Only two target-date preview articles; limited coverage and source concentration',
            'Meeting bootstrap describes fixed-model evaluation uncertainty, not fitting uncertainty',
            'No new model calibration; no claimed per-horse uncertainty intervals',
            'No website export or publication; no March-June evaluation'])
    out.mkdir(parents=True)
    inputs=[component/'manifest.json',component/'extraction_summary.json',original/'packets.json',original/'baseline_predictions.json',bundle/'labels.jsonl',bundle/'cases.jsonl',ROOT/'data/racing.sqlite']+runner_files
    code=[Path(__file__).resolve(),ROOT/'horse_racing/research_release.py',ROOT/'horse_racing/article_features.py',ROOT/'horse_racing/agent_features.py',ROOT/'horse_racing/forecast_comparison.py']
    save(out/'manifest.json',dict(component_run=str(component),input_hashes={str(p):sha(p) for p in inputs},code_hashes={str(p):sha(p) for p in code},publication='PROHIBITED'))
    save(out/'summary.json',report);save(out/'models.json',models);save(out/'predictions.json',predictions)
    save(out/'features.json',assembled);save(out/'market_price_receipts.json',receipts)
    save(out/'status.json',dict(status='completed',races_scored=28))
    print(json.dumps(dict(metrics=scores,article_signal_runners=sum(nonzero.values()),agent_minus_reference=comparisons),indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--component',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    evaluate(a.component.resolve(),a.out.resolve())
