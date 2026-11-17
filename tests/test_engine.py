import json
from pathlib import Path
import pytest
from horse_racing.engine.model import Audit
from horse_racing.engine.sources import Source,allowed_url,literal_prose,html_passages
from horse_racing.engine.leakage import provenance_reasons,deterministic_gate,JudgePanel,date_alarms
from horse_racing.engine.pipeline import public_task,strict_roster,forecast,select
from horse_racing.engine.run import audit_run
from horse_racing.db import initialize

TASK=dict(benchmark_version='synthetic',race_id='test_race',date='2026-01-10',venue='Synthetic Venue',split='development',
 cutoff_utc='2026-01-09T22:59:00+00:00',distance_m=1200,track='retrospective_diagnostic',
 input_availability='unverified_result_reconstruction',runners=[
 dict(runner_id='a',horse_name='ALPHA'),dict(runner_id='b',horse_name='BETA'),dict(runner_id='c',horse_name='GAMMA')])


def source(text='ALPHA had consistent earlier form over this distance before the cutoff. The trainer prepared ALPHA for similar conditions.',when='2026-01-08T12:00:00Z'):
    return Source('s1','https://www.todoturf.net/example',when,when,'live',dict(kind='live',observed_at=when),'hash',(text,))


class FakeModel:
    def __init__(self,drop_role=None,final=None):self.calls=[];self.drop_role=drop_role;self.final=final
    def complete(self,model,role,system,payload,**kwargs):
        self.calls.append(dict(role=role,payload=payload))
        if role=='planner':return json.dumps(dict(needs=[dict(id=1,need='Earlier ALPHA form',query='ALPHA form',urls=[])]))
        if role.startswith('judge_'):
            return json.dumps(dict(verdict='drop' if role==self.drop_role else 'allow',reason='Synthetic test judgment'))
        if role=='selector':return json.dumps(dict(sentence_ids=[payload['candidates'][0]['sentence_id']]))
        if role=='forecaster':return self.final or json.dumps(dict(race_id='test_race',probabilities=dict(a=.5,b=.3,c=.2)))
        raise AssertionError(role)


class FakeResearcher:
    def __init__(self,s):self.s=s
    def search(self,*args,**kwargs):return [self.s]


def test_source_times_cannot_be_overridden():
    late=source(when='2026-01-11T00:00:00Z')
    assert 'source_available_after_cutoff' in provenance_reasons(late,TASK['cutoff_utc'])
    assert not deterministic_gate(source('ALPHA won on 2026-01-10.'), 'ALPHA won on 2026-01-10.',TASK['cutoff_utc'])['allow']


def test_spanish_and_english_dates_are_code_owned():
    for text in ['El 10 de enero de 2026 ALPHA ganó.','On January 10, 2026 ALPHA won.','El 10/01/2026 ganó.']:
        assert date_alarms(text,TASK['cutoff_utc'])['explicit_future_dates']
    assert date_alarms('El 10 de enero ganó.',TASK['cutoff_utc'])['yearless_future_dates']


def test_false_archive_claim_is_rejected():
    s=Source('x','https://www.todoturf.net/example','2026-01-01T00:00:00Z','2026-11-01T00:00:00Z','wayback',
      dict(kind='wayback',timestamp='2026-01-01T00:00:00Z',capture_stamp='20260101000000',
           capture_url='https://example.invalid/fake',original_url='https://www.todoturf.net/example',status=200,mime='text/html'),'h',('text',))
    assert 'archive_provenance_mismatch' in provenance_reasons(s,TASK['cutoff_utc'])


def test_real_shape_archived_receipt_uses_capture_not_collection_date():
    original='https://www.todoturf.net/example';stamp='20260101000000';when='2026-01-01T00:00:00Z'
    s=Source('x',original,when,'2026-11-01T00:00:00Z','wayback',dict(kind='wayback',timestamp=when,
       capture_stamp=stamp,capture_url=f'https://web.archive.org/web/{stamp}id_/{original}',original_url=original,status=200,mime='text/html'),'h',('text',))
    assert provenance_reasons(s,TASK['cutoff_utc'])==[]


