"""Synthetic HTML tests. Downloaded third-party pages are not needed by the test suite."""
import hashlib
import json
import sqlite3
from pathlib import Path
import pytest
from horse_racing.db import initialize,connect
from horse_racing.ingest import import_jce
from horse_racing.mdh import parse_result,import_result,ExcludedPage
from test_database import CARD


def html(day='05-10-2025',second_status='2',horse='SYNTHETIC ALPHA (GB)'):
    def row(pos,hid,name,weight):
        return f'''<tr><td>{pos}</td><td><a href="xcaballow.cfm?caballoID={hid}">{name}&nbsp;&nbsp;(8)</a></td>
        <td>{weight}</td><td><a href="ficha_jinete.cfm?idJinete=21">Synthetic Jockey</a></td>
        <td><a href="ficha_preparador.cfm?idPreparador=31">Synthetic Trainer</a></td>
        <td><a href="ficha_propietario.cfm?idPropietario=41">Synthetic Stable</a></td>
        <td>3</td><td></td><td>1/2</td><td>3,9</td></tr>'''
    return f'''<html><body>
    <font class="naranjaPremio">RESULTADO 2ª CARRERA - 367</font>
    <font class="naranjaPremio">Hipódromo de La Zarzuela 12:05 {day} ª Otoño</font>
    <font class="textoPremio">SYNTHETIC RACE</font>
    <p>Distancia: 1.100 L.R. metros Categoría: D Pista: Hierba Terreno: Bueno
    Dotación: 5.000, 2.000 Condición: Synthetic conditions.</p>
    <table><tr><td>Pto.</td><td>Caballo</td><td>Peso</td><td>Jinete</td><td>Preparador</td>
    <td>Propietario</td><td>CS</td><td></td><td>T. - Dif.</td><td>DG</td></tr>
    {row('1',1001,horse,'57-')}{row(second_status,1002,'SYNTHETIC BETA','59,5-58')}
    </table>Dividendos: G.: 3,9 Quienes Somos
    </body></html>'''


def test_parse_ids_weights_status_and_race_context():
    p=parse_result(html())
    assert p['race_number']==2 and p['race_date']=='2025-10-05'
    assert p['venue']=='La Zarzuela' and p['distance_m']==1100
    assert p['rows'][0]['horse_external']=='1001'
    assert p['rows'][0]['horse_name']=='SYNTHETIC ALPHA (GB)'
    assert p['rows'][0]['carried_weight_kg'] is None
    assert p['rows'][1]['carried_weight_kg']==58.0
    assert p['rows'][1]['assigned_weight_kg']==59.5
    assert p['rows'][1]['jockey']==('21','Synthetic Jockey')
    assert p['going_raw']=='Bueno' and p['surface_raw']=='Hierba'


def test_provider_codes_are_not_finishing_places():
    p=parse_result(html(second_status='95'))
    assert p['rows'][1]['status_raw']=='95'
    assert p['rows'][1]['position'] is None


def test_out_of_range_page_excluded():
    with pytest.raises(ExcludedPage,match='outside'):
        parse_result(html(day='22-08-1960'))
    with pytest.raises(ExcludedPage,match='venue'):
        parse_result(html().replace('La Zarzuela','Longchamp'))


def test_unknown_or_incomplete_table_rejected():
    with pytest.raises(ValueError,match='stable horse ID'):
        parse_result(html().replace('caballoID=1002','unknown=1002'))
    with pytest.raises(ValueError,match='Duplicate horse'):
        parse_result(html().replace('caballoID=1002','caballoID=1001'))
    out_of_range=parse_result(html(second_status='12'))['rows'][1]
    assert out_of_range['status_raw']=='12' and out_of_range['position'] is None


def test_import_idempotent_and_null_cloth_is_not_draw(tmp_path):
    c=initialize(tmp_path/'r.sqlite')
    body=html().encode()
    url='https://www.masdehipodromos.com/resultados2.cfm?jidPremio=50001'
    for _ in range(2):
        import_result(c,body,url,'2026-11-05T09:00:00Z')
    assert c.execute('SELECT count(*) FROM results').fetchone()[0]==2
    r=c.execute('SELECT * FROM results ORDER BY position').fetchone()
    assert r['cloth'] is None and r['draw']==3
    assert c.execute('SELECT count(*) FROM entries').fetchone()[0]==0
    assert c.execute('SELECT count(*) FROM entity_identifiers').fetchone()[0]==5
    assert c.execute('SELECT count(*) FROM snapshots').fetchone()[0]==1
    snap=c.execute('SELECT * FROM snapshots').fetchone()
    assert snap['media_type']=='text/html'
    assert hashlib.sha256(snap['body'].encode()).hexdigest()==snap['sha256']
    assert c.execute("SELECT count(*) FROM evidence WHERE kind='result'").fetchone()[0]==2
    assert not c.execute('PRAGMA foreign_key_check').fetchall()
    c.close()


