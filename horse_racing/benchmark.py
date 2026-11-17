"""Frozen H1-2026 retrospective benchmark, independently audited against TodoTurf.

Reconstructed result-derived inputs are diagnostic only. They are never certified
pre-cutoff research evidence and do not relax the study's strict admission gate.
"""
from __future__ import annotations
import hashlib
import json
import math
import random
import re
import sqlite3
import tempfile
import unicodedata
from collections import Counter,defaultdict
from datetime import date,datetime,time,timedelta
from pathlib import Path
from zoneinfo import ZoneInfo
from bs4 import BeautifulSoup
from .db import utc,uid
from .mdh import canonical_venue

VERSION='spain-h1-2026-v1'
SEED=2026
EPSILON=1e-15


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def dumps(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,allow_nan=False)


def read_jsonl(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def write_jsonl(path,rows):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(''.join(dumps(row)+'\n' for row in rows))


def name_key(value):
    value=value.replace('’',"'").replace('`',"'")
    return ' '.join(unicodedata.normalize('NFKD',value).encode('ascii','ignore').decode().upper().split())


def split_for(day):
    if not '2026-01-01'<=day<='2026-06-30':raise ValueError('Race outside H1 2026')
    return 'development' if day<'2026-03-01' else 'validation' if day<'2026-05-01' else 'test'


def cutoff_for(day):
    prior=date.fromisoformat(day)-timedelta(days=1)
    return utc(datetime.combine(prior,time(23,59),ZoneInfo('Europe/Madrid')).isoformat())


def todo_rows(body):
    # TodoTurf includes conflicting charset declarations; its actual payload is UTF-8.
    # Decode strictly so Ñ/ñ is not mistaken for two Latin-1 characters.
    text=body.decode('utf-8') if isinstance(body,bytes) else body
    soup=BeautifulSoup(text,'html.parser');rows=[]
    for tr in soup.select('table tbody tr'):
        cells=tr.find_all('td',recursive=False)
        if len(cells)!=7:raise ValueError('Unexpected TodoTurf result column count')
        a=cells[1].find('a')
        if a is None:raise ValueError('TodoTurf horse link missing')
        status=cells[0].get_text(' ',strip=True)
        match=re.fullmatch(r'(\d+)(?:\s*\([^)]*\))?',status)
        pos=int(match[1]) if match and 0<int(match[1])<90 else None
        rows.append(dict(name=a.get_text(' ',strip=True),position=pos,status=status))
    if not rows or not any(r['position']==1 for r in rows):raise ValueError('TodoTurf result/winner missing')
    if len({name_key(r['name']) for r in rows})!=len(rows):raise ValueError('Ambiguous duplicate TodoTurf horse name')
    return rows


def selected_rows(conn):
    return [dict(r) for r in conn.execute('''SELECT x.*,e.name AS horse_name,m.race_date,m.venue,m.id AS meeting_id,
      r.race_number,v.title,v.distance_m,s.source_id,s.observed_at,s.sha256 AS snapshot_sha256,s.url
      FROM latest_results x JOIN entities e ON e.id=x.horse_id JOIN races r ON r.id=x.race_id
      JOIN meetings m ON m.id=r.meeting_id JOIN race_versions v ON v.id=x.race_version_id
      JOIN snapshots s ON s.id=v.snapshot_id ORDER BY m.race_date,m.venue,r.id,x.horse_id''')]


def history_before_2026(rows):
    races=defaultdict(list)
    for row in rows:
        if row['race_date']<'2026-01-01':races[row['race_id']].append(row)
    history=defaultdict(lambda:dict(starts=0,win_share=0.0,last_race_date=None))
    accepted=[]
    for group in races.values():
        winners=sum(r['position']==1 for r in group)
        if not winners or any(r['position'] is None for r in group):continue
        for row in group:
            h=history[row['horse_id']];h['starts']+=1
            h['win_share']+=1/winners if row['position']==1 else 0
            h['last_race_date']=row['race_date']
            accepted.append({k:row[k] for k in ['race_id','race_date','venue','horse_id','horse_name','position','observed_at','snapshot_sha256']})
    return history,accepted


def build(db_path,cache_dir,out_dir):
    out=Path(out_dir)
    if out.exists():raise FileExistsError(f'Benchmark already exists: {out}; use a new version directory')
    cache=Path(cache_dir);source_manifest=json.loads((cache/'manifest.json').read_text())
    conn=sqlite3.connect('file:'+str(Path(db_path).resolve())+'?mode=ro',uri=True);conn.row_factory=sqlite3.Row
    rows=selected_rows(conn);conn.close()
    history,history_records=history_before_2026(rows)
    candidates=defaultdict(list)
    for row in rows:
        if '2026-01-01'<=row['race_date']<='2026-06-30':
            # Annual number is parsed from the already preserved version, not assumed to be unique.
            candidates[(row['race_date'],row['venue'],row['race_number'])].append(row)
    tasks=[];labels=[];cases=[];exclusions=[];admission=[];secondary_audit=[];packets={};used=set()
    for source in sorted(source_manifest['races'],key=lambda r:(r['date'],r['venue'],r['ordinal'])):
        venue,_=canonical_venue(source['venue'])
        key=(source['date'],venue,source['ordinal']);group=candidates.get(key,[])
        reasons=[];todo=[]
        if not group:reasons.append('missing_primary_database_race')
        elif len({r['race_id'] for r in group})!=1:reasons.append('ambiguous_primary_race_identity')
        metadata=json.loads((cache/source['metadata']).read_text())
        if digest(cache/source['file'])!=source['sha256'] or source['sha256']!=metadata['sha256']:
            raise ValueError('TodoTurf cache hash mismatch')
        try:todo=todo_rows((cache/source['file']).read_bytes())
        except ValueError as e:reasons.append('invalid_secondary_result:'+str(e))
        if group:
            if len(group)<3:reasons.append('fewer_than_three_recorded_runners')
            if any(r['position'] is None for r in group):reasons.append('unresolved_primary_runner_status')
            if len({name_key(r['horse_name']) for r in group})!=len(group):reasons.append('ambiguous_primary_horse_names')
            if not any(r['position']==1 for r in group):reasons.append('primary_winner_missing')
            if any(r['position'] and r['position']>len(group) for r in group):reasons.append('invalid_primary_position')
        if todo:
            if any(r['position'] is None for r in todo):reasons.append('unresolved_secondary_runner_status')
            if group:
                if {name_key(r['horse_name']) for r in group}!={name_key(r['name']) for r in todo}:
                    reasons.append('cross_source_field_disagreement')
                if {name_key(r['horse_name']) for r in group if r['position']==1}!={name_key(r['name']) for r in todo if r['position']==1}:
                    reasons.append('cross_source_winner_disagreement')
        secondary_audit.append(dict(date=source['date'],venue=venue,ordinal=source['ordinal'],
            secondary_url=source['url'],secondary_sha256=source['sha256'],secondary_file=source['file'],
            secondary_rows=todo,primary_rows=[{k:r[k] for k in ['race_id','horse_name','position','status_raw','snapshot_sha256']} for r in group],
            decision='exclude' if reasons else 'include',reasons=reasons))
        if reasons:
            exclusions.append(dict(date=source['date'],venue=venue,ordinal=source['ordinal'],reasons=reasons,
                                   primary_race_ids=sorted({r['race_id'] for r in group}),secondary_url=source['url']))
            continue
        rid=group[0]['race_id']
        if rid in used:raise ValueError('A primary race matched multiple secondary races')
        used.add(rid);bid='race_'+uid(VERSION,rid);cutoff=cutoff_for(source['date'])
        ordered=sorted(group,key=lambda row:uid(SEED,rid,row['horse_id']))
        runners=[];mapping={};winner_count=sum(r['position']==1 for r in ordered);target={}
        for row in ordered:
            runner='runner_'+uid(VERSION,rid,row['horse_id']);mapping[runner]=row['horse_id']
            prior=history.get(row['horse_id'],dict(starts=0,win_share=0.0,last_race_date=None))
            if prior['last_race_date'] and prior['last_race_date']>='2026-01-01':raise ValueError('History leaked past frozen training boundary')
            runners.append(dict(runner_id=runner,horse_name=row['horse_name'],history_through_2025=dict(prior)))
            target[runner]=1/winner_count if row['position']==1 else 0.0
        task=dict(benchmark_version=VERSION,race_id=bid,date=source['date'],venue=venue,
                  split=split_for(source['date']),cutoff_utc=cutoff,distance_m=group[0]['distance_m'],
                  track='retrospective_diagnostic',input_availability='unverified_result_reconstruction',
                  instruction='Assign a win probability to every listed runner; return race_id and probabilities keyed by runner_id. Probabilities must sum to one.',
                  runners=runners)
        packets[bid]=task
        tasks.append({k:task[k] for k in ['race_id','date','venue','split','cutoff_utc','track']})
        label=dict(race_id=bid,target=target,dead_heat=winner_count>1)
        labels.append(label)
        cases.append(dict(race_id=bid,source_race_id=rid,meeting_id=group[0]['meeting_id'],runner_mapping=mapping,
                          primary_url=group[0]['url'],primary_snapshot_sha256=group[0]['snapshot_sha256'],
                          primary_observed_at=group[0]['observed_at'],secondary_url=source['url'],
                          secondary_sha256=source['sha256'],secondary_observed_at=metadata['observed_at']))
        admission.append(dict(race_id=bid,strict_admissible=False,
            deterministic_reasons=['roster_reconstructed_from_target_result','no_verified_pre_cutoff_roster',
                                   'history_publication_times_unverified'],
            primary_observed_after_cutoff=utc(group[0]['observed_at'])>cutoff,
            secondary_observed_after_cutoff=utc(metadata['observed_at'])>cutoff,
            required_judges=['provenance','outcome','relevance'],judge_votes='not_run',
            override_allowed=False))
    for key,group in candidates.items():
        if group[0]['race_id'] not in used and not any(e['date']==key[0] and e['venue']==key[1] and e['ordinal']==key[2] for e in exclusions):
            exclusions.append(dict(date=key[0],venue=key[1],ordinal=key[2],reasons=['missing_secondary_index_entry'],primary_race_ids=sorted({r['race_id'] for r in group})))
    if not tasks:raise ValueError('No cross-validated benchmark races')
    out.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.benchmark-',dir=out.parent) as tmp:
        bundle=Path(tmp)/'bundle';bundle.mkdir()
        write_jsonl(bundle/'diagnostic/tasks.jsonl',tasks)
        for rid,packet in packets.items():
            p=bundle/f'diagnostic/packets/{rid}.json';p.parent.mkdir(parents=True,exist_ok=True);p.write_text(dumps(packet)+'\n')
        write_jsonl(bundle/'supervisor/labels.jsonl',labels)
        write_jsonl(bundle/'supervisor/cases.jsonl',cases)
        write_jsonl(bundle/'supervisor/exclusions.jsonl',exclusions)
        write_jsonl(bundle/'supervisor/secondary_audit.jsonl',secondary_audit)
        write_jsonl(bundle/'supervisor/admission_audit.jsonl',admission)
        write_jsonl(bundle/'supervisor/history_before_2026.jsonl',history_records)
        policy=dict(version=VERSION,selection='All indexed H1-2026 Spanish races meeting the frozen quality rules; no sampling by outcome',
                    development=['2026-01-01','2026-02-28'],validation=['2026-03-01','2026-04-30'],test=['2026-05-01','2026-06-30'],
                    history_end='2025-12-31',history_updates_during_h1=False,cutoff='23:59 Europe/Madrid on the preceding calendar day',
                    minimum_runners=3,dead_heat='Equal target mass over all first-place finishers',
                    primary_metric='Race-weighted multiclass Brier: sum((p_i-y_i)^2)',
                    secondary_metric='Cross entropy with fixed 1e-15 probability floor; zero winning probabilities reported',
                    intervals='95% meeting-cluster bootstrap; 1000 resamples; seed 2026',seed=SEED,
                    uniform_baseline='p=1/N',history_baseline='Normalize (pre-2026 win_share+1)/(pre-2026 starts+10); no tuning',
                    invalid_predictions='Excluded from scores; coverage and error reasons reported; never imputed',
                    strict_ready_cases=0,retrospective_only=True)
        (bundle/'protocol.json').write_text(dumps(policy)+'\n')
        (bundle/'README.md').write_text('# Spain H1 2026 benchmark\n\nThis frozen bundle is a retrospective diagnostic with independently checked fields and winners.\n\n**No case is certified for strict historical researched forecasting.** All rosters are reconstructed from results collected after the race, and pre-2026 histories have unverified publication times. The strict gate must reject these inputs.\n\nMount only one `diagnostic/packets/<race_id>.json` in a forecaster process. Keep `supervisor/`, all other packets, the master database and the raw caches inaccessible. Disable direct network access for the forecaster; any agent research must pass the existing source-time/judge gate.\n\nDevelopment: January–February; validation: March–April; test: May–June. All history features are frozen through 2025, including for later test races. See `protocol.json` for scoring and exclusions, and the study `docs/BENCHMARK_H1_2026.md` for commands. Baseline results are plumbing/diagnostic measurements, not evidence of leak-free forecasting skill.\n')
        files={str(p.relative_to(bundle)):digest(p) for p in sorted(bundle.rglob('*')) if p.is_file()}
        manifest=dict(version=VERSION,builder_sha256=digest(__file__),database_sha256=digest(db_path),secondary_index_manifest_sha256=digest(cache/'manifest.json'),
            candidate_database_races=len({r['race_id'] for g in candidates.values() for r in g}),
            secondary_index_races=len(source_manifest['races']),included_races=len(tasks),excluded_candidates=len(exclusions),
            splits=dict(Counter(t['split'] for t in tasks)),months=dict(sorted(Counter(t['date'][:7] for t in tasks).items())),
            venues=dict(Counter(t['venue'] for t in tasks)),runner_rows=sum(len(p['runners']) for p in packets.values()),
            strict_ready_cases=0,files=files)
        (bundle/'manifest.json').write_text(dumps(manifest)+'\n');bundle.rename(out)
    return manifest


def verify(bundle):
    root=Path(bundle);manifest=json.loads((root/'manifest.json').read_text())
    for relative,expected in manifest['files'].items():
        path=root/relative
        if path.resolve().is_relative_to(root.resolve()) is False:raise ValueError('Unsafe artifact path')
        if digest(path)!=expected:raise ValueError(f'Benchmark artifact changed: {relative}')
    return manifest


def baseline_predictions(bundle,kind):
    verify(bundle);root=Path(bundle);predictions=[]
    if kind not in ('uniform','history'):raise ValueError('Unknown baseline')
    for task in read_jsonl(root/'diagnostic/tasks.jsonl'):
        packet=json.loads((root/f'diagnostic/packets/{task["race_id"]}.json').read_text())
        weights={r['runner_id']:1.0 if kind=='uniform' else (r['history_through_2025']['win_share']+1)/(r['history_through_2025']['starts']+10) for r in packet['runners']}
        total=sum(weights.values())
        predictions.append(dict(race_id=task['race_id'],probabilities={k:v/total for k,v in weights.items()}))
    return predictions


def validate_prediction(value,expected):
    if not isinstance(value,dict) or set(value)!=set(expected):return 'runner_set_mismatch'
    if any(isinstance(p,bool) or not isinstance(p,(float,int)) or not math.isfinite(p) or p<0 or p>1 for p in value.values()):return 'invalid_probability'
    if abs(sum(value.values())-1)>1e-6:return 'probabilities_do_not_sum_to_one'
    return None


def metrics(probabilities,target):
    brier=sum((probabilities[k]-target[k])**2 for k in target)
    loss=-sum(y*math.log(max(probabilities[k],EPSILON)) for k,y in target.items() if y)
    top=max(probabilities.values());tied=[k for k,v in probabilities.items() if v==top]
    accuracy=sum(target[k] for k in tied)/len(tied)
    return dict(brier=brier,log_loss=loss,top1_fractional_accuracy=accuracy,
                zero_probability_winner=any(y and probabilities[k]==0 for k,y in target.items()),
                uniform_brier=sum((1/len(target)-y)**2 for y in target.values()),uniform_log_loss=math.log(len(target)))


def mean(values):return sum(values)/len(values)


def interval(values):
    values=sorted(values)
    def percentile(q):
        i=(len(values)-1)*q;lo=int(i);hi=min(lo+1,len(values)-1)
        return values[lo]+(i-lo)*(values[hi]-values[lo])
    return [percentile(.025),percentile(.975)]


def aggregate(rows,bootstrap=1000):
    if not rows:return dict(scored_races=0)
    keys=['brier','log_loss','top1_fractional_accuracy']
    result={k:mean([r[k] for r in rows]) for k in keys}
    result.update(scored_races=len(rows),zero_probability_winners=sum(r['zero_probability_winner'] for r in rows),
                  brier_skill_vs_uniform=1-result['brier']/mean([r['uniform_brier'] for r in rows]),
                  log_loss_improvement_vs_uniform=mean([r['uniform_log_loss']-r['log_loss'] for r in rows]))
    clusters=defaultdict(list)
    for r in rows:clusters[r['meeting_id']].append(r)
    result['meeting_clusters']=len(clusters)
    if len(clusters)<2:
        result['confidence_intervals_95']=None
    else:
        rng=random.Random(SEED);groups=list(clusters.values());samples=defaultdict(list)
        for _ in range(bootstrap):
            sample=[r for group in rng.choices(groups,k=len(groups)) for r in group]
            for k in keys:samples[k].append(mean([r[k] for r in sample]))
            samples['brier_skill_vs_uniform'].append(1-mean([r['brier'] for r in sample])/mean([r['uniform_brier'] for r in sample]))
        result['confidence_intervals_95']={k:interval(v) for k,v in samples.items()}
    return result


def score(bundle,prediction_path,split='test',bootstrap=1000):
    verify(bundle);root=Path(bundle)
    tasks={t['race_id']:t for t in read_jsonl(root/'diagnostic/tasks.jsonl')}
    labels={r['race_id']:r['target'] for r in read_jsonl(root/'supervisor/labels.jsonl')}
    cases={r['race_id']:r for r in read_jsonl(root/'supervisor/cases.jsonl')}
    eligible={rid:t for rid,t in tasks.items() if split=='all' or t['split']==split}
    if split not in ('all','development','validation','test'):raise ValueError('Unknown split')
    predictions=defaultdict(list);malformed=[];nonblank=0;parsed=0
    for n,line in enumerate(Path(prediction_path).read_text().splitlines(),1):
        if not line.strip():continue
        nonblank+=1
        try:
            value=json.loads(line)
            if not isinstance(value,dict) or not isinstance(value.get('race_id'),str):raise ValueError('missing race_id')
            if value['race_id'] not in tasks:raise ValueError('unknown race_id')
            predictions[value['race_id']].append(value);parsed+=1
        except (ValueError,TypeError) as error:malformed.append(dict(line=n,error=str(error)))
    rows=[];invalid=[]
    for rid,task in eligible.items():
        values=predictions.get(rid,[])
        reason='missing_prediction' if not values else 'duplicate_predictions' if len(values)>1 else validate_prediction(values[0].get('probabilities'),labels[rid])
        if reason:invalid.append(dict(race_id=rid,reason=reason));continue
        rows.append(dict(race_id=rid,meeting_id=cases[rid]['meeting_id'],date=task['date'],venue=task['venue'],
                         **metrics(values[0]['probabilities'],labels[rid])))
    report=dict(benchmark_version=VERSION,track='retrospective_diagnostic',split=split,expected_races=len(eligible),
                valid_predictions=len(rows),coverage=len(rows)/len(eligible) if eligible else 0,
                invalid_predictions=invalid,malformed_lines=malformed,input_nonblank_lines=nonblank,
                parsed_known_race_lines=parsed,parse_rate=parsed/nonblank if nonblank else 0,
                leaderboard_eligible=len(rows)==len(eligible) and bool(eligible) and not malformed,log_loss_floor=EPSILON,
                strict_historical_validity=False,overall=aggregate(rows,bootstrap),
                by_venue={v:aggregate([r for r in rows if r['venue']==v],bootstrap) for v in sorted({r['venue'] for r in rows})},
                by_month={m:aggregate([r for r in rows if r['date'][:7]==m],bootstrap) for m in sorted({r['date'][:7] for r in rows})})
    return report