def test_judge_error_or_one_veto_blocks(tmp_path):
    for role in ['judge_outcome','judge_provenance','judge_relevance']:
        audit=Audit(tmp_path/f'{role}.jsonl');model=FakeModel(drop_role=role)
        result=JudgePanel(model,audit).assess(TASK,{'need':'Earlier ALPHA form'},source(),source().passages[0])
        assert not result['allow'] and len(result['votes'])==3
    class Bad(FakeModel):
        def complete(self,*args,**kwargs):return '{}'
    assert not JudgePanel(Bad(),Audit(tmp_path/'bad.jsonl')).assess(TASK,{},source(),source().passages[0])['allow']


def test_time_drop_invokes_no_judges(tmp_path):
    model=FakeModel();panel=JudgePanel(model,Audit(tmp_path/'a.jsonl'))
    result=panel.assess(TASK,{},source(when='2026-11-05T00:00:00Z'),'Late text')
    assert not result['allow'] and not model.calls


def test_known_labels_only_go_to_outcome_judge(tmp_path):
    model=FakeModel();audit=Audit(tmp_path/'ledger.jsonl');panel=JudgePanel(model,audit)
    result=forecast(TASK,model,FakeResearcher(source()),panel,audit,rounds=1,known_winners=['SECRET_GOLD_WINNER'])
    assert result['prediction'] and result['selected_items']==1
    for call in model.calls:
        has='SECRET_GOLD_WINNER' in json.dumps(call['payload'])
        assert has==(call['role']=='judge_outcome')
    final=next(c['payload'] for c in model.calls if c['role']=='forecaster')
    assert final['approved_evidence'][0]['paragraph_context']==source().passages[0]
    assert 'Synthetic test judgment' not in json.dumps(final)


def test_dropped_text_never_reaches_selector_or_forecaster(tmp_path):
    secret='ALPHA leaked outcome UNIQUE_DROPPED_TOKEN.'
    model=FakeModel(drop_role='judge_outcome');audit=Audit(tmp_path/'a.jsonl')
    r=forecast(TASK,model,FakeResearcher(source(secret)),JudgePanel(model,audit),audit,rounds=1)
    assert r['selected_items']==0 and r['prediction']
    assert all('UNIQUE_DROPPED_TOKEN' not in json.dumps(c['payload']) for c in model.calls if c['role'] in ('selector','forecaster'))


def test_late_source_never_reaches_any_judge_or_downstream_model(tmp_path):
    model=FakeModel();audit=Audit(tmp_path/'a.jsonl')
    r=forecast(TASK,model,FakeResearcher(source('LATE_SECRET',when='2026-11-05T00:00:00Z')),JudgePanel(model,audit),audit,rounds=1)
    assert r['approved_items']==0
    assert not any(c['role'].startswith('judge_') for c in model.calls)
    assert all('LATE_SECRET' not in json.dumps(c['payload']) for c in model.calls)


def test_public_whitelist_strips_gold_and_judge_metadata():
    p=dict(TASK,label='SECRET',known_winners=['SECRET'],judge_reply='SECRET')
    p['runners']=[dict(r,label='SECRET',finish_position=1) for r in TASK['runners']]
    assert 'SECRET' not in json.dumps(public_task(p))
    assert all('finish_position' not in r for r in public_task(p)['runners'])


def test_unparseable_forecasts_excluded_not_repaired(tmp_path):
    for i,raw in enumerate(['bad','{}','{"race_id":"test_race","probabilities":{"a":0.5,"b":0.5}}',
       '{"race_id":"test_race","probabilities":{"a":0.4,"b":0.3,"c":0.2}}']):
        audit=Audit(tmp_path/f'{i}.jsonl');model=FakeModel(final=raw)
        r=forecast(TASK,model,FakeResearcher(source()),JudgePanel(model,audit),audit,research=False)
        assert r['prediction'] is None and r['error']


