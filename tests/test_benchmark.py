import hashlib,json,math,sqlite3
from pathlib import Path
import pytest
from horse_racing.db import initialize
from horse_racing.ingest import import_jce
from horse_racing.benchmark import (build,verify,cutoff_for,split_for,metrics,validate_prediction,
    baseline_predictions,score,write_jsonl,read_jsonl,aggregate,history_before_2026,todo_rows)
from test_database import CARD


def todo_html(names=('SYNTHETIC ALPHA (FR)','SYNTHETIC BETA')):
    return '<table><tbody>'+''.join(f'<tr><td>{i}</td><td><a href="horse">{n}</a></td><td>57</td><td>J</td><td></td><td></td><td></td></tr>' for i,n in enumerate(names,1))+'</tbody></table>'


@pytest.fixture
def source(tmp_path):
    db=tmp_path/'source.sqlite';c=initialize(db)
    # Synthetic recorded finishers, not withdrawn/status-coded runners.
    card=CARD.replace('L14: ~~2~~ | ~~SYNTHETIC BETA~~ | ~~56~~ | ~~Synthetic Jockey B~~ | ~~Synthetic Stable~~ | ~~Synthetic Trainer~~ | ~~1~~',
      'L14: 2 | SYNTHETIC BETA | 56 | Synthetic Jockey B | Synthetic Stable | Synthetic Trainer | 1')
    card=card.replace('L18: RET | SYNTHETIC BETA | 2 | - | - | - | - | Synthetic Trainer | Synthetic Stable |',
      'L18: 2 | SYNTHETIC BETA | 2 | - | Synthetic Jockey B | 56 | 1 | Synthetic Trainer | Synthetic Stable |')
    # Add a third runner; benchmark requires >=3.
    card=card.replace('L15: ####','L14: 3 | SYNTHETIC GAMMA | 56 | Synthetic Jockey C | Synthetic Stable | Synthetic Trainer | 3\nL15: ####')
    card=card.replace('L19: Condiciones','L18: 3 | SYNTHETIC GAMMA | 3 | - | Synthetic Jockey C | 56 | 3 | Synthetic Trainer | Synthetic Stable |\nL19: Condiciones')
    dates=['2025-12-01','2026-01-10','2026-03-10','2026-05-10']
    for d in dates:import_jce(c,card,d,'1','La Zarzuela','2026-11-05T12:00:00Z')
    c.close();cache=tmp_path/'cache';cache.mkdir();races=[]
    for i,d in enumerate(dates[1:]):
        body=todo_html(('SYNTHETIC ALPHA (FR)','SYNTHETIC BETA','SYNTHETIC GAMMA'))
        raw=f'race{i}.html';meta=f'race{i}.json';sha=hashlib.sha256(body.encode()).hexdigest()
        (cache/raw).write_text(body)
        (cache/meta).write_text(json.dumps(dict(sha256=sha,observed_at='2026-11-05T12:01:00Z')))
        races.append(dict(date=d,venue='LA ZARZUELA',ordinal=1,file=raw,metadata=meta,sha256=sha,url=f'https://example.invalid/race/{i}'))
    (cache/'manifest.json').write_text(json.dumps(dict(races=races)))
    return db,cache,tmp_path/'bundle'


def test_local_cutoff_respects_winter_and_summer_and_splits():
    assert cutoff_for('2026-02-01')=='2026-01-31T22:59:00+00:00'
    assert cutoff_for('2026-06-01')=='2026-05-31T21:59:00+00:00'
    assert split_for('2026-02-28')=='development'
    assert split_for('2026-03-01')=='validation'
    assert split_for('2026-05-01')=='test'
    with pytest.raises(ValueError):split_for('2026-07-01')


def test_build_repeatable_frozen_and_label_isolated(source):
    db,cache,out=source;m=build(db,cache,out)
    assert m['included_races']==3 and m['strict_ready_cases']==0
    assert m['splits']==dict(development=1,validation=1,test=1)
    again=out.parent/'again';assert build(db,cache,again)==m
    assert verify(out)==m
    with pytest.raises(FileExistsError):build(db,cache,out)
    labels=read_jsonl(out/'supervisor/labels.jsonl')
    for task,label in zip(read_jsonl(out/'diagnostic/tasks.jsonl'),labels):
        packet=json.loads((out/f'diagnostic/packets/{task["race_id"]}.json').read_text())
        assert set(label['target'])=={r['runner_id'] for r in packet['runners']}
        assert all(r['history_through_2025']['starts']==1 for r in packet['runners'])
        assert all(r['history_through_2025']['last_race_date']=='2025-12-01' for r in packet['runners'])
        assert 'target' not in packet and 'position' not in json.dumps(packet)
        assert 'primary_url' not in packet and 'status_raw' not in json.dumps(packet)
    assert all(not a['strict_admissible'] and a['override_allowed'] is False for a in read_jsonl(out/'supervisor/admission_audit.jsonl'))
    h=read_jsonl(out/'supervisor/history_before_2026.jsonl')
    assert all(r['race_date']<'2026-01-01' for r in h)


