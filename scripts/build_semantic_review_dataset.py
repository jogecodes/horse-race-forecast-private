"""Freeze assistant-reviewed genuine excerpts; labels never enter judge payloads.

Run after acquisition snapshots exist. Date-withheld cases are explicit metadata-ablation
scenarios, not claims that their publishers omitted dates. Original URLs remain visible.
"""
import json,sys,hashlib
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from horse_racing.benchmark import digest,verify
from horse_racing.engine.pipeline import public_task

ROOT=Path('data/semantic_leakage_review_v1')
BUNDLE=Path('benchmarks/h1_2026_v2')
verify(BUNDLE)
if (ROOT/'dataset.json').exists():raise FileExistsError('Dataset is frozen; use a new version')
tasks=[]
for row in map(json.loads,(BUNDLE/'diagnostic/tasks.jsonl').read_text().splitlines()):
    if row['split']=='development':tasks.append(public_task(json.loads((BUNDLE/f"diagnostic/packets/{row['race_id']}.json").read_text())))

def target(day,horse):
    return next(t for t in tasks if t['date']==day and any(horse in r['horse_name'] for r in t['runners']))

# Every index below refers to a full extracted original paragraph, with no text rewriting.
# Review labels were assigned by the assistant before local-model evaluation. They are
# not independent human adjudication, and uncertain cases are conservative judgments.
specs=[
 ('a01_prior_season_stats','prior_november',[1],'publisher','2026-01-11','SHAMRAN','V. JANACEK','allow','earlier_history','Known November 2025 publication anchors today and the 85-win total before January 2026.'),
 ('a02_earlier_winner','prior_november',[3],'publisher','2026-01-11','SHAMRAN','V. JANACEK','allow','earlier_history','A named different November 2025 race is completed history, not the January target outcome.'),
 ('a03_earlier_connections','prior_november',[4],'publisher','2026-01-11','SHAMRAN','G. ARIZKORRETA','allow','earlier_history','Earlier Cudillero result is relevant trainer history with a pre-cutoff publication date.'),
 ('a04_explicit_earlier_date_unknown_publication','jan4_results',[0,1],'withheld','2026-02-01','MADAME CARACOL','V. JANACEK','allow','earlier_history','The unchanged January 4, 2026 date and narrative anchor completed performances before the January 31 cutoff even with publication metadata withheld.'),
 ('a05_undated_target_preview','jan11_preview',[1,2],'natural','2026-01-11','JUSTCALLMESERGIO','JUSTCALLMESERGIO','allow','preview','Future plans and an opinion about Justcallmesergio before the explicitly described January 11 meeting; no realized target outcome. Parser found no supported publication date.'),
 ('a06_undated_favorite_is_opinion','jan11_preview',[3],'natural','2026-01-11','IFACH','IFACH','allow','preview','Specialist favorites are pre-race opinions, not a disclosure of a completed result.'),
 ('a07_mixed_prior_form_and_plan','feb1_preview',[2],'publisher','2026-02-01','ROMEO','ROMEO','allow','preview','January 29 publication anchors prior performances and February 1 forecasts. Mentions of earlier wins do not describe target results.'),
 ('a08_mixed_earlier_and_future_plan','jan5_mixed',[1],'publisher','2026-01-11','JUSTCALLMESERGIO','O. ANAYA','allow','preview','January 5 publication places the previous meeting before cutoff and the January 11 ambitions in the future.'),
 ('r01_target_finish_order','jan4_results',[5],'withheld','2026-01-04','KEY TO SUCCESS','KEY TO SUCCESS','reject','target_leakage','The eight-horse 1900m Baltasar narrative identifies the same field and states Key To Success, Farnesio and Irish Breath finish order.'),
 ('r02_target_winner_without_date','jan4_results',[6],'withheld','2026-01-04','MADAME CARACOL','MADAME CARACOL','reject','target_leakage','Diurno 1200m with eleven entrants matches the target and reports its winner and placings.'),
 ('r03_target_winner_implicit_meeting','jan11_results',[0,1],'withheld','2026-01-11','JUSTCALLMESERGIO','JUSTCALLMESERGIO','reject','target_leakage','First 2026 Dos Hermanas meeting and Justcallmesergio win reveal this target. The original URL also supplies the meeting date.'),
 ('r04_target_in_meeting_summary','jan4_results',[1],'withheld','2026-01-04','FLAMING GLASS','FLAMING GLASS','reject','target_leakage','Flaming Glass win in the named Premio Gaspar reveals the target even without a standalone date.'),
 ('r05_target_stewards_incident','jan11_results',[0,4],'withheld','2026-01-11','SPANISH RULER','SPANISH RULER','reject','target_leakage','Spanish Ruler, Sweet Wish and a demotion incident identify the target and disclose its realized outcome.'),
 ('r06_late_source_with_earlier_background','jan11_results',[2],'publisher','2026-01-11','FLIGHT LEADER','FLIGHT LEADER','reject','known_postcutoff_source','Publication is January 11 after the previous-day cutoff. Even benign earlier background cannot override the explicit source-date block.'),
 ('r07_known_postcutoff_report','jan4_results',[5],'publisher','2026-01-04','KEY TO SUCCESS','KEY TO SUCCESS','reject','known_postcutoff_source','Known January 4 publication is after January 3 cutoff; metadata must still block it.'),
 ('r08_later_preview_reveals_target_result','feb1_preview',[2],'withheld','2026-01-04','MADAME CARACOL','MADAME CARACOL','reject','target_leakage','The later preview calls Madame Caracol a winner in Madrid 1200m by 2.5+2.5 lengths, identifying the January 4 target; January 29 URL is another later-context clue.'),
 ('u01_unanchored_season_total','prior_november',[1],'withheld','2026-01-11','SHAMRAN','V. JANACEK','uncertain','ambiguous','With publication metadata withheld, today and this year cannot be placed relative to cutoff. The URL has no date.'),
 ('u02_unanchored_team_season','prior_november',[2],'withheld','2026-01-11','SHAMRAN','G. ARIZKORRETA','uncertain','ambiguous','No event date anchors these new wins or this season; current performance may describe earlier or later history.'),
 ('u03_unanchored_different_race','prior_november',[4],'withheld','2026-01-11','SHAMRAN','G. ARIZKORRETA','uncertain','ambiguous','Different-race results may be useful, but this paragraph supplies no year/date placing them before cutoff.'),
 ('u04_unanchored_horse_result','prior_november',[5],'withheld','2026-01-11','STARSHADOW','STARSHADOW','uncertain','ambiguous','Starshadow result describes a 2100m race but provides no date. Do not infer historical availability from a different distance.'),
 ('u05_unanchored_trainer_result','prior_november',[6],'withheld','2026-02-01','DONENTAL','B. RAMA','uncertain','ambiguous','Trainer win has no temporal anchor when metadata is withheld; same connection does not establish pre-cutoff timing.'),
 ('u06_unknown_date_other_meeting','jan4_results',[4],'withheld','2026-02-01','MADAME CARACOL','A. SOTO','uncertain','ambiguous','A different-race Flaming Glass result is relevant trainer history, but standalone paragraph gives no event date. URL hints start of 2026 without resolving exact timing; conservative uncertainty label.'),
 ('c01_unrelated_venue_description','prior_november',[9],'publisher','2026-01-11','SHAMRAN','V. JANACEK','reject','unrelated','Venue architecture and green-space description does not supply requested jockey-performance evidence.'),
 ('c02_unrelated_amenities','jan11_preview',[7],'natural','2026-01-11','JUSTCALLMESERGIO','JUSTCALLMESERGIO','reject','unrelated','Parking and food amenities do not inform the requested horse form.')
]
cases=[];snapshots={}
for cid,sid,indices,dating,day,horse,entity,label,category,rationale in specs:
    path=ROOT/(sid+'.json');snapshot=json.loads(path.read_text());snapshots[sid]=dict(file=path.name,sha256=digest(path))
    text='\n\n'.join(snapshot['paragraphs'][i] for i in indices)
    if dating=='natural':assert not snapshot['date_claims']
    cases.append(dict(id=cid,source_snapshot=sid,paragraph_indices=indices,text=text,text_sha256=hashlib.sha256(text.encode()).hexdigest(),dating_scenario=dating,
      task=target(day,horse),information_need=dict(id=1,need='Pre-cutoff racing background about '+entity,query=entity),
      expected=label,category=category,review_rationale=rationale))
dataset=dict(version='semantic-leakage-review-v1',scope='24 assistant-reviewed genuine excerpt scenarios from six publisher snapshots; small diagnostic corpus, not an independent human benchmark',
    review='Assistant read extracted source paragraphs and assigned labels/rationales before model execution. No independent human review. No prompt tuning on model results.',
    metadata_ablations='withheld removes publication/update claims only; original URL and title remain visible, and may themselves contain temporal clues. natural uses actual missing parser date metadata. Full source dating remains preserved in supervisor snapshots.',
    related_cases='Repeated paragraphs and sources are paired metadata/context probes; counts are not independent observations. Uncertain labels express conservative temporal judgments.',
    bundle_manifest_sha256=digest(BUNDLE/'manifest.json'),snapshots=snapshots,cases=cases)
(ROOT/'dataset.json').write_text(json.dumps(dataset,ensure_ascii=False,indent=2)+'\n')
print('Frozen',len(cases),'reviewed scenarios from',len(snapshots),'sources; dataset SHA256',digest(ROOT/'dataset.json'))