def test_no_unknown_selector_id_can_inject_evidence(tmp_path):
    class Bad(FakeModel):
        def complete(self,*args,**kwargs):return '{"sentence_ids":["invented"]}'
    audit=Audit(tmp_path/'a.jsonl')
    assert select(Bad(),audit,TASK,[dict(item_id='x',text='Unrelated sentence.',source_id='s',available_at=TASK['cutoff_utc'],need_id=1)],'fake')==[]


def test_url_allowlist_blocks_local_and_untrusted_destinations():
    assert allowed_url('https://www.todoturf.net/resultados.php')
    for url in ['http://www.todoturf.net/a','https://127.0.0.1/a','https://www.todoturf.net.evil.test/a',
                'https://user:pass@www.todoturf.net/a','https://www.todoturf.net:444/a']:
        assert not allowed_url(url)


def test_wikipedia_templates_and_current_resources_not_expanded():
    prose='ALPHA is a racehorse with earlier form relevant to racing at this track. This literal paragraph has no templates.'
    assert literal_prose(prose+'\n\n{{CurrentCareerStatistics}}')[0]==prose
    assert literal_prose(prose+' {{CurrentCareerStatistics}}')==()
    assert 'BAD' not in str(html_passages('<script>BAD</script><p>'+prose+'</p>'))


def test_missing_strict_roster_does_not_trust_packet_flag(tmp_path):
    db=tmp_path/'r.sqlite';initialize(db).close()
    p=dict(TASK,verified=True)
    assert not strict_roster(db,'not-real',p)['verified']


def test_audit_source_hash_does_not_collide_with_event_hash(tmp_path):
    import hashlib
    a=Audit(tmp_path/'ledger.jsonl');a.log('source',sha256='SOURCE_CONTENT_HASH')
    row=json.loads(a.path.read_text());claimed=row.pop('event_sha256')
    assert row['sha256']=='SOURCE_CONTENT_HASH'
    assert claimed==hashlib.sha256(json.dumps(row,ensure_ascii=False,sort_keys=True,allow_nan=False).encode()).hexdigest()


def test_json_contract_rejects_duplicate_keys_and_nonfinite_values():
    from horse_racing.engine.model import json_reply
    for raw in ['{"x":1,"x":2}','{"x":NaN}','{"x":Infinity}']:
        with pytest.raises(ValueError):json_reply(raw)


def test_declared_task_requires_pre_cutoff_collected_declaration(tmp_path):
    from horse_racing.engine.declared import declaration_task
    db=tmp_path/'r.sqlite';c=initialize(db)
    c.execute("INSERT INTO sources VALUES('s','Synthetic','https://example.test','','')")
    c.execute("INSERT INTO snapshots VALUES('snap','s','https://example.test','2026-01-08T12:00:00+00:00',NULL,'text/html','synthetic','h','test')")
    c.execute("INSERT INTO meetings VALUES('m','s','m','2026-01-10','Test Venue','Europe/Madrid')")
    c.execute("INSERT INTO races VALUES('race','m',1)")
    c.execute("INSERT INTO race_versions VALUES('v','race','snap','declaration','1','Test',1200,'','')")
    for i in (1,2,3):
        c.execute("INSERT INTO entities VALUES(?, 'horse',?,'test')",(f'h{i}',f'HORSE {i}'))
        c.execute("INSERT INTO entries VALUES(?, 'v', ?, ?, NULL,NULL,NULL,NULL,NULL,?,'',1,'')",(f'e{i}',i,f'h{i}',int(i==3)))
    c.commit();c.close()
    with pytest.raises(ValueError,match='No collected'):declaration_task(db,'race','2026-01-07T00:00:00Z')
    with pytest.raises(ValueError,match='before race day'):declaration_task(db,'race','2026-01-10T00:00:00Z')
    task,proof=declaration_task(db,'race','2026-01-09T22:59:00Z')
    assert task['track']=='strict' and len(task['runners'])==2 and proof['snapshot_id']=='snap'
    assert 'history_through_2025' not in json.dumps(task)
    fake_packet=dict(task,venue='POST_RESULT_VENUE',distance_m=9999)
    checked=strict_roster(db,'race',fake_packet)
    assert checked['verified']
    assert checked['task']['distance_m']==1200 and checked['task']['venue']=='Test Venue'


