#!/usr/bin/env python3
"""Freeze expanded training previews and test source-scoped extraction locally."""
import argparse
import json
from pathlib import Path
import sqlite3
import sys
from bs4 import BeautifulSoup
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from horse_racing.shared_forecast import write_json,digest,SYSTEM_ROOT
from horse_racing.article_features import normalized_name
from horse_racing.article_features_v2 import scoped_candidates,extract_article
from run_article_component import run,read,now


def expanded_sources():
    old=ROOT/'runs/agent_features_20261111_v2/public/sources.json'
    sources=read(old);inputs=[old];omissions=[]
    specs=[('jan18_form_full','2026-01-18','data/event_grounded_review_v1/jan18_form_preview.json','data/event_grounded_review_v1/cache/9cb2b62f52156a34baaa79b99f597e9f.json',None),
        ('jan25_form_full','2026-01-25','data/event_grounded_review_v1/jan25_form_preview.json','data/event_grounded_review_v1/cache/d04e39e8ef0f8a06260aba73200c4fa8.json',None),
        ('jan04_form_full','2026-01-04','data/article_expansion_20261112/jan04_form_preview.json','data/article_expansion_20261112/jan04_form_preview.html',None),
        ('jan11_form_full','2026-01-11','data/article_expansion_20261112/jan11_form_preview.json','data/article_expansion_20261112/jan11_form_preview.html',None),
        ('feb1_missing_context','2026-02-01','data/semantic_leakage_review_v1/feb1_preview.json','data/semantic_leakage_review_v1/cache/c02a82a027f70afa1d70905c27fe2e2d.json',{6,9})]
    for name,event,file,rawfile,indices in specs:
        file=ROOT/file;rawfile=ROOT/rawfile;d=read(file);inputs.extend([file,rawfile])
        published=[c for c in d['date_claims'] if c['kind']=='published']
        if not published:omissions.append(dict(source=name,reason='no_publication_claim'));continue
        available=max(c['value'] for c in d['date_claims'])
        raw=read(rawfile)['text'] if rawfile.suffix=='.json' else rawfile.read_text()
        soup=BeautifulSoup(raw,'html.parser');body=soup.select_one('article .entry-content')
        if body is None:raise ValueError('Missing article body')
        for i,p in enumerate(body.find_all('p')):
            if indices is not None and i not in indices:continue
            text=' '.join(p.get_text(' ',strip=True).split())
            if not text:continue
            meta=dict(source_type='publisher_article',target_event_date=event,historical_event_date=None,
                observed_at=d['observed_at'],body_sha256=d['body_sha256'],raw_receipt=str(rawfile),raw_receipt_hash=digest(rawfile),
                claims=d['date_claims'],paragraph_index=i,context='Complete article paragraph, no length filter',
                availability_assumption='Retrospective publisher-dated reconstruction; not independently archived')
            sources.append(dict(id=name+':'+str(i),title=d['metadata']['title'],text=text,url=d['url'],available_at=available,kind='archive',provenance=json.dumps(meta,ensure_ascii=False)))
    for name in ['jan18_preview','jan25_preview']:
        omissions.append(dict(source=name,reason='Cached official preview has no parsed publication claims; not admitted'))
    return sources,inputs,omissions


