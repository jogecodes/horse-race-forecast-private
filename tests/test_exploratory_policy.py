"""Exploratory semantics must preserve unknown dates and the admission boundary."""
import json
from dataclasses import asdict,replace
from pathlib import Path
import pytest
from horse_racing.engine.model import Audit
from horse_racing.engine.publications import publisher_source,date_claim
from horse_racing.engine.leakage import JudgePanel,provenance_reasons,deterministic_gate
from horse_racing.engine.discovery import Explorer
from horse_racing.engine.pipeline import forecast
from horse_racing.engine.run import audit_run,run_benchmark
from horse_racing.benchmark import digest

TEXT='ALPHA finished second in an earlier race on 2025-11-01 over 1200 metres. The earlier performance informs distance suitability.'
URL='https://publisher.example/earlier-form'
RESPONSE=dict(observed_at='2026-11-05T12:00:00Z',sha256='test_hash')
TASK=dict(race_id='test',date='2026-01-04',venue='La Zarzuela',cutoff_utc='2026-01-03T22:59:00Z',track='publisher_documented',runners=[dict(runner_id='a',horse_name='ALPHA'),dict(runner_id='b',horse_name='BETA')])


def unknown(claims=()):
    return publisher_source(URL,RESPONSE,[TEXT],claims,allow_undated=True)


class Model:
    def __init__(self,verdict='allow',quotes=None):self.calls=[];self.verdict=verdict;self.quotes=quotes
    def complete(self,model,role,system,payload,**kwargs):
        self.calls.append(dict(role=role,payload=payload,system=system))
        if role=='planner':return json.dumps({'needs':[dict(id=1,need='Earlier ALPHA form',query='ALPHA',urls=[])]})
        if role.startswith('judge_'):
            return json.dumps(dict(verdict=self.verdict,reason='Assessment of the supplied earlier race.',supporting_quotes=[TEXT[:60]] if self.quotes is None else self.quotes))
        if role=='selector':return json.dumps(dict(sentence_ids=[payload['candidates'][0]['sentence_id']]))
        if role=='forecaster':return json.dumps(dict(race_id='test',probabilities=dict(a=.6,b=.4)))
        raise AssertionError(role)


def test_unknown_publication_is_none_and_only_exploratory_accepts_receipt():
    s=unknown()
    assert s.available_at is None and s.receipt['claimed_available_at'] is None
    assert provenance_reasons(s,TASK['cutoff_utc'],'exploratory')==[]
    for policy in ('strict','publisher-dated'):
        assert provenance_reasons(s,TASK['cutoff_utc'],policy)==['unverified_dating_requires_exploratory_policy']
    assert provenance_reasons(replace(s,available_at=TASK['cutoff_utc']),TASK['cutoff_utc'],'exploratory')


def test_partial_late_modification_is_still_a_hard_block(tmp_path):
    s=unknown([date_claim('2026-02-01T12:00:00Z','meta:modified','modified')])
    model=Model();r=JudgePanel(model,Audit(tmp_path/'a.jsonl'),policy='exploratory').assess(TASK,{},s,TEXT)
    assert r['decision']=='reject' and not model.calls
    assert 'source_date_claim_after_cutoff' in r['hard']['reasons']


def test_exploratory_uses_semantics_for_future_text_but_preserves_source_dates(tmp_path):
    s=publisher_source(URL,RESPONSE,[TEXT],[date_claim('2025-12-01T12:00:00Z','meta')])
    mixed='ALPHA won earlier on 2025-11-01. A race on 2026-01-04 is mentioned without a clear event relation.'
    assert not deterministic_gate(s,mixed,TASK['cutoff_utc'],'publisher-dated')['allow']
    assert deterministic_gate(s,mixed,TASK['cutoff_utc'],'exploratory')['allow']
    late=publisher_source(URL,RESPONSE,[TEXT],[date_claim('2026-01-05T12:00:00Z','meta')])
    assert not deterministic_gate(late,TEXT,TASK['cutoff_utc'],'exploratory')['allow']


@pytest.mark.parametrize('verdict,quotes,decision',[('uncertain',[],'uncertain'),('drop',[TEXT[:60]],'reject'),('allow',['INVENTED QUOTE'],'uncertain'),('allow',[],'uncertain')])
def test_uncertain_or_unsupported_judgments_never_admit(tmp_path,verdict,quotes,decision):
    m=Model(verdict,quotes);r=JudgePanel(m,Audit(tmp_path/'a.jsonl'),policy='exploratory').assess(TASK,{},unknown(),TEXT)
    assert not r['allow'] and r['decision']==decision
    assert len(r['votes'])==3


