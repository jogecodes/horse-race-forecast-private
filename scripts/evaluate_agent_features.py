#!/usr/bin/env python3
"""Evaluator-only January-fit/February-score and paired market comparisons."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from horse_racing.agent_features import form_tokens,form_vector,fit_offset,predict_offset,AGENT_FEATURES
from horse_racing.forecast_comparison import score_predictions,paired_model_market,reported_price_proxies


def save(path,value):
    path.parent.mkdir(parents=True,exist_ok=True);tmp=path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n');tmp.replace(path)


def evaluate_run(out):
    packets=json.loads((out/'public/packets.json').read_text());ids={p['race_id'] for p in packets}
    bundle=ROOT/'benchmarks/h1_2026_v2'
    labels={r['race_id']:r['target'] for r in map(json.loads,(bundle/'supervisor/labels.jsonl').read_text().splitlines()) if r['race_id'] in ids}
    cases={r['race_id']:r for r in map(json.loads,(bundle/'supervisor/cases.jsonl').read_text().splitlines()) if r['race_id'] in ids}
    baseline={r['race_id']:r['probabilities'] for r in json.loads((out/'public/baseline_predictions.json').read_text())}
    january=[p for p in packets if p['date']<'2026-02-01'];february=[p for p in packets if p['date']>='2026-02-01']
    report=dict(scope='Development only; fit new weights on January, evaluate February. No refit/tuning on February.',
        expected=dict(january_training=len(january),february_evaluation=len(february)),
        evaluation_A_actual_results={},evaluation_B_market_comparison={},feature_extraction={})
    predictions={'baseline':{p['race_id']:baseline[p['race_id']] for p in february}}
    report['evaluation_A_actual_results']['baseline_all_48_development']=score_predictions(baseline,labels)[0]
    extracted={};statuses=Counter()
    for p in packets:
        file=out/'cases'/p['race_id']/'result.json'
        if not file.exists():continue
        record=json.loads(file.read_text());statuses[record['status']]+=1
        if record['status']=='complete':extracted[p['race_id']]=record['features']
    report['feature_extraction']=dict(completed_cases=sum(statuses.values()),statuses=dict(statuses),
        valid_extractions=len(extracted),expected=len(packets),feature_names=list(AGENT_FEATURES))
    def build(packet,mode):
        rid=packet['race_id'];runners=packet['runners']
        if mode=='agent':
            if rid not in extracted:return None
            x=[extracted[rid][r['runner_id']] for r in runners]
        else:x=[form_vector(*form_tokens(r['prior_form_raw'])) for r in runners]
        return dict(race_id=rid,x=x,baseline=[baseline[rid][r['runner_id']] for r in runners],
                    y=[labels[rid][r['runner_id']] for r in runners],runner_ids=[r['runner_id'] for r in runners])
    model_details={}
    for mode,name in [('literal','baseline_plus_deterministic_form'),('agent','baseline_plus_agent_features')]:
        train=[c for p in january if (c:=build(p,mode)) is not None]
        test=[c for p in february if (c:=build(p,mode)) is not None]
        if len(train)<5 or not test:
            model_details[name]=dict(status='insufficient_extractions',training=len(train),evaluation=len(test));continue
        model=fit_offset(train,regularization=1.,steps=1000)
        model_details[name]=dict(status='fit',model=model,training=len(train),evaluation=len(test),
            warning='Small January development fit; fixed ridge 1.0, no February tuning or probability calibration claim')
        predictions[name]={c['race_id']:dict(zip(c['runner_ids'],predict_offset(c,model))) for c in test}
    for name,rows in predictions.items():
        report['evaluation_A_actual_results'][name]=score_predictions(rows,labels)[0]
        if name!='baseline':
            common={rid:predictions['baseline'][rid] for rid in rows}
            report['evaluation_A_actual_results'][name]['baseline_on_same_races']=score_predictions(common,labels)[0]
    if 'baseline_plus_agent_features' in predictions:
        common_ids=set(predictions['baseline_plus_agent_features'])&set(predictions['baseline_plus_deterministic_form'])
        report['evaluation_A_actual_results']['agent_vs_literal_common_races']={name:score_predictions({rid:predictions[name][rid] for rid in common_ids},labels)[0]
            for name in ['baseline','baseline_plus_deterministic_form','baseline_plus_agent_features']}
    # Closing prices never enter the feature process. No currently stored price
    # has independent proof that it is the final available pre-off market quote.
    verified=json.loads((out/'evaluation_inputs/verified_closing_markets.json').read_text())
    proxies,excluded,receipts=reported_price_proxies(ROOT/'data/racing.sqlite',cases,packets)
    report['evaluation_B_market_comparison']['verified_closing']={name:paired_model_market(rows,labels,verified,evidence_tier='verified_closing') for name,rows in predictions.items()}
    report['evaluation_B_market_comparison']['reported_price_proxy']={name:paired_model_market(rows,labels,proxies,evidence_tier='reported_result_price_proxy_NOT_verified_closing') for name,rows in predictions.items()}
    report['evaluation_B_market_comparison']['proxy_coverage']=dict(full_markets=len(proxies),expected=len(packets),excluded_races=excluded,
        warning='Post-result DG fields are a provisional market proxy, not certified closing odds. No T-60 availability or executable return claim.')
    report['evaluation_B_market_comparison']['definitions']=dict(model_error='sum((model_probability - outcome_share)^2)',
        market_error='sum((market_probability - outcome_share)^2)',
        paired_difference='model_error - market_error on identical races/runner fields; negative favours model',
        disagreement='sum((model_probability - market_probability)^2); not accuracy')
    save(out/'evaluation/summary.json',report);save(out/'evaluation/models.json',model_details)
    save(out/'evaluation/predictions.json',predictions);save(out/'evaluation/market_price_receipts.json',receipts)
    print(json.dumps(dict(extractions=report['feature_extraction'],results=report['evaluation_A_actual_results'],
        verified_closing_markets=len(verified),reported_price_proxy_markets=len(proxies)),indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--out',required=True,type=Path)
    evaluate_run(parser.parse_args().out.resolve())
