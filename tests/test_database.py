"""Synthetic plumbing tests; these fixtures are never inserted into the real seed."""
import json
import sqlite3
from pathlib import Path
import pytest
from horse_racing.db import initialize, insert, snapshot, uid, stats, utc
from horse_racing.ingest import import_jce, parse, horse_name
from horse_racing.gate import create_run, record_vote, decision, export_packet

CARD = '''L10: #### 1ª Carrera (100): Synthetic Test - 1.200 m. 5.000 euros.
L11: Synthetic conditions.
L12: Nº | Caballo | Peso | Jockey | Propietario | Entrenador | Cajón
L13: 1 | SYNTHETIC ALPHA (FR) (8) | 57.5 | Synthetic Jockey A | Synthetic Stable | Synthetic Trainer | 2
L14: ~~2~~ | ~~SYNTHETIC BETA~~ | ~~56~~ | ~~Synthetic Jockey B~~ | ~~Synthetic Stable~~ | ~~Synthetic Trainer~~ | ~~1~~
L15: #### 1ª Carrera (nº 100): Synthetic Test - 1.200 m. Hierba/Bueno
L16: Pos | Nombre | Nº | Dist. | Jockey | Peso | Cajón | Entrenador | Propietario | Criador
L17: 1 | SYNTHETIC ALPHA (FR) (8) | 1 | - | Synthetic Jockey A | 57.5 | 2 | Synthetic Trainer | Synthetic Stable | Synthetic Breeder
L18: RET | SYNTHETIC BETA | 2 | - | - | - | - | Synthetic Trainer | Synthetic Stable |
L19: Condiciones de carrera: Synthetic conditions.
'''
JUDGES = ['provenance','outcome','relevance']


@pytest.fixture
def conn(tmp_path):
    c = initialize(tmp_path/'test.sqlite')
    import_jce(c,CARD,'2026-10-25','1','Synthetic Venue','2026-10-26T12:00:00Z')
    import_jce(c,CARD,'2026-11-01','1','Synthetic Venue','2026-10-30T12:00:00Z')
    yield c
    c.close()


def run(conn):
    return create_run(conn,'jce:2026-11-01:1:r1','2026-10-31T12:00:00Z',JUDGES)


def item(conn, day='2026-10-25', kind='declaration'):
    return conn.execute('SELECT id FROM evidence WHERE related_race_id=? AND kind=? ORDER BY id',
                        (f'jce:{day}:1:r1',kind)).fetchone()[0]


def approve(conn,r,e):
    for j in JUDGES:
        record_vote(conn,r,e,j,json.dumps(dict(verdict='allow',reason='Synthetic approval')),'fake-test-model','Synthetic prompt')


def test_parse_realistic_rows():
    p = parse(CARD)
    assert len(p)==2 and len(p[0]['rows'])==2
    assert p[0]['distance_m']==1200 and p[1]['phase']=='result'
    assert horse_name('ORION GRO')=='ORION'
    assert horse_name('EXAMPLE (IRE) (4)(8)')=='EXAMPLE (IRE)'


def test_seed_idempotent_and_append_only(conn):
    before = stats(conn)
    import_jce(conn,CARD,'2026-10-25','1','Synthetic Venue','2026-10-26T12:00:00Z')
    assert stats(conn)==before
    with pytest.raises(sqlite3.IntegrityError,match='append-only'):
        conn.execute("UPDATE snapshots SET observed_at='2000-01-01'")
    with pytest.raises(sqlite3.IntegrityError,match='append-only'):
        conn.execute('DELETE FROM results')
    conn.rollback()
    assert not stats(conn)['foreign_key_errors']


def test_keep_revisions(conn):
    import_jce(conn,CARD.replace('Synthetic conditions.','Revised conditions.'),'2026-10-25','1','Synthetic Venue','2026-10-27T12:00:00Z')
    assert conn.execute('SELECT count(*) FROM snapshots').fetchone()[0]==3
    assert conn.execute('SELECT count(*) FROM race_versions').fetchone()[0]==6


def test_malformed_ingest_does_not_commit(conn):
    before = stats(conn)
    with pytest.raises(ValueError):
        import_jce(conn,CARD.replace('L18: RET','L18: UNKNOWN'),'2026-10-20','1','Synthetic Venue','2026-10-21T00:00:00Z')
    assert stats(conn)==before


def test_incomplete_result_rejected():
    with pytest.raises(ValueError,match='Incomplete'):
        parse('\n'.join(line for line in CARD.splitlines() if not line.startswith('L18:')))


def test_duplicate_runner_rejected():
    with pytest.raises(ValueError,match='Duplicate'):
        parse(CARD.replace('~~2~~','~~1~~'))


