"""Stateless, local-only Ollama JSON completions; no hosted fallback."""
import hashlib,json,time
from urllib.parse import urlparse
import requests
from ..db import now


class Audit:
    def __init__(self,path):
        self.path=path;self.previous='0'*64
        if path.exists():raise FileExistsError(path)
        path.parent.mkdir(parents=True,exist_ok=True)
        path.touch(exist_ok=False)
    def log(self,event,**fields):
        row=dict(at=now(),event=event,previous_sha256=self.previous,**fields)
        serialized=json.dumps(row,ensure_ascii=False,sort_keys=True,allow_nan=False)
        row['event_sha256']=hashlib.sha256(serialized.encode()).hexdigest()
        with self.path.open('a') as f:f.write(json.dumps(row,ensure_ascii=False,sort_keys=True,allow_nan=False)+'\n')
        self.previous=row['event_sha256']


class Ollama:
    requires_short_runner_ids=True
    def __init__(self,audit,base='http://127.0.0.1:11434',timeout=180):
        p=urlparse(base)
        if p.scheme!='http' or p.hostname not in ('localhost','127.0.0.1','::1') or p.username or p.password:
            raise ValueError('Only local Ollama HTTP endpoints are supported')
        self.base=base.rstrip('/');self.audit=audit;self.timeout=timeout
    def tags(self):
        r=requests.get(self.base+'/api/tags',timeout=10);r.raise_for_status();return r.json()['models']
    def complete(self,model,role,system,payload,tokens=768,seed=0):
        output_format='json'
        if role=='forecaster':
            task=payload['task'];ids=[r['runner_id'] for r in task['runners']]
            output_format=dict(type='object',properties={
                'race_id':dict(type='string',enum=[task['race_id']]),
                'probabilities':dict(type='object',properties={rid:dict(type='number',minimum=0,maximum=1) for rid in ids},
                                     required=ids,additionalProperties=False)},required=['race_id','probabilities'],additionalProperties=False)
        elif role.startswith('judge_'):
            output_format=dict(type='object',properties={'reason':dict(type='string'),
                               'verdict':dict(type='string',enum=['drop','allow'])},required=['verdict','reason'],additionalProperties=False)
            if payload.get('dating_policy')=='exploratory':
                output_format['properties']['verdict']['enum'].append('uncertain')
                output_format['properties']['supporting_quotes']=dict(type='array',items=dict(type='string'),maxItems=3)
                output_format['required'].append('supporting_quotes')
            if payload.get('dating_policy')=='event-grounded':
                output_format['properties']['verdict']['enum'].append('uncertain')
                output_format['properties']['support_ids']=dict(type='array',items=dict(type='string',enum=[s['id'] for s in payload['sentences']]),maxItems=3)
                output_format['required'].append('support_ids')
        if role=='event_resolver':
            from .events import resolver_schema
            output_format=resolver_schema(payload)
        request=dict(model=model,stream=False,format=output_format,messages=[dict(role='system',content=system),
             dict(role='user',content=json.dumps(payload,ensure_ascii=False,allow_nan=False))],
             options=dict(temperature=0,seed=seed,num_ctx=8192,num_predict=tokens))
        self.audit.log('model_request',role=role,model=model,request=request)
        start=time.monotonic()
        try:
            r=requests.post(self.base+'/api/chat',json=request,timeout=self.timeout);r.raise_for_status();result=r.json()
            if not result.get('done'):raise ValueError('Incomplete local model response')
            text=result['message']['content']
            self.audit.log('model_response',role=role,model=model,text=text,seconds=time.monotonic()-start,
                           done_reason=result.get('done_reason'),prompt_eval_count=result.get('prompt_eval_count'),eval_count=result.get('eval_count'))
            return text
        except Exception as error:
            self.audit.log('model_error',role=role,model=model,error=str(error),seconds=time.monotonic()-start)
            raise


def json_reply(text):
    # One exact JSON object. Extra prose and code fences are parse failures, never repaired.
    def pairs(items):
        out={}
        for key,value in items:
            if key in out:raise ValueError('Duplicate JSON key')
            out[key]=value
        return out
    def invalid_constant(value):raise ValueError('Nonfinite JSON constant')
    value=json.loads(text,object_pairs_hook=pairs,parse_constant=invalid_constant)
    if not isinstance(value,dict):raise ValueError('Expected one JSON object')
    return value
