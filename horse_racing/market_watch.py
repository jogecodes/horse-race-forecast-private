"""Outcome-free fixed-odds disagreement detector with a strict T-60 boundary.

The caller supplies a verified identity mapping and captured price data. This
module does not fetch websites, place bets or certify an imported timestamp.
"""
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
from pathlib import Path


def timestamp(value):
    result=datetime.fromisoformat(value.replace('Z','+00:00'))
    if result.tzinfo is None:raise ValueError('Timezone required')
    return result


def canonical(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,allow_nan=False,separators=(',',':'))


def probability(value):
    return not isinstance(value,bool) and isinstance(value,(int,float)) and math.isfinite(value) and 0<=value<=1


def inspect_market(snapshot,prediction,*,min_gap=.03,min_model_return=.05,max_age_seconds=300):
    """A complete single-book win market; policy thresholds are development defaults.

    No outcomes are accepted or read. Return before-cost model-implied returns,
    never realized profits or an assertion that displayed prices are executable.
    """
    if not probability(min_gap) or not math.isfinite(min_model_return) or min_model_return<0:
        raise ValueError('Invalid flag policy')
    if type(max_age_seconds) is not int or max_age_seconds<0:raise ValueError('Invalid staleness policy')
    errors=[]
    cutoff=timestamp(snapshot['scheduled_start_at'])-timedelta(hours=1)
    capture=timestamp(snapshot['captured_at'])
    quote=timestamp(snapshot['quote_at'])
    forecast=timestamp(prediction['created_at'])
    if snapshot.get('price_type')!='fixed' or snapshot.get('market')!='win':
        errors.append('requires_fixed_odds_win_market')
    if snapshot.get('status')!='open' or snapshot.get('in_play') is not False:
        errors.append('market_not_open_pre_race')
    if not snapshot.get('provider') or not snapshot.get('market_id') or not snapshot.get('source_url'):
        errors.append('missing_provider_provenance')
    for field in ['raw_response_sha256','capture_receipt_id']:
        if not isinstance(snapshot.get(field),str) or not snapshot[field].strip():
            errors.append('missing_'+field)
    if not snapshot.get('schedule_source') or 'schedule_known_at' not in snapshot:
        errors.append('missing_schedule_provenance')
    elif timestamp(snapshot['schedule_known_at'])>capture:
        errors.append('schedule_not_known_at_capture')
    if capture>cutoff:errors.append('capture_after_T60')
    if quote>capture:errors.append('quote_after_capture')
    if quote>cutoff:errors.append('quote_after_T60')
    if (cutoff-quote).total_seconds()>max_age_seconds:errors.append('quote_too_stale')
    if snapshot.get('race_id')!=prediction.get('race_id'):errors.append('race_identity_mismatch')
    if forecast>cutoff:errors.append('prediction_after_T60')
    if timestamp(prediction['cutoff_utc'])!=cutoff:errors.append('prediction_cutoff_mismatch')
    if not prediction.get('model_version'):errors.append('missing_model_version')
    if 'training_data_through' not in prediction:
        errors.append('missing_training_boundary')
    elif timestamp(prediction['training_data_through'])>=cutoff:
        errors.append('training_boundary_not_before_cutoff')
    if snapshot.get('mapping_status')!='verified':errors.append('unverified_runner_mapping')
    odds=snapshot['decimal_odds'];probs=prediction['probabilities']
    if not isinstance(odds,dict) or not isinstance(probs,dict) or len(odds)<2 or set(odds)!=set(probs):
        errors.append('runner_field_mismatch')
    if not isinstance(odds,dict) or any(isinstance(o,bool) or not isinstance(o,(int,float)) or not math.isfinite(o) or o<=1 for o in odds.values()):
        errors.append('invalid_decimal_odds')
    if not isinstance(probs,dict) or any(not probability(p) for p in probs.values()) or abs(sum(probs.values())-1)>1e-6:
        errors.append('invalid_model_distribution')
    policy=dict(version='market-watch-v1',cutoff='scheduled start minus 60 minutes',
                min_probability_gap=min_gap,min_model_return_before_costs=min_model_return,
                max_quote_age_seconds=max_age_seconds,
                thresholds='Development defaults, not selected using betting outcomes')
    if errors:
        return dict(status='rejected',cutoff_utc=cutoff.isoformat(),reasons=errors,candidates=[],policy=policy)
    book_sum=sum(1/o for o in odds.values())
    comparisons=[]
    for rid,o in odds.items():
        fair=(1/o)/book_sum
        p=probs[rid];gap=p-fair;model_return=p*o-1
        comparisons.append(dict(runner_id=rid,decimal_odds=o,model_probability=p,
            break_even_probability=1/o,market_probability_proportional_devig=fair,
            probability_gap=gap,model_implied_return_before_costs=model_return,
            candidate=gap>=min_gap and model_return>=min_model_return))
    return dict(status='eligible',race_id=snapshot['race_id'],provider=snapshot['provider'],
        market_id=snapshot['market_id'],cutoff_utc=cutoff.isoformat(),book_probability_sum=book_sum,
        candidates=[r for r in comparisons if r['candidate']],comparisons=comparisons,policy=policy,
        interpretation='Research watchlist only. Proportional de-vig is an assumption. Model-implied returns '
            'exclude settlement deductions/costs and do not certify model accuracy, execution or profitability.')


def persist_check(out,snapshot,prediction,report):
    """One immutable decision directory per attempt; never overwrite a prior flag."""
    out=Path(out)
    out.mkdir(parents=True,exist_ok=False)
    for name,value in [('snapshot.json',snapshot),('prediction.json',prediction),('report.json',report)]:
        (out/name).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    manifest=dict(recorded_at=datetime.now(timezone.utc).isoformat(),
        snapshot_sha256=hashlib.sha256(canonical(snapshot).encode()).hexdigest(),
        prediction_sha256=hashlib.sha256(canonical(prediction).encode()).hexdigest(),
        report_sha256=hashlib.sha256(canonical(report).encode()).hexdigest(),
        source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        timestamp_trust='Imported capture metadata must be backed by its original receipt; this detector cannot authenticate it')
    (out/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')


def capture_export(source,out,*,clock=None):
    """Capture a provider-adapter export NOW. Never trust a supplied capture time.

    This is a local ingestion boundary, not a bookmaker scraper. The input must
    already contain source-native event/runner mapping and fixed decimal prices.
    """
    clock=clock or (lambda:datetime.now(timezone.utc))
    raw=Path(source).read_bytes()
    snapshot=json.loads(raw)
    captured=clock()
    if captured.tzinfo is None:raise ValueError('Timezone required')
    snapshot['captured_at']=captured.isoformat()
    snapshot['raw_response_sha256']=hashlib.sha256(raw).hexdigest()
    snapshot['capture_receipt_id']='local-export:'+snapshot['raw_response_sha256']
    out=Path(out);out.mkdir(parents=True,exist_ok=False)
    (out/'raw_export.json').write_bytes(raw)
    (out/'snapshot.json').write_text(json.dumps(snapshot,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
    return snapshot
