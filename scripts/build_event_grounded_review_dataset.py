"""Freeze fresh assistant-reviewed scenarios before model evaluation; no outcome reads."""
import hashlib,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from horse_racing.benchmark import digest,verify
from horse_racing.engine.pipeline import public_task
ROOT=Path('data/event_grounded_review_v1');BUNDLE=Path('benchmarks/h1_2026_v2');verify(BUNDLE)
if (ROOT/'dataset.json').exists():raise FileExistsError('Frozen dataset already exists')
old=json.loads(Path('data/semantic_leakage_review_v1/dataset.json').read_text())
old_urls={json.loads((Path('data/semantic_leakage_review_v1')/r['file']).read_text())['url'] for r in old['snapshots'].values()}
old_texts={c['text'] for c in old['cases']}
tasks=[]
for row in map(json.loads,(BUNDLE/'diagnostic/tasks.jsonl').read_text().splitlines()):
 if row['split']=='development':tasks.append(public_task(json.loads((BUNDLE/f"diagnostic/packets/{row['race_id']}.json").read_text())))
def target(day,horse):return next(t for t in tasks if t['date']==day and any(horse in r['horse_name'] for r in t['runners']))
specs=[
('a01_undated_meeting_preview','jan18_preview',[0],'natural','2026-01-18','LEIVINHA','LEIVINHA','allow','preview','Future race conditions and participant preferences are plans/opinions, not a completed result.'),
('a02_undated_favorite_prediction','jan18_preview',[1],'natural','2026-01-18','SHUTTERWOOD','SHUTTERWOOD','allow','preview','This is a future 1800m handicap preview. Naming a favorite does not identify a realized winner.'),
('a03_undated_pair_prediction','jan25_preview',[1],'natural','2026-01-25','PASAPALABRA','PASAPALABRA','allow','preview','The five-runner 2200m target is explicitly prospective; Aniol and Pasapalabra are preferences.'),
('a04_same_horse_different_earlier_win','jan18_form_preview',[3],'publisher','2026-01-18','COGSWORTH','COGSWORTH','allow','earlier_history','January 15 publication anchors earlier performances, including Cogsworth autumn win in Madrid, before the January 18 target; predictions are separate from realized results.'),
('a05_prior_form_and_conditional_forecast','jan18_form_preview',[4],'publisher','2026-01-18','HELHEIM','HELHEIM','allow','earlier_history','January 15 publication anchors Helheim and Fiji Gold earlier form. Conditional success predictions do not reveal the target winner.'),
('a06_prior_winners_are_not_target_results','jan25_form_preview',[2],'publisher','2026-01-25','KING KAID','KING KAID','allow','earlier_history','January 22 publication precedes the target. King Kaid and Mi Niño earlier wins inform a prospective opinion; the phrase third describes a selection, not a finish.'),
('r01_target_with_jockey_substitution','jan18_official_report',[1],'natural','2026-01-18',"ARCHIE'S DREAM",'ARCHIE\'S DREAM','reject','target_leakage','Ocio Caballo 2100m, Archie’s Dream beating Flaming Glass and Gast a Gast, plus a rider substitution, identify the actual target outcome despite no supported publication timestamp.'),
('r02_target_order_same_field','jan18_official_report',[2],'natural','2026-01-18','SHUTTERWOOD','SHUTTERWOOD','reject','target_leakage','1800m A Galopar, Shutterwood/Spielman/Misstifly match the target field and disclose its finish.'),
('r03_target_trainer_first_win','jan18_official_report',[3],'natural','2026-01-18','COGSWORTH','COGSWORTH','reject','target_leakage','1500m Hipotour, Cogsworth ahead of Haya Taal and Smooth Transition, matches the target and also reveals trainer first win.'),
('r04_target_second_place_revealed','jan18_official_report',[4],'natural','2026-01-18','HELHEIM','HELHEIM','reject','target_leakage','Groupe Carrus and Helheim/Fiji Gold/Gloomy Rose identify target result and margins.'),
('r05_target_winner_other_named_favorite','jan18_official_report',[5],'natural','2026-01-18','BRAVO','BRAVO','reject','target_leakage','Black Type, Telemachus beating Bravo with Summercake third, identifies target even when the requested horse did not win.'),
('r06_later_preview_recalls_target','jan18_form_preview',[5],'withheld','2026-01-04','CROSS THE TRACKS','CROSS THE TRACKS','reject','target_leakage','The January 15 preview recalls Ambushed second behind Cross The Tracks in Madrid, identifying the January 4 target. Withheld source dates must not turn a recalled target result into usable earlier history.'),
('u01_undated_caption_completed_win','jan18_official_report',[0],'natural','2026-02-01','SHUTTERWOOD','SHUTTERWOOD','uncertain','ambiguous','Caption reports a Shutterwood win but does not date it. The title season 2025-2026 does not place this event before January 31.'),
('u02_different_distance_not_a_date','jan18_official_report',[2],'natural','2026-02-01','SHUTTERWOOD','SHUTTERWOOD','uncertain','ambiguous','1800m is a different event from the February 1 target; that mismatch alone cannot prove it occurred before cutoff.'),
('u03_different_race_unknown_chronology','jan18_official_report',[3],'natural','2026-02-01','COGSWORTH','COGSWORTH','uncertain','ambiguous','Cogsworth report is a different 1500m race from the target 1600m event, but supplies no absolute date. Treat chronology as unresolved.'),
('u04_unanchored_connection_result','jan18_official_report',[4],'natural','2026-02-01','FIJI GOLD','FIJI GOLD','uncertain','ambiguous','Fiji Gold placing in a different field is relevant form without a date; season title and field difference do not determine timing.'),
('c01_calendar_statistics_unrelated_to_horse','calendar_news',[1],'publisher','2026-01-18','LEIVINHA','LEIVINHA','reject','unrelated','Calendar counts and total prize money are not evidence of the requested horse form.'),
('c02_wrong_horse_photo_caption','jan25_preview',[0],'natural','2026-01-25','PASAPALABRA','PASAPALABRA','reject','unrelated','Caption names Muguetajarra rather than the requested horse; no target-horse performance or conditions are given.')]
cases=[];snapshots={}
for cid,sid,indices,dating,day,horse,entity,label,category,rationale in specs:
 path=ROOT/(sid+'.json');snapshot=json.loads(path.read_text());assert snapshot['url'] not in old_urls
 if dating=='natural':assert not snapshot['date_claims']
 if dating=='publisher':assert snapshot['date_claims']
 snapshots[sid]=dict(file=path.name,sha256=digest(path));text='\n\n'.join(snapshot['paragraphs'][i] for i in indices);assert text not in old_texts
 cases.append(dict(id=cid,source_snapshot=sid,paragraph_indices=indices,text=text,text_sha256=hashlib.sha256(text.encode()).hexdigest(),dating_scenario=dating,task=target(day,horse),information_need=dict(id=1,need='Pre-cutoff racing background about '+entity,query=entity),expected=label,category=category,review_rationale=rationale))
