import json
import pytest
from horse_racing.article_features_v2 import scoped_candidates,validate,schema


def source(text):
    return dict(id='s',text=text,title='Preview',url='https://example.test',available_at='2026-01-29T12:00:00Z',
        provenance=json.dumps(dict(source_type='publisher_article',target_event_date='2026-02-01')))


P=dict(date='2026-02-01',cutoff_utc='2026-01-31T22:59:00Z',race_ordinal=5,venue='V')


def test_tip_entry_is_exact_and_official_identity_is_checked():
    text='Selección: 507 DUKES OF HAATHER (GB) // 502 XMAS (IRE) // 509IMONFIRE (IRE)'
    c,omissions=scoped_candidates(P,dict(horse_name='IMONFIRE (IRE)',cloth=9),[source(text)])
    assert not omissions and len(c)==1 and c[0]['scope']=='explicit_numbered_tip'
    assert c[0]['text']=='509IMONFIRE (IRE)'
    assert text[c[0]['start']:c[0]['end']]==c[0]['text']
    c,omissions=scoped_candidates(P,dict(horse_name='IMONFIRE (IRE)',cloth=8),[source(text)])
    assert not c and omissions[0]['reason']=='tip_code_disagrees_with_official_declaration'


def test_comparator_mention_keeps_its_actual_entry_owner():
    text='Para ganar: 7-MUSIC HISTORY (GB) Es su oportunidad. 1-NATURAL FORCE (GB) Fue tercero tras Shutterwood y Ambushed.'
    c,_=scoped_candidates(P,dict(horse_name='SHUTTERWOOD (FR)',cloth=5),[source(text)])
    assert len(c)==1 and c[0]['scope']=='mention_in_another_horse_entry'
    assert c[0]['entry_horse']=='NATURAL FORCE'
    assert c[0]['text'].startswith('1-NATURAL FORCE')


def test_own_entry_retains_heading_and_does_not_include_next_horse():
    text='Para ganar: 1-ROMEO (FR) Tiene una opción clara. 5-HAYA TAAL (IRE) Es peligroso.'
    c,_=scoped_candidates(P,dict(horse_name='ROMEO (FR)',cloth=1),[source(text)])
    assert len(c)==1 and c[0]['section_context']=='Para ganar: '
    assert 'HAYA' not in c[0]['text']


def test_unknown_and_supported_withdrawal_are_distinct_and_nonpredictive():
    text='Se ha retirado 3-BE TRUE (FR), que era uno de mis favoritos.'
    c,_=scoped_candidates(P,dict(horse_name='BE TRUE (FR)',cloth=3),[source(text)])
    assert 'retirado' in c[0]['section_context']
    result=validate(dict(decision='withdrawn@0'),c)
    assert result['assessment']=='unknown' and result['mention_role']=='withdrawn'
    assert result['quote']==c[0]['text']
    assert validate(dict(decision='unknown'),c)['evidence_id'] is None
    assert schema(c)['properties']['decision']['enum'][0]=='unknown'
    with pytest.raises(ValueError):validate(dict(decision='selected@99'),c)
