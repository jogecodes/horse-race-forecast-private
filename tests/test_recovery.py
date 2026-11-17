import json
from pathlib import Path
import pytest
from horse_racing.recovery import parse_declaration,publisher_timing
from horse_racing.recovered_benchmark import identity
from horse_racing.start_times import parse_finish_start,quote_timing


def declaration(day='04/01/2026'):
    return f'''Programa del día {day}
    1ª CARRERA - Premio Sintético - 8.000 Euros a repartir - 1.200 mts. Hora: 12:00 h.
Nº CABALLO       EDAD   KG     JINETE       CUADRA       ENTRENADOR       CAJÓN   Últ. actuaciones
1  ALPHA (IRE)   3 años  57    J.TEST        STABLE A     T.TEST            1       [1,2,3]
2  BETA (FR)     3 años  56    K.TEST  (55)  STABLE B     U.TEST            2       [  Debutante   ]
3  GAMMA         3 años  55    L.TEST        STABLE C     V.TEST            3       [Ret,3]
Incidencias: el entrenador declara al jockey en la 2ª carrera.
'''


def test_parse_full_field_without_result_names():
    races=parse_declaration(declaration(),'2026-01-04')
    assert len(races)==1 and len(races[0]['runners'])==3 and not races[0]['issues']
    assert races[0]['runners'][1]['horse_name']=='BETA (FR)'
    assert races[0]['runners'][1]['jockey_name']=='K.TEST (55)'
    assert races[0]['runners'][1]['prior_form_raw']=='[  Debutante   ]'
    with pytest.raises(ValueError,match='date'):parse_declaration(declaration(),'2026-02-04')


def test_parse_spanish_named_date_and_plain_form():
    text=declaration().replace('Programa del día 04/01/2026','PARTICIPANTES DEFINITIVOS PARA LAS CARRERAS DEL DOMINGO, 4 DE ENERO DE 2026')
    text=text.replace('1ª CARRERA - Premio','1 ª CARRERA PREMIO').replace('[Ret,3]','Ret,3')
    races=parse_declaration(text,'2026-01-04')
    assert not races[0]['issues'] and races[0]['runners'][-1]['prior_form_raw']=='Ret,3'


def test_bad_row_cannot_silently_shrink_field():
    text=declaration().replace('3  GAMMA         3 años  55','3  GAMMA         UNKNOWN  55')
    r=parse_declaration(text,'2026-01-04')[0]
    assert r['issues'][0]['code']=='unparsed_entry'


def test_publisher_dates_are_never_independent_archive_proof():
    d=dict(date_claims=dict(pdf_created_at='2026-01-02T12:00:00Z',pdf_modified_at='2026-01-02T12:00:00Z'))
    t=publisher_timing(d,'2026-01-03T22:59:00Z')
    assert t['tier']=='publisher_dates_consistent_before_cutoff' and not t['strict_eligible']
    d['date_claims']['pdf_modified_at']='2026-01-05T12:00:00Z'
    assert publisher_timing(d,'2026-01-03T22:59:00Z')['tier']=='publication_time_unverified'


def test_rendering_identity_keeps_countries_and_handles_acute_apostrophe():
    assert identity('ANNIE´S SONG (FR)')==identity("Annie's Song (FR)")
    assert identity('ECLAIR LANE (IRE)')==identity('ECLAIRLANE (IRE)')
    assert identity('LIBERTY BLEU (FB)')!=identity('LIBERTY BLEU (FR)')


def test_actual_start_retains_hundredths_and_dst():
    actual=parse_finish_start('Hora de la Salida: 16/04/2026 11:06:02.59','2026-04-16')
    assert actual=='2026-04-16T09:06:02.590000+00:00'
    assert quote_timing('2026-04-16T09:06:02Z',actual)==(.59,'last_60_seconds_before_actual_start')
    assert quote_timing('2026-04-16T09:06:12Z',actual)==(-9.41,'at_or_after_actual_start')
    assert parse_finish_start('Hora de la Salida: 04/01/2026 12:00:00')=='2026-01-04T11:00:00+00:00'
    with pytest.raises(ValueError):parse_finish_start('Scheduled start: 11:05')
    with pytest.raises(ValueError):parse_finish_start('Hora de la Salida: 25/10/2026 02:30:00')
    with pytest.raises(ValueError):parse_finish_start('Hora de la Salida: 16/04/2026 11:06:02.59','2026-04-17')


def test_recovered_bundle_retains_declared_absentees_and_hides_supervisor_data(tmp_path,monkeypatch):
    import horse_racing.recovered_benchmark as module
    from horse_racing.benchmark import write_jsonl,verify,read_jsonl
    old=tmp_path/'old';(old/'diagnostic/packets').mkdir(parents=True);(old/'supervisor').mkdir()
    task=dict(race_id='r',date='2026-01-04',venue='Synthetic',split='development',cutoff_utc='2026-01-03T22:59:00+00:00',distance_m=1200,
        runners=[dict(runner_id='a',horse_name='ALPHA (IRE)'),dict(runner_id='b',horse_name='BETA (FR)')])
    (old/'diagnostic/packets/r.json').write_text(json.dumps(task))
    write_jsonl(old/'diagnostic/tasks.jsonl',[{k:v for k,v in task.items() if k!='runners'}])
    write_jsonl(old/'supervisor/cases.jsonl',[dict(race_id='r',meeting_id='m',source_race_id='source-r',runner_mapping=dict(a='horse-a',b='horse-b'))])
    write_jsonl(old/'supervisor/labels.jsonl',[dict(race_id='r',target=dict(a=1.0,b=0.0))])
    (old/'manifest.json').write_text(json.dumps(dict(version='synthetic-v1',files={})))
    recovery=tmp_path/'recovery.json'
    doc=dict(text=declaration(),date_claims=dict(pdf_created_at='2026-01-02T12:00:00+00:00',pdf_modified_at='2026-01-02T12:00:00+00:00'),
       receipt=dict(url='https://example.test/card.pdf',sha256='synthetic-hash',observed_at='2026-11-05T12:00:00+00:00'))
    recovery.write_text(json.dumps(dict(records=[dict(date='2026-01-04',venue='Synthetic',kind='declaration',document=doc)])))
    monkeypatch.setattr(module,'RECOVERIES',[str(recovery)])
    out=tmp_path/'new';manifest=module.build(out,old)
    assert manifest['races']==1 and manifest['runners']==3 and manifest['additional_declared_runners']==1
    assert verify(out)['version']==module.VERSION
    packet=json.loads((out/'diagnostic/packets/r.json').read_text())
    assert 'target' not in packet and len(packet['runners'])==3 and 'history_through_2025' not in json.dumps(packet)
    y=read_jsonl(out/'supervisor/labels.jsonl')[0]['target']
    assert len(y)==3 and y['a']==1 and sum(y.values())==1
    with pytest.raises(FileExistsError):module.build(out,old)
