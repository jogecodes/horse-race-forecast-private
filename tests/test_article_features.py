import asyncio
import json
from types import SimpleNamespace
import pytest
from horse_racing.article_features import candidates_for,names_horse,validate_claim,prompt_for,extract_article,article_vector


def fixture():
    packet=dict(date='2026-02-01',cutoff_utc='2026-01-31T22:59:00Z',venue='V')
    runner=dict(horse_name='IFACH (IRE)',prior_form_raw='[01,02]')
    source=dict(id='s',text='Los favoritos son Ifach y Something.',title='Preview',url='https://example.test',
        available_at='2026-01-29T12:00:00Z',provenance=json.dumps(dict(source_type='publisher_article',target_event_date='2026-02-01')))
    return packet,runner,source


def test_gate_uses_before_cutoff_target_date_and_full_horse_name():
    p,r,s=fixture();assert len(candidates_for(p,r,[s]))==1
    assert not names_horse('IFACHETTE won','IFACH (IRE)')
    assert names_horse('José’s horse','JOSE\'S HORSE (GB)')
    assert not candidates_for(p,r,[dict(s,available_at='2026-02-01T10:00:00Z')])
    wrong=json.dumps(dict(source_type='publisher_article',target_event_date='2026-01-11'))
    assert not candidates_for(p,r,[dict(s,provenance=wrong)])


def test_quote_is_resolved_from_source_and_unknown_requires_null():
    p,r,s=fixture();c=candidates_for(p,r,[s])
    out=validate_claim(dict(assessment='selected',evidence_id='s'),c)
    assert out['quote']==s['text']
    with pytest.raises(ValueError,match='admitted'):validate_claim(dict(assessment='selected',evidence_id='made-up'),c)
    with pytest.raises(ValueError,match='must not cite'):validate_claim(dict(assessment='unknown',evidence_id='s'),c)


def test_prompt_cannot_ask_agent_to_reparse_form():
    p,r,s=fixture();payload=prompt_for(p,r,candidates_for(p,r,[s]))
    assert 'prior_form_raw' not in json.dumps(payload)
    assert 'probabilities' not in payload and 'outcomes' not in payload


def test_conflicting_source_ids_and_naive_dates_fail_closed():
    p,r,s=fixture()
    with pytest.raises(ValueError,match='Conflicting'):candidates_for(p,r,[s,dict(s,text='Changed')])
    with pytest.raises(ValueError,match='Timezone'):candidates_for(p,r,[dict(s,available_at='2026-01-29T12:00:00')])


def test_no_source_skips_inference_and_failure_preserves_unknown():
    p,r,s=fixture()
    # Any client call would fail; the empty-source path must not call it.
    out=asyncio.run(extract_article(None,p,r,[],None))
    assert out['model_calls']==0 and out['assessment']=='unknown'
    assert article_vector(out)==[0.]*5
    assert article_vector(dict(status='failed'))==[0.]*5