def test_changed_packet_detected(source):
    db,cache,out=source;build(db,cache,out)
    next((out/'diagnostic/packets').glob('*.json')).write_text('{}')
    with pytest.raises(ValueError,match='changed'):verify(out)


def test_cross_source_winner_disagreement_excluded(source):
    db,cache,out=source;m=json.loads((cache/'manifest.json').read_text());r=m['races'][0]
    body=todo_html(('SYNTHETIC BETA','SYNTHETIC ALPHA (FR)','SYNTHETIC GAMMA'))
    sha=hashlib.sha256(body.encode()).hexdigest();(cache/r['file']).write_text(body)
    r['sha256']=sha;(cache/r['metadata']).write_text(json.dumps(dict(sha256=sha,observed_at='2026-11-05T12:01:00Z')))
    (cache/'manifest.json').write_text(json.dumps(m))
    manifest=build(db,cache,out)
    assert manifest['included_races']==2
    assert 'cross_source_winner_disagreement' in read_jsonl(out/'supervisor/exclusions.jsonl')[0]['reasons']


def test_uniform_and_perfect_probabilistic_scores():
    y={'a':1.,'b':0.,'c':0.}
    p={k:1/3 for k in y};m=metrics(p,y)
    assert m['brier']==pytest.approx(2/3)
    assert m['log_loss']==pytest.approx(math.log(3))
    assert m['top1_fractional_accuracy']==pytest.approx(1/3)
    assert metrics(y,y)['brier']==0
    assert metrics({'a':0.,'b':1.,'c':0.},y)['zero_probability_winner']


def test_dead_heat_target_and_tied_predictions():
    y={'a':.5,'b':.5,'c':0.};m=metrics(y,y)
    assert m['brier']==0 and m['log_loss']==pytest.approx(math.log(2))
    assert m['top1_fractional_accuracy']==.5


@pytest.mark.parametrize('p',[{'a':True,'b':0},{'a':float('nan'),'b':0},{'a':1.2,'b':-.2},{'a':.2,'b':.2},{'a':1},None])
def test_invalid_probability_vectors_rejected(p):
    assert validate_prediction(p,{'a':1,'b':0})


def test_invalid_replies_excluded_and_no_imputation(source,tmp_path):
    db,cache,out=source;build(db,cache,out)
    predictions=baseline_predictions(out,'uniform');p=tmp_path/'pred.jsonl'
    # Duplicate one race, malformed one line, and omit another race.
    write_jsonl(p,[predictions[0],predictions[0],predictions[1]])
    with p.open('a') as f:f.write('not-json\n')
    result=score(out,p,split='all',bootstrap=30)
    assert result['valid_predictions']==1 and result['coverage']==pytest.approx(1/3)
    assert result['parse_rate']==.75 and not result['leaderboard_eligible']
    assert {r['reason'] for r in result['invalid_predictions']}=={'duplicate_predictions','missing_prediction'}
    assert len(result['malformed_lines'])==1


def test_baselines_valid_and_test_split_default(source,tmp_path):
    db,cache,out=source;build(db,cache,out)
    for kind in ['uniform','history']:
        predictions=baseline_predictions(out,kind);p=tmp_path/f'{kind}.jsonl';write_jsonl(p,predictions)
        result=score(out,p,bootstrap=30)
        assert result['expected_races']==1 and result['coverage']==1
        assert result['leaderboard_eligible']
        assert result['overall']['confidence_intervals_95'] is None


def test_bootstrap_is_meeting_clustered_and_deterministic():
    rows=[dict(meeting_id=str(i//2),**metrics({'a':p,'b':1-p},{'a':1,'b':0})) for i,p in enumerate([.1,.2,.8,.9])]
    a=aggregate(rows,bootstrap=100);b=aggregate(rows,bootstrap=100)
    assert a==b and a['meeting_clusters']==2
    assert len(a['confidence_intervals_95']['brier'])==2


def test_todoturf_utf8_overrides_conflicting_legacy_meta():
    body=('<meta http-equiv="Content-Type" content="text/html; charset=iso-8859-1"><meta charset="UTF-8">'+todo_html(('MI NIÑO (IRE)','SEÑALES MIXTAS','THIRD'))).encode('utf-8')
    parsed=todo_rows(body)
    assert parsed[0]['name']=='MI NIÑO (IRE)'
    assert parsed[1]['name']=='SEÑALES MIXTAS'
