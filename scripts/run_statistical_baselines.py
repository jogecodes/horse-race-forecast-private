#!/usr/bin/env python3
"""CPU-only development comparison; never evaluates 2026 validation/test."""
import argparse
from collections import Counter
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import sys
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from horse_racing.statistical import historical_cases,declaration_case,fit,predict,mean_metrics,evaluate


def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(out):
    out.mkdir(parents=True,exist_ok=False)
    bundle=ROOT/'benchmarks/h1_2026_v2'
    input_paths=[ROOT/'data/racing.sqlite',bundle/'manifest.json',bundle/'supervisor/labels.jsonl',
                 bundle/'diagnostic/tasks.jsonl',Path(__file__).resolve(),ROOT/'horse_racing/statistical.py']
    tasks=[json.loads(x) for x in (bundle/'diagnostic/tasks.jsonl').read_text().splitlines()]
    packets=[json.loads((bundle/'diagnostic/packets'/(t['race_id']+'.json')).read_text())
             for t in tasks if t['split']=='development']
    input_paths += [bundle/'diagnostic/packets'/(p['race_id']+'.json') for p in packets]
    before={str(p):sha(p) for p in input_paths}
    for source in [Path(__file__).resolve(),ROOT/'horse_racing/statistical.py']:
        target=out/'source'/source.name
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_bytes(source.read_bytes())
    save(out/'status.json',dict(status='running',started_at=datetime.now(timezone.utc).isoformat()))
    historical,histories,aliases,exclusions=historical_cases(ROOT/'data/racing.sqlite')
    train=[c for c in historical if c['date']<'2025-01-01']
    tune=[c for c in historical if '2025-01-01'<=c['date']<'2025-10-01']
    calibration=[c for c in historical if '2025-10-01'<=c['date']<'2026-01-01']
    protocol=dict(created_at=datetime.now(timezone.utc).isoformat(),input_hashes=before,
        python=sys.version,numpy_version=np.__version__,log_loss_floor=1e-15,
        training='2022-2024',selection='2025 January-September',calibration='2025 October-December',
        evaluation='2026 January-February development declarations only; frozen histories through 2025',
        scheduled_prediction_target='Future production: scheduled start minus 60 minutes',
        actual_experiment_cutoff='Existing day-before publisher-documented declaration benchmark; NOT a historical T-60 test',
        candidates=[.01,.1,1.],temperatures=[.5,.75,1.,1.5,2.,3.],
        selection_metric='Mean race log loss; calibration also minimizes log loss',
        counts=dict(train=len(train),selection=len(tune),calibration=len(calibration),development=len(packets)),
        caveats=['Prior result pages captured retrospectively; historical availability assumed',
            'Historical training fields reconstructed from results, not declarations',
            'No same-day results in features; no 2026 results used in feature histories',
            'Recorded appearances can include status codes/nonfinishers; not certified starts',
            'Unknown finish position contributes neutral recent strength, with no inferred finishing rank',
            'Declared nonstarters retained; target dead-heat win mass split equally',
            'No odds, LLM inference, shared engine changes, paid services or model downloads',
            '2026 validation/test outcomes not scored; development is already exposed'],
        exclusions=exclusions)
    save(out/'protocol.json',protocol)
    choices=[]
    for reg in protocol['candidates']:
        model=fit(train,reg)
        choices.append(dict(regularization=reg,metrics=mean_metrics(tune,'linear_race',model)))
    chosen=min(choices,key=lambda c:c['metrics']['log_loss'])['regularization']
    final_model=fit(train+tune,chosen)
    temperatures=[dict(temperature=t,metrics=mean_metrics(calibration,'linear_race',final_model,t))
                  for t in protocol['temperatures']]
    temperature=min(temperatures,key=lambda t:t['metrics']['log_loss'])['temperature']
    save(out/'model.json',dict(model=final_model,temperature=temperature,selection=choices,calibration=temperatures))
    public_cases=[declaration_case(p,histories,aliases) for p in packets]
    save(out/'public/features.json',public_cases)
    variants={'uniform':('uniform',None,1.),'smoothed_history':('smoothed_history',None,1.),
              'linear_race':('linear_race',final_model,1.),
              'linear_race_calibrated':('linear_race',final_model,temperature)}
    predictions={}
    for name,(kind,model,temp) in variants.items():
        rows=[dict(race_id=c['race_id'],probabilities=dict(zip(c['runner_ids'],predict(c,kind,model,temp))))
              for c in public_cases]
        predictions[name]=rows
        (out/(name+'_predictions.jsonl')).write_text(''.join(json.dumps(r,allow_nan=False)+'\n' for r in rows))
    # Evaluator-only: load only development labels after model selection and prediction.
    dev_ids={c['race_id'] for c in public_cases}
    labels={r['race_id']:r['target'] for r in map(json.loads,(bundle/'supervisor/labels.jsonl').read_text().splitlines())
            if r['race_id'] in dev_ids}
    summaries={}; race_scores=[]
    for name,rows in predictions.items():
        scored=[]
        for case,row in zip(public_cases,rows):
            target=[labels[case['race_id']][rid] for rid in case['runner_ids']]
            score=evaluate([row['probabilities'][rid] for rid in case['runner_ids']],target)
            scored.append(score);race_scores.append(dict(variant=name,race_id=case['race_id'],**score))
        summaries[name]=dict(races=len(scored),**{k:sum(s[k] for s in scored)/len(scored) for k in scored[0]})
    baseline=summaries['uniform']
    for summary in summaries.values():
        summary['brier_skill_vs_uniform']=1-summary['brier']/baseline['brier']
        summary['log_loss_improvement_vs_uniform']=baseline['log_loss']-summary['log_loss']
    save(out/'race_scores.json',race_scores)
    save(out/'summary.json',dict(variants=summaries,selected_regularization=chosen,temperature=temperature,
        identity_links=dict(Counter(link['status'] for c in public_cases for link in c['identity_links'])),
        independent_development_races=len(public_cases),interpretation='Multiclass race Brier (sum over runners), '
        'not directly comparable with the previous pooled binary Brier. Development only; no significance claim.'))
    assert all(sha(Path(p))==expected for p,expected in before.items()),'Input changed during experiment'
    save(out/'status.json',dict(status='completed',finished_at=datetime.now(timezone.utc).isoformat(),
        input_drift=[],scored_development_races=len(public_cases),variants=len(variants)))
    print(json.dumps(dict(out=str(out),summary=summaries),indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True)
    run(parser.parse_args().out.resolve())
