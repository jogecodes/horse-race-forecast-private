"""Evaluator-only forecast errors and paired closing-market comparisons."""
import math
import re
import sqlite3
from pathlib import Path
from .statistical import evaluate


def average(rows):
    if not rows:return None
    return {key:sum(r[key] for r in rows)/len(rows) for key in ['brier','log_loss']}


def score_predictions(predictions,labels):
    scores={};errors={}
    for rid,probs in predictions.items():
        if rid not in labels:errors[rid]='missing_label';continue
        target=labels[rid]
        if set(probs)!=set(target):errors[rid]='runner_set_mismatch';continue
        try:scores[rid]=evaluate([probs[k] for k in target],[target[k] for k in target])
        except ValueError as exc:errors[rid]=str(exc)
    return dict(valid_races=len(scores),metrics=average(list(scores.values())),errors=errors),scores


def paired_model_market(predictions,labels,markets,*,evidence_tier):
    rows=[];exclusions={}
    for rid,market in markets.items():
        if rid not in predictions or rid not in labels:
            exclusions[rid]='missing_model_or_label';continue
        p=predictions[rid];q=market['probabilities'];y=labels[rid]
        if set(p)!=set(q) or set(p)!=set(y):exclusions[rid]='different_runner_fields';continue
        try:
            ps=evaluate([p[k] for k in y],[y[k] for k in y]);qs=evaluate([q[k] for k in y],[y[k] for k in y])
        except ValueError as exc:exclusions[rid]=str(exc);continue
        rows.append(dict(race_id=rid,model_brier=ps['brier'],market_brier=qs['brier'],
            model_minus_market_brier=ps['brier']-qs['brier'],model_log_loss=ps['log_loss'],
            market_log_loss=qs['log_loss'],model_minus_market_log_loss=ps['log_loss']-qs['log_loss'],
            model_market_squared_distance=sum((p[k]-q[k])**2 for k in y)))
    means={k:sum(r[k] for r in rows)/len(rows) for k in rows[0] if k!='race_id'} if rows else None
    return dict(evidence_tier=evidence_tier,paired_races=len(rows),metrics=means,rows=rows,exclusions=exclusions,
        interpretation='Positive model-minus-market error means the market forecast was better. '
        'Model-market distance measures disagreement, not correctness. Both errors use identical races/runner fields.')


def reported_price_proxies(db,cases,public_packets):
    """Uniformly filtered post-result fields; never label them certified closing odds."""
    c=sqlite3.connect('file:'+str(Path(db).resolve())+'?mode=ro',uri=True);c.row_factory=sqlite3.Row
    markets={};excluded={};receipts=[]
    try:
        for packet in public_packets:
            rid=packet['race_id'];case=cases[rid];prices={};bad=[]
            for runner in packet['runners']:
                runner_id=runner['runner_id'];hid=case['runner_mapping'].get(runner_id)
                if hid is None:bad.append(dict(runner_id=runner_id,reason='no_reported_price_for_declared_runner'));continue
                row=c.execute('''SELECT d.dividend_raw,d.time_or_margin_raw,s.url,s.sha256,s.observed_at
                  FROM latest_results x JOIN result_details d ON d.result_id=x.id
                  JOIN race_versions v ON v.id=x.race_version_id JOIN snapshots s ON s.id=v.snapshot_id
                  WHERE x.race_id=? AND x.horse_id=?''',(case['source_race_id'],hid)).fetchone()
                if row is None:bad.append(dict(runner_id=runner_id,reason='missing_price_record'));continue
                raw=row['dividend_raw'].strip();normalized=raw.replace(',','.')
                value=float(normalized) if re.fullmatch(r'\d+(?:\.\d+)?',normalized) else None
                receipt=dict(race_id=rid,runner_id=runner_id,raw=raw,url=row['url'],source_sha256=row['sha256'],observed_at=row['observed_at'],quote_at=None)
                receipts.append(receipt)
                if value is None or not math.isfinite(value) or value<1:
                    bad.append(dict(runner_id=runner_id,reason='missing_or_invalid_reported_price'));continue
                if raw==row['time_or_margin_raw'].strip():
                    bad.append(dict(runner_id=runner_id,reason='suspected_duplicated_margin_or_time'));continue
                prices[runner_id]=value
            if bad:excluded[rid]=bad;continue
            total=sum(1/v for v in prices.values())
            markets[rid]=dict(probabilities={k:(1/v)/total for k,v in prices.items()},
                evidence_tier='reported_result_price_proxy',quote_at=None,
                assumption='Interpret reported DG as decimal gross return; normalize inverse prices over complete declared field. '
                'No independent proof of exact closing price or historical availability.')
    finally:c.close()
    return markets,excluded,receipts