def test_stable_ids_survive_display_name_changes(tmp_path):
    c=initialize(tmp_path/'r.sqlite')
    import_result(c,html(),'https://www.masdehipodromos.com/resultados2.cfm?jidPremio=50001','2026-11-05T09:00:00Z')
    import_result(c,html(day='12-10-2025',horse='ALPHA RENAMED'),'https://www.masdehipodromos.com/resultados2.cfm?jidPremio=50002','2026-11-05T09:01:00Z')
    assert c.execute("SELECT count(*) FROM entities WHERE kind='horse'").fetchone()[0]==2
    assert c.execute('SELECT count(*) FROM results').fetchone()[0]==4
    c.close()


def test_import_reuses_known_race_identity_across_sources(tmp_path):
    c=initialize(tmp_path/'r.sqlite')
    import_jce(c,CARD,'2025-10-05','1','La Zarzuela','2026-11-05T09:00:00Z')
    import_result(c,html().replace('2ª CARRERA','1ª CARRERA').replace('CARRERA - 367','CARRERA - 100').replace('1.100 L.R.','1.200 L.R.'),'https://www.masdehipodromos.com/resultados2.cfm?jidPremio=50001','2026-11-05T09:00:00Z')
    assert c.execute('SELECT count(*) FROM meetings').fetchone()[0]==1
    assert c.execute('SELECT count(*) FROM races').fetchone()[0]==1
    assert c.execute('SELECT race_id FROM race_identifiers').fetchone()[0]=='jce:2025-10-05:1:r1'
    c.close()


def test_v1_migration_preserves_seed_and_allows_unknown_cloth(tmp_path):
    path=tmp_path/'old.sqlite'
    c=connect(path)
    schema=Path('horse_racing/schema.sql').read_text().split('-- Source-provided')[0]
    schema=schema.replace('CHECK(version=3)','CHECK(version=1)').replace('schema_version VALUES(3)','schema_version VALUES(1)')
    schema=schema.replace('race_number INTEGER NOT NULL CHECK(race_number>0)\n);','race_number INTEGER NOT NULL CHECK(race_number>0), UNIQUE(meeting_id,race_number)\n);')
    schema=schema.replace('cloth INTEGER CHECK(cloth>0)','cloth INTEGER NOT NULL CHECK(cloth>0)')
    schema=schema.replace(', UNIQUE(race_version_id,horse_id)','')
    c.executescript(schema)
    import_jce(c,CARD,'2025-10-05','1','La Zarzuela','2026-11-05T09:00:00Z')
    before=[tuple(r) for r in c.execute('SELECT * FROM results ORDER BY id')]
    hashes=[tuple(r) for r in c.execute('SELECT id,sha256 FROM snapshots')]
    c.close()
    c=initialize(path)
    assert c.execute('SELECT version FROM schema_version').fetchone()[0]==3
    assert [tuple(r) for r in c.execute('SELECT * FROM results ORDER BY id')]==before
    assert [tuple(r) for r in c.execute('SELECT id,sha256 FROM snapshots')]==hashes
    import_result(c,html(),'https://www.masdehipodromos.com/resultados2.cfm?jidPremio=50001','2026-11-05T09:00:00Z')
    assert c.execute('SELECT count(*) FROM results WHERE cloth IS NULL').fetchone()[0]==2
    with pytest.raises(sqlite3.IntegrityError,match='append-only'):
        c.execute('UPDATE results SET position=2')
    c.close()


def test_invalid_source_weight_is_preserved_without_imputation(tmp_path):
    body=html().replace('59,5-58','61-5')
    parsed=parse_result(body)
    assert parsed['rows'][1]['assigned_weight_kg']==61
    assert parsed['rows'][1]['carried_weight_kg'] is None
    assert parsed['rows'][1]['field_warning']
    c=initialize(tmp_path/'r.sqlite')
    import_result(c,body,'https://www.masdehipodromos.com/resultados2.cfm?jidPremio=50001','2026-11-05T09:00:00Z')
    assert c.execute("SELECT count(*) FROM quality_issues WHERE code='invalid_source_weight'").fetchone()[0]==1
    assert c.execute("SELECT weight_raw FROM result_details WHERE weight_raw='61-5'").fetchone()[0]=='61-5'
    c.close()


