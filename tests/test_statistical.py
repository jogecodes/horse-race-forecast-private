import sqlite3
import pytest

np=pytest.importorskip('numpy',reason='CPU experiments use existing sibling research interpreter')
from horse_racing.statistical import (features,historical_cases,declaration_case,
    predict,fit,evaluate,identity)


def observation(day,win=1):
    return dict(date=day,win_share=win,finish_strength=win,distance_m=1600)


def test_features_exclude_same_day_and_future_outcomes():
    prior=[observation('2024-01-01')]
    reference=features(prior,'2024-02-01',1600)
    assert reference==features(prior+[observation('2024-02-01',0),observation('2024-03-01',0)],'2024-02-01',1600)
    assert features([],'2024-02-01',1600)[-1]==1


def test_historical_snapshot_waits_until_next_day(tmp_path):
    db=tmp_path/'history.sqlite';c=sqlite3.connect(db)
    c.executescript('''CREATE TABLE entities(id,name);CREATE TABLE meetings(id,race_date,venue);
      CREATE TABLE races(id,meeting_id);CREATE TABLE race_versions(id,distance_m);
      CREATE TABLE latest_results(race_id,horse_id,position,race_version_id);
      INSERT INTO entities VALUES('a','Horse A'),('b','Horse B');
      INSERT INTO meetings VALUES('m1','2024-01-01','Venue'),('m2','2024-01-02','Venue');
      INSERT INTO races VALUES('r1','m1'),('r2','m1'),('r3','m2');
      INSERT INTO race_versions VALUES('v1',1600),('v2',1600),('v3',1600);
      INSERT INTO latest_results VALUES('r1','a',1,'v1'),('r1','b',2,'v1'),
      ('r2','a',2,'v2'),('r2','b',1,'v2'),('r3','a',1,'v3'),('r3','b',2,'v3');''')
    c.commit();c.close()
    cases,histories,aliases,exclusions=historical_cases(db)
    assert not exclusions
    assert cases[0]['x']==cases[1]['x']
    assert cases[2]['x'][0][1]==pytest.approx(np.log1p(2))
    assert len(histories['a'])==3


def test_public_case_preserves_unmatched_declared_runner():
    packet=dict(split='development',race_id='r',date='2026-01-04',venue='V',
                cutoff_utc='2026-01-03T22:59:00Z',distance_m=1600,
                runners=[dict(runner_id='a',horse_name='Horse A'),dict(runner_id='b',horse_name='Unknown')])
    history={'idA':[observation('2025-01-01')]};aliases={identity('Horse A'):['idA']}
    case=declaration_case(packet,history,aliases)
    assert case['runner_ids']==['a','b']
    assert case['identity_links'][1]['status']=='no_history'
    assert len(predict(case,'smoothed_history'))==2
    assert sum(predict(case,'smoothed_history'))==pytest.approx(1)
    assert 'y' not in case
    history['idA'].append(observation('2026-01-02'))
    with pytest.raises(ValueError):declaration_case(packet,history,aliases)
    packet['split']='test'
    with pytest.raises(ValueError):declaration_case(packet,{}, {})


def test_learning_finds_signal_and_builds_distribution():
    cases=[dict(x=[[1.,0.],[0.,0.]],y=[1.,0.]) for _ in range(8)]
    model=fit(cases,.01,steps=200)
    p=predict(cases[0],'linear_race',model)
    assert p[0]>.8
    assert sum(p)==pytest.approx(1)
    assert evaluate(p,[1,0])['log_loss'] < evaluate([.5,.5],[1,0])['log_loss']


@pytest.mark.parametrize('p',[[.7,.7],[float('nan'),.5],[-.1,1.1]])
def test_invalid_distributions_are_rejected(p):
    with pytest.raises(ValueError):evaluate(p,[1,0])