def test_unknown_dating_flows_through_pipeline_and_audit_without_invented_timestamp(tmp_path):
    s=unknown();audit=Audit(tmp_path/'ledger.jsonl');audit.log('source',source=asdict(s));m=Model()
    class Researcher:
        def search(self,*args,**kwargs):return [s]
    result=forecast(TASK,m,Researcher(),JudgePanel(m,audit,policy='exploratory'),audit,rounds=1,known_winners=['CONFIDENTIAL'])
    assert result['approved_items']==result['selected_items']==1
    final=next(c['payload'] for c in m.calls if c['role']=='forecaster')
    assert final['approved_evidence'][0]['available_at'] is None
    assert final['research_status']['dating_policy']=='exploratory'
    for call in m.calls:
        assert ('CONFIDENTIAL' in json.dumps(call['payload']))==(call['role']=='judge_outcome')
    manifest=dict(research_policy='exploratory',ledger_sha256={'ledger.jsonl':digest(audit.path)})
    (tmp_path/'run_manifest.json').write_text(json.dumps(manifest))
    assert audit_run(tmp_path)['status']=='passed'
    manifest['research_policy']='publisher-dated';(tmp_path/'run_manifest.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError,match='policy differs'):audit_run(tmp_path)


def test_uncertain_text_stays_out_of_predictor_and_selector(tmp_path):
    m=Model('uncertain',[]);audit=Audit(tmp_path/'ledger.jsonl')
    class Researcher:
        def search(self,*args,**kwargs):return [unknown()]
    result=forecast(TASK,m,Researcher(),JudgePanel(m,audit,policy='exploratory'),audit,rounds=1)
    assert result['prediction'] and result['approved_items']==0
    assert all(TEXT not in json.dumps(c['payload']) for c in m.calls if c['role'] in ('selector','forecaster'))


def test_discovery_only_keeps_undated_body_with_explicit_exploratory_policy(tmp_path):
    html='<article><p>'+TEXT+'</p></article>'
    for policy in ('publisher-dated','exploratory'):
        r=Explorer(tmp_path/policy,Audit(tmp_path/(policy+'.jsonl')),None,TASK,policy=policy)
        r.registered.add(URL);r.get=lambda *args,**kwargs:dict(RESPONSE,text=html,url=URL)
        if policy=='publisher-dated':
            with pytest.raises(ValueError,match='No supported'):r.page(URL,TASK['cutoff_utc'])
        else:
            s=r.page(URL,TASK['cutoff_utc']);assert s.available_at is None and s.passages==(TEXT,)


def test_strict_track_cannot_select_exploratory_policy(tmp_path):
    bundle=Path(__file__).resolve().parents[1]/'benchmarks/h1_2026_v2'
    with pytest.raises(ValueError,match='Strict runs require'):
        run_benchmark(bundle,tmp_path/'strict',track='strict',research_policy='exploratory')


def test_audit_rechecks_quotes_even_when_outer_hashes_are_updated(tmp_path):
    import hashlib
    s=unknown();audit=Audit(tmp_path/'ledger.jsonl');audit.log('source',source=asdict(s));m=Model()
    class Researcher:
        def search(self,*args,**kwargs):return [s]
    forecast(TASK,m,Researcher(),JudgePanel(m,audit,policy='exploratory'),audit,rounds=1)
    rows=[json.loads(line) for line in audit.path.read_text().splitlines()]
    previous='0'*64
    for row in rows:
        row.pop('event_sha256');row['previous_sha256']=previous
        if row['event']=='judge_panel':row['votes'][0]['supporting_quotes']=['FABRICATED SUPPORT']
        row['event_sha256']=hashlib.sha256(json.dumps(row,ensure_ascii=False,sort_keys=True,allow_nan=False).encode()).hexdigest()
        previous=row['event_sha256']
    audit.path.write_text(''.join(json.dumps(row,ensure_ascii=False)+'\n' for row in rows))
    (tmp_path/'run_manifest.json').write_text(json.dumps(dict(research_policy='exploratory',ledger_sha256={'ledger.jsonl':digest(audit.path)})))
    with pytest.raises(ValueError,match='exact supporting quotes'):audit_run(tmp_path)
