#!/usr/bin/env python3
"""CPU-only feature experiments: four 2025 walk-forward folds, then 2026 dev."""
from collections import defaultdict
from datetime import datetime,timezone
import argparse
import hashlib
import json
from pathlib import Path
import random
import statistics
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import numpy as np
from horse_racing.statistical import historical_cases,declaration_case,predict,evaluate
from horse_racing.ablation import (VARIANTS,GROUPS,EXTENDED_FEATURES,add_prior_ratings,
    add_frozen_ratings,project,fit_subset,chronological_parts)

FOLDS=[
    ('2025_Q1','2024-07-01','2024-10-01','2025-01-01','2025-04-01'),
    ('2025_Q2','2024-10-01','2025-01-01','2025-04-01','2025-07-01'),
    ('2025_Q3','2025-01-01','2025-04-01','2025-07-01','2025-10-01'),
    ('2025_Q4','2025-04-01','2025-07-01','2025-10-01','2026-01-01'),
]
REGULARIZATIONS=[.01,.1,1.]
TEMPERATURES=[.5,.75,1.,1.5,2.,3.]


def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n');tmp.replace(path)


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def mean_score(rows):
    keys=('brier','log_loss','top1_fractional_accuracy')
    return dict(races=len(rows),**{k:statistics.mean(r[k] for r in rows) for k in keys})


def scored(cases,kind,model=None,temperature=1.):
    rows=[]
    for c in cases:
        p=predict(c,kind,model,temperature)
        rows.append(dict(race_id=c['race_id'],date=c['date'],venue=c['venue'],
                         **evaluate(p,c['y'])))
    return rows


def tune_variant(train,tune,cal,indices):
    candidates=[]
    for reg in REGULARIZATIONS:
        model=fit_subset(train,indices,reg)
        candidates.append(dict(regularization=reg,metrics=mean_score(scored(project(tune,indices),'linear_race',model))))
    reg=min(candidates,key=lambda r:r['metrics']['log_loss'])['regularization']
    model=fit_subset(train+tune,indices,reg)
    temps=[dict(temperature=t,metrics=mean_score(scored(project(cal,indices),'linear_race',model,t))) for t in TEMPERATURES]
    temperature=min(temps,key=lambda r:r['metrics']['log_loss'])['temperature']
    return dict(model=model,temperature=temperature,regularization_selection=candidates,temperature_selection=temps)


def paired_interval(rows,variant,baseline='legacy_full',samples=2000):
    baseline_rows={r['race_id']:r for r in rows if r['variant']==baseline}
    target=[r for r in rows if r['variant']==variant]
    groups=defaultdict(list)
    for row in target:
        other=baseline_rows[row['race_id']]
        groups[(row['date'],row['venue'])].append({k:row[k]-other[k] for k in ['brier','log_loss']})
    rng=random.Random(2026);clusters=list(groups.values());draws=defaultdict(list)
    for _ in range(samples):
        sample=[r for cluster in rng.choices(clusters,k=len(clusters)) for r in cluster]
        for k in ['brier','log_loss']:draws[k].append(statistics.mean(r[k] for r in sample))
    result={}
    for k,v in draws.items():
        v.sort();result[k]=dict(mean=statistics.mean(r[k] for group in clusters for r in group),percentile_95=[v[49],v[1949]])
    return dict(races=len(target),meeting_clusters=len(clusters),difference_vs=baseline,metrics=result,
                warning='Descriptive development intervals; selected-model comparisons are optimistic and not multiplicity-adjusted')


