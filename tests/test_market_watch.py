from copy import deepcopy
from datetime import datetime,timezone
import json
import pytest
from horse_racing.market_watch import inspect_market,persist_check,capture_export


@pytest.fixture
def inputs():
    snapshot=dict(race_id='invented-race',provider='synthetic-fixture',market_id='win-1',
        source_url='https://example.invalid/fixture',price_type='fixed',market='win',status='open',in_play=False,
        scheduled_start_at='2026-11-15T14:00:00Z',schedule_known_at='2026-11-14T12:00:00Z',
        schedule_source='invented schedule',quote_at='2026-11-15T12:59:00Z',captured_at='2026-11-15T12:59:30Z',
        raw_response_sha256='fixture-only',capture_receipt_id='synthetic-receipt',mapping_status='verified',
        decimal_odds={'a':4.,'b':2.,'c':3.})
    prediction=dict(race_id='invented-race',created_at='2026-11-15T12:58:00Z',
        cutoff_utc='2026-11-15T13:00:00Z',model_version='test-only',
        training_data_through='2025-12-31T23:59:59Z',probabilities={'a':.4,'b':.3,'c':.3})
    return snapshot,prediction


def test_flag_has_gap_and_positive_before_cost_return(inputs):
    snapshot,prediction=inputs
    r=inspect_market(snapshot,prediction)
    assert r['status']=='eligible'
    assert [x['runner_id'] for x in r['candidates']]==['a']
    assert r['candidates'][0]['model_implied_return_before_costs']==pytest.approx(.6)


@pytest.mark.parametrize('field,value,reason',[
    ('captured_at','2026-11-15T13:00:01Z','capture_after_T60'),
    ('quote_at','2026-11-15T13:01:00Z','quote_after_T60'),
    ('quote_at','2026-11-15T12:00:00Z','quote_too_stale'),
    ('price_type','pool','requires_fixed_odds_win_market'),
    ('in_play',True,'market_not_open_pre_race'),
    ('mapping_status','unverified','unverified_runner_mapping')])
def test_invalid_markets_rejected(inputs,field,value,reason):
    s,p=inputs;s[field]=value
    r=inspect_market(s,p)
    assert r['status']=='rejected' and reason in r['reasons'] and r['candidates']==[]


def test_margin_can_make_market_disagreement_unprofitable(inputs):
    s,p=inputs;s['decimal_odds']={'a':2.,'b':2.};p['probabilities']={'a':.55,'b':.45}
    # Heavy book margin: fair market p=.5, but raw break-even p=.625.
    s['decimal_odds']={'a':1.6,'b':1.6}
    r=inspect_market(s,p)
    assert r['comparisons'][0]['probability_gap']>.03
    assert not r['candidates']


def test_missing_horse_late_forecast_and_bad_distribution(inputs):
    s,p=inputs;s['decimal_odds'].pop('c');p['created_at']='2026-11-15T13:01:00Z';p['probabilities']['a']=.9
    r=inspect_market(s,p)
    assert {'runner_field_mismatch','prediction_after_T60','invalid_model_distribution'}<=set(r['reasons'])


def test_record_cannot_overwrite_and_capture_cannot_be_backdated(inputs,tmp_path):
    s,p=inputs
    raw=tmp_path/'export.json';raw.write_text(json.dumps(s))
    captured=capture_export(raw,tmp_path/'capture',clock=lambda:datetime(2026,11,15,13,5,tzinfo=timezone.utc))
    assert 'capture_after_T60' in inspect_market(captured,p)['reasons']
    r=inspect_market(s,p);persist_check(tmp_path/'decision',s,p,r)
    with pytest.raises(FileExistsError):persist_check(tmp_path/'decision',s,p,r)
