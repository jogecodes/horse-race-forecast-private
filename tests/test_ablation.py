from copy import deepcopy
import pytest
np=pytest.importorskip('numpy')
from horse_racing.ablation import (add_prior_ratings,add_frozen_ratings,project,
    fit_subset,chronological_parts,EXTENDED_FEATURES)
from horse_racing.statistical import predict


def race(rid,day,y):
    return dict(race_id=rid,date=day,venue='V',runner_ids=['a','b'],
                x=[[0.]*6,[0.]*6],y=y)


def test_rating_waits_until_next_day_and_never_uses_current_outcome():
    cases=[race('r1','2024-01-01',[1,0]),race('r2','2024-01-01',[1,0]),race('r3','2024-01-02',[0,1])]
    original=deepcopy(cases)
    enriched,ratings=add_prior_ratings(cases)
    assert cases==original
    assert [r['x'][0][-1] for r in enriched]==pytest.approx([0,0,.5])
    changed=deepcopy(cases);changed[-1]['y']=[1,0]
    changed_enriched,_=add_prior_ratings(changed)
    assert enriched[-1]['x']==changed_enriched[-1]['x']
    assert sum(ratings.values())==pytest.approx(0)


def test_appending_future_race_does_not_change_earlier_features():
    cases=[race('r1','2024-01-01',[1,0]),race('r2','2024-01-02',[1,0])]
    earlier,_=add_prior_ratings(cases)
    extended,_=add_prior_ratings(cases+[race('r3','2025-01-01',[0,1])])
    assert earlier==extended[:2]


def test_subset_excludes_dropped_feature_and_preserves_metadata():
    cases=[]
    for i in range(8):
        c=race(str(i),'2024-01-01',[1,0]);c['x']=[[0,0,1,0,0,0,0],[0,0,0,0,0,0,0]];cases.append(c)
    indices=(2,5);model=fit_subset(cases,indices,.01,steps=200)
    assert model['features']==[EXTENDED_FEATURES[i] for i in indices]
    assert len(model['weights'])==len(model['features'])==2
    original=predict(project([cases[0]],indices)[0],'linear_race',model)
    changed=deepcopy(cases[0]);changed['x'][0][0]=999999
    assert original==predict(project([changed],indices)[0],'linear_race',model)
    assert original[0]>.8


def test_period_boundaries_and_frozen_unknown_identity():
    cases=[race('r'+str(i),day,[1,0]) for i,day in enumerate(['2023-01-01','2024-01-01','2025-01-01','2026-01-01','2027-01-01'])]
    groups=chronological_parts(cases,'2024-01-01','2025-01-01','2026-01-01','2027-01-01')
    assert [[c['race_id'] for c in g] for g in groups]==[['r0'],['r1'],['r2'],['r3']]
    c={'x':[[0]*6,[0]*6],'identity_links':[{'horse_id':'a'},{'horse_id':None}]}
    rated=add_frozen_ratings(c,{'a':.7})
    assert rated['x'][0][-1]==.7 and rated['x'][1][-1]==0
    assert len(c['x'][0])==6
    with pytest.raises(ValueError):chronological_parts(cases,'2025','2024','2026','2027')
