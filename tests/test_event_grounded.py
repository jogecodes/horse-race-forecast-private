import copy,json,hashlib
from dataclasses import asdict
import pytest
from horse_racing.engine.events import context,sentences,resolution_gate,resolver_schema
from horse_racing.engine.publications import publisher_source
from horse_racing.engine.model import Audit
from horse_racing.engine.leakage import JudgePanel
from horse_racing.engine.pipeline import forecast
from horse_racing.engine.run import audit_run
from horse_racing.benchmark import digest

TEXT='ALPHA finished second on 2025-11-01 over 1200 metres. The earlier performance informs distance suitability.'
TASK=dict(race_id='test',date='2026-01-04',venue='La Zarzuela',cutoff_utc='2026-01-03T22:59:00Z',track='publisher_documented',runners=[dict(runner_id='a',horse_name='ALPHA'),dict(runner_id='b',horse_name='BETA')])

def source(text=TEXT):
 return publisher_source('https://publisher.example/form',dict(observed_at='2026-11-06T12:00:00Z',sha256='fixture'),[text],[],allow_undated=True)

def claims(payload,relation='other',when='before',supports=None):
 return dict(claims=[dict(sentence_id=s['id'],event_kind='realized' if i==0 else 'background',race_relation=relation if i==0 else 'not_applicable',time_relation=when if i==0 else 'not_applicable',runner_ids=['r1'] if i==0 else [],time_support_ids=(['s1'] if supports is None else supports) if i==0 else [],reason='RESTRICTED_EVENT_REASON') for i,s in enumerate(payload['sentences'])])

class Model:
 def __init__(self,audit,relation='other',support_ids=None):self.audit=audit;self.calls=[];self.relation=relation;self.support_ids=support_ids
 def complete(self,model,role,system,payload,**kwargs):
  self.calls.append(dict(role=role,payload=copy.deepcopy(payload)))
  self.audit.log('model_request',role=role,request=dict(messages=[dict(role='system',content=system),dict(role='user',content=json.dumps(payload))]))
  if role=='event_resolver':value=claims(payload,self.relation)
  elif role.startswith('judge_'):value=dict(verdict='allow',reason='Independent criterion allows earlier form.',support_ids=['s1'] if self.support_ids is None else self.support_ids)
  elif role=='planner':value=dict(needs=[dict(id=1,need='Earlier ALPHA form',query='ALPHA',urls=[])])
  elif role=='selector':value=dict(sentence_ids=[payload['candidates'][0]['sentence_id']])
  elif role=='forecaster':value=dict(race_id='test',probabilities=dict(a=.6,b=.4))
  else:raise AssertionError(role)
  text=json.dumps(value);self.audit.log('model_response',role=role,text=text);return text


def test_offsets_and_complete_coverage():
 pool=sentences(TEXT)
 assert len(pool)==2 and all(TEXT[s['start']:s['end']]==s['text'] for s in pool)
 payload=context(TASK,source(),TEXT);value=claims(payload)
 assert resolution_gate(payload,value)['allow']
 value['claims'].pop()
 with pytest.raises(ValueError,match='Incomplete'):resolution_gate(payload,value)

@pytest.mark.parametrize('change',[dict(sentence_id='invented'),dict(runner_ids=['r99']),dict(time_support_ids=['invented'])])
def test_unknown_references_are_not_repaired(change):
 payload=context(TASK,source(),TEXT);value=claims(payload);value['claims'][0].update(change)
 with pytest.raises(ValueError):resolution_gate(payload,value)

def test_duplicate_sentence_review_is_not_complete():
 payload=context(TASK,source(),TEXT);value=claims(payload);value['claims'][1]=value['claims'][0]
 with pytest.raises(ValueError,match='duplicate'):resolution_gate(payload,value)

def test_realized_target_and_future_events_veto_allows():
 payload=context(TASK,source(),TEXT)
 assert resolution_gate(payload,claims(payload,'target'))['decision']=='reject'
 assert resolution_gate(payload,claims(payload,when='after',supports=[]))['decision']=='reject'

def test_unsupported_before_assertion_remains_uncertain():
 text='ALPHA won a race recently with a strong finish.';payload=context(TASK,source(text),text)
 assert resolution_gate(payload,claims(payload,supports=[]))['decision']=='uncertain'
 assert payload['source']['available_at'] is None
 schema=resolver_schema(payload)
 assert schema['properties']['claims']['minItems']==len(payload['sentences'])

def test_future_or_same_day_anchor_cannot_ground_before():
 for text in ('ALPHA won on 2026-01-04.','ALPHA won on 2026-01-03.'):
  payload=context(TASK,source(text),text)
  gate=resolution_gate(payload,claims(payload))
  assert not gate['allow'] and 's1:unsupported_pre_cutoff_assertion' in gate['uncertainties']

def test_plans_are_not_completed_target_outcomes():
 text='ALPHA will run in the target race on 2026-01-04.';payload=context(TASK,source(text),text);value=claims(payload)
 value['claims'][0].update(event_kind='plan',race_relation='target',time_relation='not_applicable',time_support_ids=[])
 assert resolution_gate(payload,value)['allow']