def test_audit_rejects_modified_ledger_and_preserves_source_hash(tmp_path):
    from horse_racing.benchmark import digest
    audit=Audit(tmp_path/'ledger.jsonl');audit.log('source',sha256='SOURCE')
    manifest=dict(ledger_sha256={'ledger.jsonl':digest(audit.path)})
    (tmp_path/'run_manifest.json').write_text(json.dumps(manifest))
    assert audit_run(tmp_path)['status']=='passed'
    row=json.loads(audit.path.read_text());row['sha256']='CHANGED'
    audit.path.write_text(json.dumps(row)+'\n')
    # Even an updated outer file digest cannot hide a broken event chain.
    manifest['ledger_sha256']['ledger.jsonl']=digest(audit.path)
    (tmp_path/'run_manifest.json').write_text(json.dumps(manifest))
    with pytest.raises(ValueError,match='event hash'):audit_run(tmp_path)


def test_audit_checks_positive_evidence_chain_and_rejects_substitution(tmp_path):
    from dataclasses import asdict
    from horse_racing.engine.pipeline import sentence_pool
    from horse_racing.benchmark import digest
    from horse_racing.db import uid
    def build(directory,alter):
        directory.mkdir();audit=Audit(directory/'ledger.jsonl');s=source();text=s.passages[0]
        item=uid(s.source_id,text)
        audit.log('source',source=asdict(s))
        audit.log('judge_panel',item_id=item,allow=True,hard=dict(allow=True),source_id=s.source_id,text=text,
                  votes=[dict(role=r,verdict='allow') for r in ('provenance','outcome','relevance')])
        approved=dict(item_id=item,text=text,source_id=s.source_id,available_at=s.available_at,need_id=1)
        selected=sentence_pool([approved])[:1];audit.log('selected_evidence',selected=selected)
        if alter:selected[0]=dict(selected[0],text='ALTERED OUTCOME')
        payload=dict(task=public_task(TASK),approved_evidence=selected)
        audit.log('final_forecaster_input',payload=payload)
        audit.log('model_request',role='forecaster',request=dict(messages=[dict(role='user',content=json.dumps(payload))]))
        (directory/'run_manifest.json').write_text(json.dumps(dict(ledger_sha256={'ledger.jsonl':digest(audit.path)})))
        return directory
    assert audit_run(build(tmp_path/'good',False))['status']=='passed'
    with pytest.raises(ValueError,match='altered evidence'):audit_run(build(tmp_path/'bad',True))


def test_research_outage_still_forecasts_without_invented_evidence(tmp_path):
    class Unavailable:
        def search(self,*args,**kwargs):raise ValueError('Public source unavailable')
    m=FakeModel();audit=Audit(tmp_path/'ledger.jsonl')
    result=forecast(TASK,m,Unavailable(),JudgePanel(m,audit),audit,rounds=1)
    assert result['prediction'] and result['approved_items']==result['selected_items']==0
    payload=[c['payload'] for c in m.calls if c['role']=='forecaster'][0]
    assert payload['approved_evidence']==[] and 'Public source unavailable' not in json.dumps(payload)


def test_short_aliases_preserve_values_and_bounded_retry_without_repair(tmp_path):
    class Aliased(FakeModel):
        requires_short_runner_ids=True
        def complete(self,model,role,system,payload,**kwargs):
            if role!='forecaster':return super().complete(model,role,system,payload,**kwargs)
            self.calls.append(dict(role=role,payload=json.loads(json.dumps(payload))))
            probabilities=dict(r1=.4,r2=.4,r3=.4) if 'output_validation' not in payload else dict(r1=.6,r2=.3,r3=.1)
            return json.dumps(dict(race_id='test_race',probabilities=probabilities))
    m=Aliased();audit=Audit(tmp_path/'ledger.jsonl')
    result=forecast(TASK,m,None,None,audit,research=False)
    assert result['prediction']['probabilities']==dict(a=.6,b=.3,c=.1)
    assert result['forecast_attempts']==2 and result['invalid_attempts']==1
    assert [c['payload']['task']['runners'][0]['runner_id'] for c in m.calls]==['r1','r1']
    assert m.calls[1]['payload']['output_validation']['previous_sum']==pytest.approx(1.2)