def run(out):
    out.mkdir(parents=True,exist_ok=False)
    sources=[ROOT/'horse_racing/statistical.py',ROOT/'horse_racing/ablation.py',Path(__file__).resolve()]
    bundle=ROOT/'benchmarks/h1_2026_v2'
    tasks=[json.loads(l) for l in (bundle/'diagnostic/tasks.jsonl').read_text().splitlines()]
    packet_paths=[bundle/'diagnostic/packets'/(t['race_id']+'.json') for t in tasks if t['split']=='development']
    anchor=ROOT/'runs/statistical_baselines_20261111/linear_race_calibrated_predictions.jsonl'
    inputs=sources+[ROOT/'data/racing.sqlite',bundle/'manifest.json',bundle/'supervisor/labels.jsonl',bundle/'diagnostic/tasks.jsonl',anchor]+packet_paths
    hashes={str(p):sha(p) for p in inputs}
    protocol=dict(created_at=datetime.now(timezone.utc).isoformat(),source_and_input_hashes=hashes,
        features=list(EXTENDED_FEATURES),variants={k:list(v) for k,v in VARIANTS.items()},
        fixed_baselines=['uniform','smoothed_history'],folds=FOLDS,regularizations=REGULARIZATIONS,temperatures=TEMPERATURES,
        rating_step=.5,optimizer_steps=1000,python=sys.version,numpy=np.__version__,
        candidate_selection='Lowest pooled 2025 outer-fold log loss, frozen before 2026 development scoring',
        chronological_policy='Each fold selects regularization on earlier tuning period, refits, and selects temperature on a later but still pre-evaluation calibration period',
        evaluation_2026='January-February development only; frozen history through 2025',
        caveats=['All periods are exposed development data, not new held-out validation',
            'Historical fields/availability remain retrospective assumptions',
            'Current features and rating state exclude same-day and future results',
            '2026 histories remain frozen through 2025; all declared runners retained',
            'Per-fold historical features use earlier observed results during the evaluation period, without retraining model coefficients',
            'Feature ablations compare predictive contributions under a specified model, not causal effects',
            'No odds, LLM calls, provider collection, GPU, or 2026 validation/test evaluation'])
    save(out/'protocol.json',protocol)
    for p in sources:
        target=out/'source'/p.name;target.parent.mkdir(exist_ok=True);target.write_bytes(p.read_bytes())
    save(out/'status.json',dict(status='running',phase='building_features'))
    historical,histories,aliases,exclusions=historical_cases(ROOT/'data/racing.sqlite')
    extended,ratings=add_prior_ratings(historical)
    outer_rows=[];fold_summaries=[]
    for name,a,b,c,d in FOLDS:
        train,tune,cal,test=chronological_parts(extended,a,b,c,d)
        summary=dict(fold=name,counts=dict(train=len(train),tune=len(tune),calibration=len(cal),evaluation=len(test)),variants={})
        for kind in ['uniform','smoothed_history']:
            rows=scored(test,kind)
            outer_rows.extend(dict(r,fold=name,variant=kind) for r in rows);summary['variants'][kind]=mean_score(rows)
        for variant,indices in VARIANTS.items():
            save(out/'status.json',dict(status='running',phase='walk_forward',fold=name,variant=variant))
            selected=tune_variant(train,tune,cal,indices)
            save(out/'models'/name/(variant+'.json'),selected)
            rows=scored(project(test,indices),'linear_race',selected['model'],selected['temperature'])
            outer_rows.extend(dict(r,fold=name,variant=variant) for r in rows)
            summary['variants'][variant]=mean_score(rows)
        fold_summaries.append(summary);save(out/'walk_forward_scores.json',outer_rows)
        save(out/'fold_summaries.json',fold_summaries)
    pooled={name:mean_score([r for r in outer_rows if r['variant']==name]) for name in ['uniform','smoothed_history',*VARIANTS]}
    winner=min(pooled,key=lambda k:pooled[k]['log_loss'])
    selection=dict(selected_variant=winner,selection_uses='Only 2025 walk-forward evaluation scores',pooled_2025=pooled,
        frozen_before_2026_prediction_at=datetime.now(timezone.utc).isoformat())
    save(out/'candidate_selection.json',selection)
    train=[r for r in extended if r['date']<'2025-01-01']
    tune=[r for r in extended if '2025-01-01'<=r['date']<'2025-10-01']
    cal=[r for r in extended if r['date']>='2025-10-01']
    public_cases=[add_frozen_ratings(declaration_case(json.loads(p.read_text()),histories,aliases),ratings) for p in packet_paths]
    save(out/'public/development_features.json',public_cases)
    prediction_sets={}
    for variant in ['uniform','smoothed_history',*VARIANTS]:
        save(out/'status.json',dict(status='running',phase='development_predictions',variant=variant,selected_on_2025=winner))
        if variant in VARIANTS:
            indices=VARIANTS[variant];selected=tune_variant(train,tune,cal,indices)
            save(out/'models/2026_development'/(variant+'.json'),selected)
            transformed=project(public_cases,indices);kind='linear_race';model=selected['model'];temperature=selected['temperature']
        else:transformed=public_cases;kind=variant;model=None;temperature=1.
        rows=[dict(race_id=c['race_id'],probabilities=dict(zip(c['runner_ids'],predict(c,kind,model,temperature)))) for c in transformed]
        prediction_sets[variant]=rows
        path=out/'predictions'/(variant+'.jsonl');path.parent.mkdir(exist_ok=True)
        path.write_text(''.join(json.dumps(r,allow_nan=False)+'\n' for r in rows))
    # Exact anchor check, before any 2026 outcome scoring.
    old={r['race_id']:r['probabilities'] for r in map(json.loads,anchor.read_text().splitlines())}
    max_difference=max(abs(p-old[r['race_id']][rid]) for r in prediction_sets['legacy_full'] for rid,p in r['probabilities'].items())
    assert max_difference<1e-12,('Existing baseline did not reproduce',max_difference)
    ids={c['race_id'] for c in public_cases}
    labels={r['race_id']:r['target'] for r in map(json.loads,(bundle/'supervisor/labels.jsonl').read_text().splitlines()) if r['race_id'] in ids}
    dev_rows=[]
    for variant,rows in prediction_sets.items():
        for case,row in zip(public_cases,rows):
            assert set(row['probabilities'])==set(case['runner_ids'])
            p=[row['probabilities'][rid] for rid in case['runner_ids']];y=[labels[case['race_id']][rid] for rid in case['runner_ids']]
            dev_rows.append(dict(variant=variant,race_id=case['race_id'],date=case['date'],venue=case['venue'],**evaluate(p,y)))
    dev={name:mean_score([r for r in dev_rows if r['variant']==name]) for name in pooled}
    ablations={}
    for group in GROUPS:
        without='legacy_full' if group=='winner_rating' else 'without_'+group
        ablations[group]=dict(without_variant=without,
            walk_forward_drop_minus_full_log_loss=pooled[without]['log_loss']-pooled['full_with_rating']['log_loss'],
            development_drop_minus_full_log_loss=dev[without]['log_loss']-dev['full_with_rating']['log_loss'],
            walk_forward_folds_where_inclusion_helps=sum(f['variants'][without]['log_loss']>f['variants']['full_with_rating']['log_loss'] for f in fold_summaries))
    save(out/'development_scores.json',dev_rows)
    summary=dict(selected_on_2025=winner,walk_forward_2025=pooled,development_2026=dev,group_ablations=ablations,
        paired_2025_selected_vs_legacy=paired_interval(outer_rows,winner),
        paired_2026_selected_vs_legacy=paired_interval(dev_rows,winner),
        exact_legacy_reproduction_max_probability_difference=max_difference,
        rating_feature='Online winner rating updated after the whole day; step 0.5 fixed in advance',
        historical_exclusions=exclusions,
        interpretation='Drop-minus-full positive means inclusion helped; negative means removing the group helped. No held-out or T-60/market-edge claim.')
    save(out/'summary.json',summary)
    assert all(sha(Path(p))==h for p,h in hashes.items()),'Source/input changed during experiment'
    save(out/'status.json',dict(status='completed',finished_at=datetime.now(timezone.utc).isoformat(),variants=len(pooled),walk_forward_races=len({r['race_id'] for r in outer_rows}),development_races=len(public_cases),input_drift=[]))
    print(json.dumps(dict(out=str(out),selected_on_2025=winner,selected_development=dev[winner],legacy_development=dev['legacy_full'],ablations=ablations),indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',required=True,type=Path)
    run(parser.parse_args().out.resolve())