@pytest.mark.parametrize('ids',[['s99'],[],['s1','s1']])
def test_bad_judge_support_blocks_admission(tmp_path,ids):
 audit=Audit(tmp_path/'ledger.jsonl');m=Model(audit,support_ids=ids)
 result=JudgePanel(m,audit,policy='event-grounded').assess(TASK,dict(query='ALPHA'),source(),TEXT)
 assert not result['allow'] and all(v['verdict']=='error' for v in result['votes'])

def build_run(tmp_path,relation='other'):
 audit=Audit(tmp_path/'ledger.jsonl');s=source();audit.log('source',source=asdict(s));m=Model(audit,relation)
 class Researcher:
  def search(self,*args,**kwargs):return [s]
 result=forecast(TASK,m,Researcher(),JudgePanel(m,audit,policy='event-grounded'),audit,rounds=1,known_winners=['SECRET_WINNER'])
 manifest=dict(research_policy='event-grounded',ledger_sha256={'ledger.jsonl':digest(audit.path)})
 (tmp_path/'run_manifest.json').write_text(json.dumps(manifest))
 return result,m,audit,manifest

def test_positive_flow_audits_and_keeps_resolution_and_labels_out_of_forecaster(tmp_path):
 result,m,audit,manifest=build_run(tmp_path)
 assert result['prediction'] and result['approved_items']==1
 for call in m.calls:
  assert ('SECRET_WINNER' in json.dumps(call['payload']))==(call['role']=='judge_outcome')
  if call['role'] in ('selector','forecaster'):assert 'RESTRICTED_EVENT_REASON' not in json.dumps(call['payload'])
 assert audit_run(tmp_path)['status']=='passed'

def test_target_classification_vetoes_three_allows(tmp_path):
 result,m,audit,manifest=build_run(tmp_path,'target')
 assert result['prediction'] and result['approved_items']==0
 assert audit_run(tmp_path)['status']=='passed'

@pytest.mark.parametrize('alter',['context','resolution','gate','support'])
def test_audit_detects_semantic_or_id_tampering_after_rehash(tmp_path,alter):
 result,m,audit,manifest=build_run(tmp_path)
 rows=[json.loads(x) for x in audit.path.read_text().splitlines()]
 for row in rows:
  if row['event']=='event_resolution':
   if alter=='context':row['payload']['sentences'][0]['text']='ALTERED'
   if alter=='resolution':row['resolution']['claims'][0]['reason']='REWRITTEN'
   if alter=='gate':row['gate']['decision']='reject'
  if row['event']=='judge_panel' and alter=='support':row['votes'][0]['support_ids']=['s99']
 previous='0'*64
 for row in rows:
  row.pop('event_sha256');row['previous_sha256']=previous
  row['event_sha256']=hashlib.sha256(json.dumps(row,ensure_ascii=False,sort_keys=True,allow_nan=False).encode()).hexdigest();previous=row['event_sha256']
 audit.path.write_text(''.join(json.dumps(r)+'\n' for r in rows));manifest['ledger_sha256']['ledger.jsonl']=digest(audit.path)
 (tmp_path/'run_manifest.json').write_text(json.dumps(manifest))
 with pytest.raises(ValueError):audit_run(tmp_path)


def test_native_schema_requires_empty_time_support_without_anchors():
 text='ALPHA finished strongly at some unknown time.';payload=context(TASK,source(text),text)
 assert payload['time_anchors']==[]
 support=resolver_schema(payload)['properties']['claims']['items']['properties']['time_support_ids']
 assert support['maxItems']==0
 assert 'NO_ANCHOR' not in json.dumps(support)


def test_legacy_event_protocol_context_remains_auditable(tmp_path):
 result,m,audit,manifest=build_run(tmp_path)
 rows=[json.loads(x) for x in audit.path.read_text().splitlines()]
 for row in rows:
  if row['event']=='event_resolution':row['payload']['protocol']='event-grounded-v1'
  if row['event']=='judge_panel':row['review_protocol']='event-grounded-v1'
  if row['event']=='model_request' and row['role'] in ('event_resolver','judge_provenance','judge_outcome','judge_relevance'):
   payload=json.loads(row['request']['messages'][-1]['content']);payload['protocol']='event-grounded-v1'
   row['request']['messages'][-1]['content']=json.dumps(payload)
 previous='0'*64
 for row in rows:
  row.pop('event_sha256');row['previous_sha256']=previous
  row['event_sha256']=hashlib.sha256(json.dumps(row,ensure_ascii=False,sort_keys=True,allow_nan=False).encode()).hexdigest();previous=row['event_sha256']
 audit.path.write_text(''.join(json.dumps(r)+'\n' for r in rows));manifest['ledger_sha256']['ledger.jsonl']=digest(audit.path)
 (tmp_path/'run_manifest.json').write_text(json.dumps(manifest))
 assert audit_run(tmp_path)['status']=='passed'


def test_unknown_event_protocol_is_rejected():
 with pytest.raises(ValueError,match='Unknown event review protocol'):context(TASK,source(),TEXT,protocol='invented')