def test_audit_checks_alias_mapping_and_exact_unrepaired_model_values(tmp_path):
    from horse_racing.benchmark import digest
    import copy
    def build(directory,alter):
        directory.mkdir();audit=Audit(directory/'ledger.jsonl');task=public_task(TASK)
        mapping=dict(r1='a',r2='b',r3='c');aliased=copy.deepcopy(task)
        for i,r in enumerate(aliased['runners']):r['runner_id']=f'r{i+1}'
        audit.log('forecast_runner_map',mapping=mapping,original_task=task)
        payload=dict(task=aliased,approved_evidence=[]);audit.log('final_forecaster_input',payload=payload)
        audit.log('model_request',role='forecaster',request=dict(messages=[dict(role='user',content=json.dumps(payload))]))
        audit.log('model_response',role='forecaster',text=json.dumps(dict(race_id=task['race_id'],probabilities=dict(r1=.5,r2=.3,r3=.2))))
        probabilities=dict(a=.5,b=.3,c=.2) if not alter else dict(a=.3,b=.5,c=.2)
        audit.log('forecast_valid',prediction=dict(race_id=task['race_id'],probabilities=probabilities))
        (directory/'run_manifest.json').write_text(json.dumps(dict(ledger_sha256={'ledger.jsonl':digest(audit.path)})))
        return directory
    assert audit_run(build(tmp_path/'good',False))['status']=='passed'
    with pytest.raises(ValueError,match='differs from model'):audit_run(build(tmp_path/'bad',True))


def test_discovered_articles_reach_judges_and_forecaster_but_search_snippets_do_not(tmp_path):
    from horse_racing.engine.discovery import Explorer
    from horse_racing.engine.publications import public_url
    url='https://publisher.example/earlier-alpha-form'
    searches=[]
    def provider(query,cutoff,kind):
        searches.append((query,cutoff,kind))
        return [dict(url=url,title='Earlier ALPHA reporting',snippet='SECRET_SEARCH_ONLY_TARGET_WINNER')] if 'ALPHA' in query else []
    class ResearchModel(FakeModel):
        def complete(self,model,role,system,payload,**kwargs):
            if role=='researcher':
                self.calls.append(dict(role=role,payload=payload));return '{"queries":[]}'
            if role=='researcher_select':
                self.calls.append(dict(role=role,payload=payload));return json.dumps(dict(candidate_ids=[payload['candidates'][0]['candidate_id']]))
            return super().complete(model,role,system,payload,**kwargs)
    m=ResearchModel();audit=Audit(tmp_path/'ledger.jsonl')
    researcher=Explorer(tmp_path/'cache',audit,m,public_task(TASK),policy='publisher-dated',search_provider=provider,max_queries=4)
    html='<meta property="article:published_time" content="2025-12-20T12:00:00Z"><article><p>ALPHA had consistent earlier form over this distance before the cutoff. Earlier preparations were suitable for these conditions.</p></article>'
    def get(original,params=None):
        assert original==url and public_url(original)
        return dict(url=url,text=html,sha256='fixture_body_hash',observed_at='2026-11-05T12:00:00Z')
    researcher.get=get
    result=forecast(TASK,m,researcher,JudgePanel(m,audit,policy='publisher-dated'),audit,rounds=1)
    assert searches and result['approved_items']==result['selected_items']==1
    roles=[c['role'] for c in m.calls]
    assert all(r in roles for r in ('researcher','researcher_select','judge_provenance','judge_outcome','judge_relevance','selector','forecaster'))
    final=[c['payload'] for c in m.calls if c['role']=='forecaster'][0]
    assert final['approved_evidence'][0]['evidence_strength']=='publisher_dated'
    assert 'ALPHA had consistent earlier form' in json.dumps(final)
    assert 'SECRET_SEARCH_ONLY_TARGET_WINNER' not in json.dumps(final)