def test_dead_heat_preserved():
    p = parse(CARD.replace('L18: RET','L18: 1 (EMP)'))
    assert p[1]['rows'][1][2][0]=='1 (EMP)'


def test_all_judges_required(conn):
    r,e = run(conn),item(conn)
    assert decision(conn,r,e)['decision']=='drop'
    approve(conn,r,e)
    assert decision(conn,r,e)['decision']=='allow'
    saved = conn.execute('SELECT prompt_text,raw_response FROM judge_votes LIMIT 1').fetchone()
    assert saved['prompt_text']=='Synthetic prompt'
    assert json.loads(saved['raw_response'])['verdict']=='allow'


def test_future_snapshot_cannot_be_overridden(conn):
    r = run(conn)
    sid = snapshot(conn,'jce','https://example.invalid/late','Late synthetic text','2026-11-02T00:00:00Z')
    with conn:
        insert(conn,'evidence',id='late',snapshot_id=sid,text='Synthetic context',kind='context',locator='test')
    approve(conn,r,'late')
    assert 'snapshot_observed_after_cutoff' in decision(conn,r,'late')['reasons']


def test_target_outcome_cannot_be_overridden(conn):
    r,e = run(conn),item(conn,'2026-11-01','result')
    approve(conn,r,e)
    assert 'target_race_outcome' in decision(conn,r,e)['reasons']


def test_prior_results_allowed_only_when_observed(conn):
    r,e = run(conn),item(conn,kind='result')
    approve(conn,r,e)
    assert decision(conn,r,e)['decision']=='allow'


def test_result_day_must_have_ended(conn):
    r = create_run(conn,'jce:2026-11-01:1:r1','2026-10-25T10:00:00Z',JUDGES)
    e = item(conn,kind='result')
    approve(conn,r,e)
    assert 'historical_race_not_finished_by_cutoff' in decision(conn,r,e)['reasons']


@pytest.mark.parametrize('response',['not-json','{}','{"verdict":"allow","reason":false}','{"verdict":"allow","reason":""}'])
def test_malformed_votes_fail_closed(conn,response):
    r,e = run(conn),item(conn)
    assert record_vote(conn,r,e,'outcome',response,'fake','prompt')=='error'
    assert decision(conn,r,e)['decision']=='drop'


def test_one_drop_blocks_and_cannot_be_replaced(conn):
    r,e = run(conn),item(conn)
    record_vote(conn,r,e,'outcome','{"verdict":"drop","reason":"Synthetic leak"}','fake','prompt')
    for j in ['provenance','relevance']:
        record_vote(conn,r,e,j,'{"verdict":"allow","reason":"Synthetic"}','fake','prompt')
    assert decision(conn,r,e)['decision']=='drop'
    with pytest.raises(sqlite3.IntegrityError):
        record_vote(conn,r,e,'outcome','{"verdict":"allow","reason":"Synthetic"}','fake','prompt')


def test_packet_contains_only_whitelisted_evidence(conn,tmp_path):
    r,e = run(conn),item(conn)
    approve(conn,r,e)
    path = tmp_path/'packet.sqlite'
    out = export_packet(conn,r,path)
    assert out['evidence_count']==1
    packet = sqlite3.connect(path)
    assert {x[0] for x in packet.execute("SELECT name FROM sqlite_master WHERE type='table'")}=={'task','evidence'}
    assert packet.execute('SELECT count(*) FROM evidence').fetchone()[0]==1
    assert b'Synthetic Breeder' not in path.read_bytes()
    assert packet.execute('SELECT id FROM evidence').fetchone()[0]==e
    packet.close()
    with pytest.raises(FileExistsError):
        export_packet(conn,r,path)


def test_empty_packet_rejected(conn,tmp_path):
    path = tmp_path/'empty.sqlite'
    with pytest.raises(ValueError,match='No admissible'):
        export_packet(conn,run(conn),path)
    assert not path.exists()


@pytest.mark.parametrize('judges',[[],['a','b'],['a','a','b'],['a','b','']])
def test_panel_must_have_three_distinct_ids(conn,judges):
    with pytest.raises(ValueError):
        create_run(conn,'jce:2026-11-01:1:r1','2026-10-31T12:00:00Z',judges)


def test_timezone_and_unknown_start(conn):
    assert utc('2026-10-31T13:00:00+01:00')=='2026-10-31T12:00:00+00:00'
    with pytest.raises(ValueError,match='timezone'):
        utc('2026-10-31T12:00:00')
    with pytest.raises(ValueError,match='local race day'):
        create_run(conn,'jce:2026-11-01:1:r1','2026-10-31T23:00:00Z',JUDGES)
