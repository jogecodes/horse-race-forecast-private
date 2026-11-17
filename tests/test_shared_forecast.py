import importlib.util
import json
from dataclasses import asdict
from pathlib import Path

import pytest

pytest.importorskip('jsonschema', reason='Shared engine tests use the documented sibling research interpreter')

from horse_racing.shared_forecast import (declaration_sources, environment_for,
    public_packet, question_for, score_rows, write_json, Source)

ROOT=Path(__file__).resolve().parents[1]


@pytest.fixture
def packet():
    p=json.loads((ROOT/'benchmarks/h1_2026_v2/diagnostic/packets/race_a0df96e5786c2257866c43f8d57fbd01.json').read_text())
    p['known_winner']='SECRET_OUTCOME'
    p['runners'][0]['finishing_position']='SECRET_OUTCOME'
    return p


def test_public_mapping_hides_outcomes_and_rejects_heldout(packet):
    q=question_for(packet,packet['runners'][0]['runner_id'])
    assert 'SECRET_OUTCOME' not in json.dumps(asdict(q))
    assert 'including a later nonstarter' in q.resolution_criteria
    assert 'dead-heat' in q.resolution_criteria
    packet['split']='test'
    with pytest.raises(ValueError):
        question_for(packet,packet['runners'][0]['runner_id'])


def test_real_corpus_provenance_and_metadata_cutoff():
    sources=declaration_sources(ROOT/'data/declarations_h1_2026.sqlite')
    assert sources
    assert all('not independent archive proof' in s.provenance for s in sources)
    assert all('2026-03-' not in s.title for s in sources)
    cutoff='2026-01-03T22:59:00+00:00'
    env=environment_for(sources,cutoff,'declaration_research')
    hits=env.search('Declaration',10000)
    assert hits
    assert all(h.available_at<=cutoff for h in hits)
    hidden=next(s for s in sources if s.available_at>cutoff)
    assert hidden.id not in {h.id for h in hits}
    with pytest.raises(ValueError):
        env.fetch(hidden.id)
    assert environment_for(sources,cutoff,'declaration_only').search('Declaration',100)==[]


def test_binary_scoring_missing_invalid_and_deadheat():
    rows=[dict(race_id='race',runner_id='horse',field_size=4,probability=.2),
          dict(race_id='race',runner_id='horse',field_size=4,probability=None)]
    scored=score_rows(rows,{'race':{'horse':.5}})
    assert len(scored)==1 and scored[0]['outcome']==1
    assert scored[0]['brier']==pytest.approx(.64)
    rows[0]['probability']=1.1
    with pytest.raises(ValueError):
        score_rows(rows,{'race':{'horse':.5}})


def load_runner():
    spec=importlib.util.spec_from_file_location('weekend_runner',ROOT/'scripts/run_shared_weekend.py')
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('fail',[False,True])
def test_worker_persists_real_engine_success_and_failure(tmp_path,monkeypatch,packet,fail):
    module=load_runner()
    seen=[]
    class FakeClient:
        def __init__(self,*a,**kw): pass
        async def structured(self,role,system,prompt,max_tokens,schema):
            seen.append(prompt)
            if fail: raise ValueError('preserved development failure')
            if role=='question_analyst':
                return json.dumps(dict(interpretation='winner criteria',ambiguities=[]))
            if role=='research_coordinator': return '{"tasks":[]}'
            return json.dumps(dict(reasoning='uncertain',uncertainties=['missing evidence'],source_ids=[]))
        async def complete(self,*a): return 'PROBABILITY: 0.2'
    monkeypatch.setattr(module,'OllamaClient',FakeClient)
    p=public_packet(packet)
    write_json(tmp_path/'public/packets.json',[p])
    write_json(tmp_path/'public/sources.json',[])
    case=dict(race_id=p['race_id'],runner_id=p['runners'][0]['runner_id'],model='fake',seed=0,arm='declaration_only')
    write_json(tmp_path/'public/cases.json',[case])
    attempt=tmp_path/'attempt'
    if fail:
        with pytest.raises(ValueError): module.worker(tmp_path,0,attempt)
    else:
        module.worker(tmp_path,0,attempt)
    result=json.loads((attempt/'result.json').read_text())
    assert 'SECRET_OUTCOME' not in ''.join(seen)
    assert (attempt/'trace.jsonl').exists()
    if fail: assert 'preserved development failure' in result['error']
    else: assert result['result']['probability']==pytest.approx(.2)