def prepare(out):
    out.mkdir(parents=True,exist_ok=False)
    source=ROOT/'runs/agent_features_20261111_v2/public/packets.json';packets=read(source)
    sources,inputs,omissions=expanded_sources();inputs.append(source)
    db=ROOT/'data/declarations_h1_2026.sqlite';inputs.append(db)
    c=sqlite3.connect('file:'+str(db)+'?mode=ro',uri=True)
    ordinals=dict(c.execute('SELECT race_id,ordinal FROM races'));c.close()
    tasks=[]
    for p in packets:
        race={k:p[k] for k in ['race_id','date','venue','cutoff_utc']};race['race_ordinal']=ordinals[p['race_id']]
        for r in p['runners']:
            views,excluded=scoped_candidates(race,r,sources)
            tasks.append(dict(race=race,runner={k:r[k] for k in ['runner_id','horse_name','cloth']},candidates=views,source_omissions=excluded))
    if sum(bool(t['candidates']) for t in tasks)>160:raise ValueError('Inference budget exceeded')
    refs=read(ROOT/'runs/article_component_20261112/references.json')
    original_ref_ids={r['runner_id'] for r in refs}
    extra=[('2026-01-04',n,'selected') for n in ['VIENTO DE LEVANTE','STEPINMYDIRECTION','SMOOTH TRANSITION','STAR ONE','KEY TO SUCCESS','REVENUE','MADAME CARACOL']]
    extra += [('2026-01-04',n,'opposed') for n in ['OTTO','FARNESIO','STEPHEN DEDALUS']]
    extra += [('2026-01-18',n,'selected') for n in ['LEIVINHA','MISSTIFLY','SHUTTERWOOD','HAYA TAAL','FIJI GOLD','HELHEIM','BRAVO']]
    extra += [('2026-01-25',n,'selected') for n in ['ANIOL','PASAPALABRA','KING KAID','HIGHLAND MARKET','PARTY ZONE','WANDERLUST','HEADHUNTER','PRINCE ANODIN','NATHAN']]
    for day,name,expected in extra:
        matches=[t for t in tasks if t['race']['date']==day and normalized_name(t['runner']['horse_name'])==normalized_name(name)]
        if len(matches)!=1:raise ValueError('Reference identity ambiguous '+name)
        t=matches[0];eligible=[c for c in t['candidates'] if c['scope']!='mention_in_another_horse_entry']
        if not eligible:raise ValueError('Reference has no current-runner evidence '+name)
        citation=next((v for v in eligible if v['scope']=='explicit_numbered_tip'),eligible[0])
        refs.append(dict(runner_id=t['runner']['runner_id'],horse=t['runner']['horse_name'],date=day,expected=expected,
            source_id=citation['source_id'],source_quote=citation['text'],reviewer='coding_assistant_source_review; independent human review pending'))
    for r in refs:r['reference_group']='existing_regression' if r['runner_id'] in original_ref_ids else 'additional_source_review'
    for name,data in [('tasks.json',tasks),('references.json',refs),('sources.json',sources),('source_omissions.json',omissions)]:write_json(out/name,data)
    inputs += [ROOT/'runs/article_component_20261112/references.json',*[out/n for n in ['tasks.json','references.json','sources.json','source_omissions.json']]]
    code=[Path(__file__).resolve(),ROOT/'scripts/run_article_component.py',ROOT/'horse_racing/article_features.py',ROOT/'horse_racing/article_features_v2.py',ROOT/'horse_racing/shared_forecast/__init__.py']+list((SYSTEM_ROOT/'forecast_system').glob('*.py'))
    for p in code:
        dest=out/'source_receipts'/('upstream' if p.is_relative_to(SYSTEM_ROOT) else 'study')/p.name
        dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(p.read_bytes())
    manifest=dict(created_at=now(),input_hashes={str(p):digest(p) for p in inputs},code_hashes={str(p):digest(p) for p in code},
        model='llama3.1:8b',gpu=3,api='http://127.0.0.1:11440',runner_rows=len(tasks),eligible_model_calls=sum(bool(t['candidates']) for t in tasks),
        maximum_model_calls=160,call_timeout=90,max_output_tokens=128,reference_rows=len(refs),corpus_sources=len(sources),
        quality_gate=dict(minimum_reference_accuracy=.90,critical_false_current_recommendations=0,maximum_schema_failures=0,
            minimum_correct_january_opposed_references=2),
        scope='Controlled source extraction. Expanded earlier training previews and recovered full context. Sources changed as well as extractor; not an isolated causal comparison.',
        evaluation_policy='Check extraction gate before any outcome evaluation; no February tuning; March-June untouched',
        reference_caveat='Assistant-reviewed development sources, not independent human annotation or unseen examples',publication='PROHIBITED. Local files only.')
    write_json(out/'manifest.json',manifest);write_json(out/'status.json',dict(status='prepared',planned=len(tasks),eligible_calls=manifest['eligible_model_calls']))
    print(json.dumps({k:manifest[k] for k in ['runner_rows','eligible_model_calls','reference_rows','corpus_sources']}))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--prepare',action='store_true');a=p.parse_args()
    if a.prepare:prepare(a.out.resolve())
    else:run(a.out.resolve(),extractor=extract_article)