def test_conflicting_ordinals_do_not_collapse_distinct_source_races(tmp_path):
    c=initialize(tmp_path/'r.sqlite')
    import_result(c,html(),'https://www.masdehipodromos.com/resultados2.cfm?jidPremio=50001','2026-11-05T09:00:00Z')
    import_result(c,html().replace('CARRERA - 367','CARRERA - 368'),'https://www.masdehipodromos.com/resultados2.cfm?jidPremio=50002','2026-11-05T09:00:00Z')
    assert c.execute('SELECT count(*) FROM races').fetchone()[0]==2
    assert c.execute('SELECT count(*) FROM latest_results').fetchone()[0]==4
    assert c.execute("SELECT count(*) FROM quality_issues WHERE code='conflicting_source_race_ordinal'").fetchone()[0]==1
    before = c.execute('SELECT count(*) FROM quality_issues').fetchone()[0]
    import_result(c,html(),'https://www.masdehipodromos.com/resultados2.cfm?jidPremio=50001','2026-11-05T09:00:00Z')
    assert c.execute('SELECT count(*) FROM quality_issues').fetchone()[0]==before
    c.close()


def test_latest_results_prefers_official_version_and_counts_once(tmp_path):
    from horse_racing.db import coverage
    c=initialize(tmp_path/'r.sqlite')
    import_jce(c,CARD,'2025-10-05','1','La Zarzuela','2026-11-05T08:00:00Z')
    body=html().replace('2ª CARRERA','1ª CARRERA').replace('CARRERA - 367','CARRERA - 100').replace('1.100 L.R.','1.200 L.R.')
    import_result(c,body,'https://www.masdehipodromos.com/resultados2.cfm?jidPremio=50001','2026-11-05T10:00:00Z')
    actual=c.execute('''SELECT DISTINCT s.source_id FROM latest_results x
      JOIN race_versions v ON v.id=x.race_version_id JOIN snapshots s ON s.id=v.snapshot_id''').fetchall()
    assert [r[0] for r in actual]==['jce']
    report=coverage(c)
    assert report['races']==1 and report['source_result_rows']==4 and report['selected_runner_rows']==2
    c.close()


def test_duplicate_annual_numbers_do_not_merge_distinct_provider_ids(tmp_path):
    c=initialize(tmp_path/'r.sqlite')
    import_result(c,html(),'https://www.masdehipodromos.com/resultados2.cfm?jidPremio=50001','2026-11-05T09:00:00Z')
    import_result(c,html().replace('2ª CARRERA','3ª CARRERA'),'https://www.masdehipodromos.com/resultados2.cfm?jidPremio=50002','2026-11-05T09:00:00Z')
    assert c.execute('SELECT count(*) FROM races').fetchone()[0]==2
    assert c.execute('SELECT count(*) FROM latest_results').fetchone()[0]==4
    assert c.execute("SELECT count(*) FROM quality_issues WHERE code='conflicting_source_annual_number'").fetchone()[0]==1
    c.close()


def test_v2_migration_preserves_historical_details_and_views(tmp_path):
    path=tmp_path/'v2.sqlite'
    c=connect(path)
    schema=Path('horse_racing/schema.sql').read_text().replace('CHECK(version=3)','CHECK(version=2)').replace('schema_version VALUES(3)','schema_version VALUES(2)')
    schema=schema.replace('race_number INTEGER NOT NULL CHECK(race_number>0)\n);','race_number INTEGER NOT NULL CHECK(race_number>0), UNIQUE(meeting_id,race_number)\n);')
    c.executescript(schema)
    import_result(c,html(),'https://www.masdehipodromos.com/resultados2.cfm?jidPremio=50001','2026-11-05T09:00:00Z')
    c.close()
    c=initialize(path)
    assert c.execute('SELECT version FROM schema_version').fetchone()[0]==3
    assert c.execute('SELECT count(*) FROM latest_results').fetchone()[0]==2
    assert c.execute('SELECT count(*) FROM result_details').fetchone()[0]==2
    assert not c.execute('PRAGMA foreign_key_check').fetchall()
    import_result(c,html().replace('CARRERA - 367','CARRERA - 368'),'https://www.masdehipodromos.com/resultados2.cfm?jidPremio=50002','2026-11-05T09:00:00Z')
    assert c.execute('SELECT count(*) FROM races').fetchone()[0]==2
    c.close()
