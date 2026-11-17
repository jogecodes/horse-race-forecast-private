#!/usr/bin/env python3
"""Paired uncertainty and integrity checks for the frozen statistical run."""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import random
import statistics


def analyze(out):
    protocol=json.loads((out/'protocol.json').read_text())
    cases=json.loads((out/'public/features.json').read_text())
    scores=json.loads((out/'race_scores.json').read_text())
    score_map={(r['variant'],r['race_id']):r for r in scores}
    groups=defaultdict(list)
    for c in cases:
        groups[(c['date'],c['venue'])].append(c['race_id'])
    clusters=list(groups.values());rng=random.Random(2026)
    samples=[sum(rng.choices(clusters,k=len(clusters)),[]) for _ in range(2000)]
    intervals={}
    for variant in ['smoothed_history','linear_race','linear_race_calibrated']:
        intervals[variant]={}
        for metric in ['brier','log_loss']:
            differences=sorted(statistics.mean(score_map[(variant,rid)][metric]-score_map[('uniform',rid)][metric]
                for rid in sample) for sample in samples)
            intervals[variant][metric+'_difference_vs_uniform']={
                'mean':statistics.mean(score_map[(variant,c['race_id'])][metric]-score_map[('uniform',c['race_id'])][metric] for c in cases),
                'percentile_95':[differences[49],differences[1949]]}
    verified={}
    expected={c['race_id']:set(c['runner_ids']) for c in cases}
    for p in out.glob('*_predictions.jsonl'):
        rows=[json.loads(l) for l in p.read_text().splitlines()]
        assert len(rows)==len(expected) and len({r['race_id'] for r in rows})==len(expected)
        for row in rows:
            probs=row['probabilities']
            assert set(probs)==expected[row['race_id']]
            assert all(isinstance(p,(int,float)) and 0<=p<=1 for p in probs.values())
            assert abs(sum(probs.values())-1)<1e-6
        verified[p.name]=len(rows)
    drift=[p for p,h in protocol['input_hashes'].items() if hashlib.sha256(Path(p).read_bytes()).hexdigest()!=h]
    result=dict(meeting_clusters=len(groups),races=len(cases),paired_meeting_bootstrap=intervals,
        bootstrap=dict(resamples=2000,seed=2026,cluster='race date and venue',
            interpretation='Descriptive paired percentile intervals on exposed development data; no correction for model selection'),
        probability_integrity=verified,input_or_code_drift=drift,
        note='summary.independent_development_races denotes unique races, not statistical independence; use meeting clusters.')
    (out/'analysis.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',required=True,type=Path)
    analyze(parser.parse_args().out)
