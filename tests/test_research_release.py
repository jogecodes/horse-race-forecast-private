import pytest
np=pytest.importorskip('numpy')
from horse_racing.research_release import feature_case,fit_arms,paired_interval,reliability


def packet(rid,date):
    return dict(race_id=rid,date=date,runners=[dict(runner_id='a',prior_form_raw='[01,02]'),dict(runner_id='b',prior_form_raw='[03,04]')])


def test_failed_optional_extraction_keeps_form_and_race():
    p=packet('r','2026-01-01');b={'a':.4,'b':.6};y={'a':1.,'b':0.}
    literal=feature_case(p,b,y)
    augmented=feature_case(p,b,y,dict(status='failed',error='bad quote'),augmented=True)
    assert [v[:6] for v in augmented['x']]==literal['x']
    assert all(v[6:]==[0.]*5 for v in augmented['x'])
    assert augmented['runner_ids']==literal['runner_ids']


def test_no_article_signal_and_partial_failures_preserve_predictions():
    packets=[packet('jan1','2026-01-01'),packet('jan2','2026-01-02'),packet('feb','2026-02-01')]
    base={p['race_id']:{'a':.4,'b':.6} for p in packets};labels={p['race_id']:{'a':1.,'b':0.} for p in packets}
    predictions,models=fit_arms(packets,base,labels,{'jan1':dict(status='failed')})
    assert models['optional_agent']['training_ids']==models['deterministic_form']['training_ids']==['jan1','jan2']
    assert predictions['optional_agent']['feb']==pytest.approx(predictions['deterministic_form']['feb'])


def test_paired_bootstrap_identity_and_mismatched_cohort():
    p={'r':{'a':.4,'b':.6},'s':{'a':.2,'b':.8}};y={k:{'a':1.,'b':0.} for k in p}
    result=paired_interval(p,p,y,{'r':'meeting','s':'meeting'},samples=20)
    assert result['meeting_clusters']==1
    assert result['brier']==dict(difference=0.,interval_95=[0.,0.])
    with pytest.raises(ValueError,match='cohorts'):paired_interval(p,{'r':p['r']},y,{'r':'m'})


def test_reliability_includes_probability_one_and_empty_bins():
    r=reliability({'r':{'a':1.,'b':0.}},{'r':{'a':1.,'b':0.}})
    assert r['runners']==2 and r['ece']==0
    assert r['bins'][-1]['count']==1
    assert r['bins'][3]['mean_probability'] is None
