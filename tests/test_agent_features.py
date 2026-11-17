import json
from types import SimpleNamespace
import pytest
np=pytest.importorskip('numpy')
from horse_racing.agent_features import form_tokens,form_vector,validate_extraction,fit_offset,predict_offset,extraction_schema
from horse_racing.forecast_comparison import paired_model_market,score_predictions,reported_price_proxies


def fixture():
    packet=dict(date='2026-02-01',runners=[dict(runner_id='a',horse_name='Horse A (FR)',prior_form_raw='[01,00,NP]')])
    row=dict(runner_id='a',form_quote='[01,00,NP]',form_codes=['01','00','NP'],declared_debutant=False,
        preview_assessment='unknown',preview_source_id=None,preview_quote='',prior_trouble=None,
        trouble_source_id=None,trouble_quote='')
    return packet,row


def test_literal_codes_preserve_zeros_and_unknowns():
    assert form_tokens('[01,00,NP]')==(['01','00','NP'],False)
    assert form_tokens('[  Debutante   ]')==([],True)
    assert form_vector(['01','00','NP'],False)[2:4]==[1.,1.]
    assert form_vector(['01','00','NP'],False)[-1]==pytest.approx(2/3)


def test_schema_binds_form_quote_and_empty_corpus_unknowns():
    p,r=fixture();props=extraction_schema(p['runners'],[])['properties']['runners']['items']['properties']
    assert props['form_quote']['enum']==['[01,00,NP]']
    assert props['preview_assessment']['enum']==['unknown']
    assert props['prior_trouble']['type']=='null'


def test_unknown_is_not_negative_and_form_is_not_repaired():
    p,r=fixture();f=validate_extraction({'runners':[r]},p,[])
    assert f['a'][-5:]==[0.]*5
    r['form_codes'][0]='1'
    with pytest.raises(ValueError,match='literal source'):validate_extraction({'runners':[r]},p,[])


def test_duplicate_runner_rejected():
    p,r=fixture()
    with pytest.raises(ValueError,match='coverage'):validate_extraction({'runners':[r,r]},p,[])


@pytest.mark.parametrize('event',[None,'2026-02-01','2026-02-02'])
def test_trouble_requires_earlier_event(event):
    p,r=fixture();r.update(prior_trouble=True,trouble_source_id='s',trouble_quote='Horse A was blocked.')
    s=SimpleNamespace(id='s',text='Horse A was blocked.',provenance=json.dumps(dict(source_type='publisher_article',historical_event_date=event)))
    with pytest.raises(ValueError,match='earlier event'):validate_extraction({'runners':[r]},p,[SimpleNamespace(source=s)])


def test_preview_requires_target_date_and_exact_named_quote():
    p,r=fixture();r.update(preview_assessment='favourable',preview_source_id='s',preview_quote='Horse A looks strong.')
    s=SimpleNamespace(id='s',text=r['preview_quote'],provenance=json.dumps(dict(source_type='publisher_article',target_event_date=p['date'])))
    assert validate_extraction({'runners':[r]},p,[SimpleNamespace(source=s)])['a'][-5:]==[1.,0.,1.,0.,0.]
    r['preview_quote']='Horse A should win.'
    with pytest.raises(ValueError,match='quotation'):validate_extraction({'runners':[r]},p,[SimpleNamespace(source=s)])


def test_constant_features_preserve_baseline():
    c=dict(x=[[1.,0.],[1.,0.]],y=[1.,0.],baseline=[.3,.7])
    m=fit_offset([c]*5,steps=30)
    assert predict_offset(c,m)==pytest.approx(c['baseline'])


def test_paired_errors_use_same_outcomes_and_full_fields():
    labels={'r':{'a':1.,'b':0.}}
    predictions={'r':{'a':.7,'b':.3}}
    markets={'r':{'probabilities':{'a':.6,'b':.4}},'absent':{'probabilities':{'a':1.}}}
    report=paired_model_market(predictions,labels,markets,evidence_tier='test')
    assert report['paired_races']==1
    assert report['metrics']['model_minus_market_brier']==pytest.approx(.18-.32)
    assert report['metrics']['model_market_squared_distance']==pytest.approx(.02)
    assert report['exclusions']=={'absent':'missing_model_or_label'}
    markets['r']['probabilities'].pop('b')
    assert paired_model_market(predictions,labels,markets,evidence_tier='test')['paired_races']==0
    assert score_predictions({'r':{'a':1.}},labels)[0]['valid_races']==0


def test_price_proxy_excludes_incomplete_fields_and_suspected_margins(tmp_path):
    import sqlite3
    db=tmp_path/'prices.sqlite';c=sqlite3.connect(db)
    c.executescript('''CREATE TABLE latest_results(id,race_id,horse_id,race_version_id);
      CREATE TABLE result_details(result_id,dividend_raw,time_or_margin_raw);
      CREATE TABLE race_versions(id,snapshot_id);
      CREATE TABLE snapshots(id,url,sha256,observed_at);
      INSERT INTO latest_results VALUES('a','r','ha','v'),('b','r','hb','v');
      INSERT INTO result_details VALUES('a','2,0','1:40'),('b','4,0','2');
      INSERT INTO race_versions VALUES('v','s');
      INSERT INTO snapshots VALUES('s','https://example.test','hash','2026-11-11');''')
    c.commit()
    cases={'r':dict(source_race_id='r',runner_mapping={'a':'ha','b':'hb'})}
    packets=[dict(race_id='r',runners=[dict(runner_id='a'),dict(runner_id='b')])]
    markets,excluded,receipts=reported_price_proxies(db,cases,packets)
    assert not excluded and len(receipts)==2
    assert markets['r']['probabilities']==pytest.approx({'a':2/3,'b':1/3})
    assert markets['r']['quote_at'] is None
    c.execute("UPDATE result_details SET time_or_margin_raw='4,0' WHERE result_id='b'");c.commit()
    assert not reported_price_proxies(db,cases,packets)[0]
    c.close()
    cases['r']['runner_mapping'].pop('b')
    assert reported_price_proxies(db,cases,packets)[1]['r'][0]['reason']=='no_reported_price_for_declared_runner'
