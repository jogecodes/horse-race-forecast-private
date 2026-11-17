#!/usr/bin/env python3
"""Correct the cohort confound and export a minimal research showcase dataset."""
import argparse
from collections import Counter
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from horse_racing.research_release import fit_arms,paired_interval,reliability
from horse_racing.forecast_comparison import score_predictions,reported_price_proxies,paired_model_market


def read(p):return json.loads(p.read_text())
def save(p,obj):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def build(source,out,site):
    if out.exists():raise FileExistsError('Preserve existing releases; choose a new directory')
    packets=read(source/'public/packets.json');ids={p['race_id'] for p in packets}
    if len(packets)!=48 or any(p['split']!='development' for p in packets):raise ValueError('Development scope only')
    bundle=ROOT/'benchmarks/h1_2026_v2/supervisor'
    labels={r['race_id']:r['target'] for r in map(json.loads,(bundle/'labels.jsonl').read_text().splitlines()) if r['race_id'] in ids}
    cases={r['race_id']:r for r in map(json.loads,(bundle/'cases.jsonl').read_text().splitlines()) if r['race_id'] in ids}
    baseline={r['race_id']:r['probabilities'] for r in read(source/'public/baseline_predictions.json')}
    extractions={p['race_id']:read(source/'cases'/p['race_id']/'result.json') for p in packets}
    audit=dict(statuses=dict(Counter(r['status'] for r in extractions.values())),
        failures=dict(Counter(r['error'] for r in extractions.values() if r['status']=='failed')),
        accepted_runner_rows=sum(len(r.get('features',{})) for r in extractions.values()),
        runner_rows_with_text_signal=sum(any(v!=0 for v in row[6:]) for r in extractions.values() for row in r.get('features',{}).values()),
        races_with_reviewed_evidence=0,reviewed_evidence_items=0)
    for p in packets:
        f=source/'cases'/p['race_id']/'research.json'
        if f.exists():
            n=len(read(f)['evidence']);audit['races_with_reviewed_evidence']+=bool(n);audit['reviewed_evidence_items']+=n
    predictions,models=fit_arms(packets,baseline,labels,extractions)
    meetings={k:v['meeting_id'] for k,v in cases.items()}
    metrics={name:score_predictions(rows,labels)[0] for name,rows in predictions.items()}
    paired={name:paired_interval(predictions[name],predictions['baseline'],labels,meetings) for name in ['deterministic_form','optional_agent']}
    paired['agent_minus_deterministic']=paired_interval(predictions['optional_agent'],predictions['deterministic_form'],labels,meetings)
    calibration={name:reliability(rows,labels) for name,rows in predictions.items()}
    markets,excluded,receipts=reported_price_proxies(ROOT/'data/racing.sqlite',cases,packets)
    # Only February belongs in the scored market cohort.
    feb=set(predictions['baseline']);markets={rid:q for rid,q in markets.items() if rid in feb}
    market_reports={name:paired_model_market(rows,labels,markets,evidence_tier='reported_result_price_proxy_NOT_verified_closing') for name,rows in predictions.items()}
    for name,rows in predictions.items():
        common={rid:rows[rid] for rid in markets};q={rid:r['probabilities'] for rid,r in markets.items()}
        market_reports[name]['uncertainty']=paired_interval(common,q,labels,meetings)
    max_difference=max(abs(v-predictions['optional_agent'][rid][k]) for rid,row in predictions['deterministic_form'].items() for k,v in row.items())
    report=dict(created_at=datetime.now(timezone.utc).isoformat(),release='cohort-correction-v3',
        training_races=20,evaluation_races=28,scope='January fit / February development evaluation; March–June untouched',
        historical_validity='Retrospective publisher-dated day-before declarations; no archived T-60 claim',
        correction='Both arms now retain deterministic form on all races and use identical January training and February evaluation cohorts. Existing failed extractions remain failed; article evidence is explicitly unavailable for those rows.',
        disclosure='Protocol correction after inspection of February development results; not a new blind test. No new inference and no held-out labels used.',
        metrics=metrics,paired_uncertainty=paired,reliability=calibration,extraction_audit=audit,
        agent_deterministic_max_probability_difference=max_difference,verified_closing_races=0,
        market_proxy=market_reports,proxy_excluded_races=excluded,
        conclusion='Accepted article columns contain no signal. With matching cohorts the optional-agent arm reproduces deterministic-form predictions. Any gain over baseline comes from literal declaration form.')
    races=[]
    for p in packets:
        rid=p['race_id']
        if rid not in feb:continue
        race=dict(id=rid,date=p['date'],venue=p['venue'],distance_m=p['distance_m'],cutoff=p['cutoff_utc'],
            extraction_status=extractions[rid]['status'],source_url=cases[rid]['declaration']['url'],
            proxy_available=rid in markets,runners=[])
        for r in p['runners']:
            k=r['runner_id'];race['runners'].append(dict(name=r['horse_name'],
                baseline=predictions['baseline'][rid][k],form=predictions['deterministic_form'][rid][k],
                agent=predictions['optional_agent'][rid][k],market=markets[rid]['probabilities'][k] if rid in markets else None,
                outcome=labels[rid][k]))
        races.append(race)
    out.mkdir(parents=True)
    inputs=[source/'public/packets.json',source/'public/baseline_predictions.json',bundle/'cases.jsonl',bundle/'labels.jsonl',ROOT/'data/racing.sqlite']
    inputs+=list((source/'cases').glob('*/result.json'))+list((source/'cases').glob('*/research.json'))
    code=[Path(__file__).resolve(),ROOT/'horse_racing/research_release.py',ROOT/'horse_racing/agent_features.py',ROOT/'horse_racing/forecast_comparison.py',ROOT/'horse_racing/statistical.py']
    save(out/'manifest.json',dict(source_run=str(source),input_hashes={str(p):sha(p) for p in inputs},code_hashes={str(p):sha(p) for p in code},new_inference=False))
    save(out/'summary.json',report);save(out/'models.json',models);save(out/'predictions.json',predictions)
    save(out/'market_price_receipts.json',receipts)
    # Deliberately exported facts/derived forecasts, no raw articles, DB or private traces.
    if site is not None:
        save(site/'data/research.json',dict(report=report,races=races))
        save(site/'data/summary.json',report)
    save(out/'status.json',dict(status='completed',evaluation_races=len(races),new_inference=False))
    print(json.dumps(dict(metrics=metrics,max_agent_difference=max_difference,paired=paired,audit=audit),indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,default=ROOT/'runs/agent_features_20261111_v2')
    p.add_argument('--out',type=Path,required=True);p.add_argument('--site',type=Path,help='Explicit local export only; no default website export')
    a=p.parse_args();build(a.source.resolve(),a.out.resolve(),a.site.resolve() if a.site else None)
