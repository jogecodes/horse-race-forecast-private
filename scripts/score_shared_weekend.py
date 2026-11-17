#!/usr/bin/env python3
"""Outcome-aware evaluator; never imported by the forecasting worker."""
import argparse
from collections import defaultdict
import json
from pathlib import Path
from statistics import mean
import sys
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from horse_racing.shared_forecast import score_rows, write_json


def report(out):
    labels = {r['race_id']:r['target'] for r in map(json.loads,
        (ROOT/'benchmarks/h1_2026_v2/supervisor/labels.jsonl').read_text().splitlines())}
    planned = json.loads((out/'public/cases.json').read_text())
    rows = []
    errors = defaultdict(int)
    for case in planned:
        path = out/'cases'/case['case_id']/'outcome.json'
        if not path.exists():
            continue
        record = json.loads(path.read_text())
        result = record.get('result',{})
        p = result.get('probability')
        errors[result.get('status',record.get('error','missing_result'))] += 1
        rows.append({**case, 'probability':p, 'evidence_count':len(result.get('evidence',[])),
                     'model_calls':result.get('model_calls')})
    scored = score_rows(rows,labels)
    groups, pairs, races = defaultdict(list), defaultdict(dict), defaultdict(list)
    for row in scored:
        groups[(row['model'],row['seed'],row['arm'])].append(row)
        pairs[(row['model'],row['seed'],row['race_id'],row['runner_id'])][row['arm']] = row
        races[(row['model'],row['seed'],row['arm'],row['race_id'])].append(row)
    summaries = []
    for (model,seed,arm), members in groups.items():
        target = [c for c in planned if (c['model'],c['seed'],c['arm'])==(model,seed,arm)]
        summaries.append(dict(model=model,seed=seed,arm=arm,valid=len(members),planned=len(target),
            brier=mean(r['brier'] for r in members), uniform_brier_same_subset=mean(r['uniform_brier'] for r in members),
            evidence_retention_fraction=mean(r['evidence_count']>0 for r in members)))
    paired = defaultdict(list)
    for key, arms in pairs.items():
        if len(arms)==2:
            paired[key[:2]].append(arms['declaration_research']['brier']-arms['declaration_only']['brier'])
    coherence = []
    for key,members in races.items():
        if len(members)==members[0]['field_size']:
            coherence.append(dict(model=key[0],seed=key[1],arm=key[2],race_id=key[3],
                probability_sum=sum(r['probability'] for r in members),
                binary_brier=mean(r['brier'] for r in members)))
    write_json(out/'evaluation/summary.json',dict(planned=len(planned), attempted=len(rows),valid=len(scored),
        statuses=dict(errors),groups=summaries,
        paired=[dict(model=k[0],seed=k[1],paired_runner_cases=len(v),
                     research_minus_declaration_brier=mean(v)) for k,v in paired.items()],
        complete_race_diagnostics=coherence,
        interpretation='Development only. Runner binary scores, not normalized race distributions. '
            'Paired differences use common valid runners. Seeds/runner events are dependent; '
            'no significance or calibrated performance claim. Missing forecasts excluded, coverage reported.'))
    write_json(out/'evaluation/scored_rows.json',scored)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--out',type=Path,required=True)
    report(parser.parse_args().out)