dataset=dict(version='event-grounded-review-v1',scope='18 fresh assistant-reviewed scenarios from six new publisher snapshots; development diagnostic, not independent human validation',
 review='Assistant assigned rationales/labels before model evaluation. New protocol was designed from the previous corpus failures; no tuning on this fresh set after model evaluation.',
 related_cases='Four ambiguous cases reuse paragraphs against different future targets; these are dependent context probes, not independent observations.',
 metadata_ablations='natural preserves genuinely absent supported parser dates. withheld deliberately removes known publication/update metadata; original URL/title remain visible. Full source dates are retained in supervisor snapshots.',
 previous_dataset_sha256=digest(Path('data/semantic_leakage_review_v1/dataset.json')),freshness='All six source URLs and all case text differ from the previous 24-scenario dataset',
 bundle_manifest_sha256=digest(BUNDLE/'manifest.json'),snapshots=snapshots,cases=cases)
(ROOT/'dataset.json').write_text(json.dumps(dataset,ensure_ascii=False,indent=2)+'\n')
(ROOT/'acquisition_gaps.json').write_text(json.dumps(dict(attempts_not_used=[dict(id='jan18_results',reason='TodoTurf HTML produced zero attributable paragraphs'),dict(id='jan18_opinions',reason='Giralda original fetch failed TLS certificate verification; not bypassed')]),indent=2)+'\n')
print('Frozen',len(cases),'fresh scenarios; dataset SHA256',digest(ROOT/'dataset.json'))
