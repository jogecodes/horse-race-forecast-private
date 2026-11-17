"""A versioned declaration-based benchmark; publisher dating is explicit, never strict proof."""
import json,re,unicodedata,hashlib,sqlite3,shutil
from pathlib import Path
from collections import Counter
from .benchmark import verify,read_jsonl,write_jsonl,digest,score as legacy_score
from .db import uid,now
from .recovery import parse_declaration,publisher_timing

VERSION='spain-h1-2026-declarations-v2'
RECOVERIES=['data/recovery_h1_2026.json','data/recovery_gha_h1_2026.json','data/recovery_seed_h1_2026.json']


def identity(name):
    # Rendering-only normalization. Preserve country codes; refuse collisions within a field.
    s=unicodedata.normalize('NFKC',name.replace('´',"'").replace('’',"'").replace('‘',"'")).upper()
    s=''.join(c for c in unicodedata.normalize('NFKD',s) if not unicodedata.combining(c))
    return re.sub(r'\s+','',s)


def score(bundle,predictions,split='test',bootstrap=1000):
    manifest=verify(bundle);report=legacy_score(bundle,predictions,split,bootstrap)
    report.update(benchmark_version=manifest['version'],track=manifest.get('track','retrospective_diagnostic'))
    return report


def build(out='benchmarks/h1_2026_v2',legacy='benchmarks/h1_2026_v1'):
    prior=verify(legacy);out=Path(out);root=Path(legacy)
    if out.exists():raise FileExistsError(out)
    oldcases={r['race_id']:r for r in read_jsonl(root/'supervisor/cases.jsonl')}
    oldlabels={r['race_id']:r for r in read_jsonl(root/'supervisor/labels.jsonl')}
    oldtasks=read_jsonl(root/'diagnostic/tasks.jsonl');documents=[]
    for path in RECOVERIES:
        if Path(path).exists():
            for d in json.loads(Path(path).read_text())['records']:
                if d['kind']!='declaration':continue
                row=dict(d,recovery_file=path)
                try:row['races']=parse_declaration(d['document']['text'],d['date'])
                except ValueError as e:row['races']=[];row['parse_error']=str(e)
                documents.append(row)
    packets=[];cases=[];labels=[];exclusions=[];audit=[]
    for task in oldtasks:
        rid=task['race_id'];old=json.loads((root/f'diagnostic/packets/{rid}.json').read_text())
        keys={identity(r['horse_name']):r for r in old['runners']};candidates=[]
        if len(keys)!=len(old['runners']):raise ValueError('Ambiguous legacy identity')
        for d in documents:
            if (d['date'],d['venue'])!=(task['date'],task['venue']):continue
            for race in d['races']:
                names=[identity(r['horse_name']) for r in race['runners']]
                if race['issues'] or len(names)!=len(set(names)) or race['distance_m']!=old['distance_m']:continue
                if set(keys).issubset(names):candidates.append((d,race,names))
        if len(candidates)!=1:
            exclusions.append(dict(race_id=rid,date=task['date'],venue=task['venue'],reason='missing_or_ambiguous_complete_declaration',candidate_count=len(candidates)));continue
        d,race,names=candidates[0];timing=publisher_timing(d['document'],old['cutoff_utc'])
        if timing['tier']!='publisher_dates_consistent_before_cutoff':
            exclusions.append(dict(race_id=rid,date=task['date'],venue=task['venue'],reason='publisher_timing_not_consistent_before_cutoff',timing=timing));continue
        runners=[];target={};mapping={};extra=[]
        for r in race['runners']:
            k=identity(r['horse_name']);existing=keys.get(k)
            runner=existing['runner_id'] if existing else 'runner_'+uid(rid,k)
            row=dict(runner_id=runner,horse_name=r['horse_name'],jockey_name=r['jockey_name'],trainer_name=r['trainer_name'],stable_name=r['stable_name'],
                 cloth=r['cloth'],age=r['age'],declared_weight_kg=r['weight_kg'],draw=r['draw'],prior_form_raw=r['prior_form_raw'])
            runners.append(row);target[runner]=oldlabels[rid]['target'][runner] if existing else 0.0
            if existing:mapping[runner]=oldcases[rid]['runner_mapping'][runner]
            else:extra.append(dict(runner_id=runner,horse_name=r['horse_name']))
        if abs(sum(target.values())-1)>1e-9:raise ValueError('Target mapping lost winner mass')
        runners.sort(key=lambda r:r['runner_id'])
        packet=dict(benchmark_version=VERSION,race_id=rid,date=task['date'],venue=task['venue'],split=task['split'],cutoff_utc=old['cutoff_utc'],
          distance_m=race['distance_m'],track='publisher_documented',input_availability='official_pre_race_document_publisher_dated',runners=runners)
        packets.append(packet);labels.append(dict(race_id=rid,target=target))
        case=dict(oldcases[rid],declaration=dict(url=d['document']['receipt']['url'],sha256=d['document']['receipt']['sha256'],
          observed_at=d['document']['receipt']['observed_at'],recovery_file=d['recovery_file'],ordinal=race['ordinal'],timing=timing),
          extra_declared_runners_absent_from_v1=extra,runner_mapping=mapping)
        cases.append(case)
        audit.append(dict(race_id=rid,declared_runners=len(runners),recorded_starters=len(keys),additional_declared_runners=len(extra),
             source_pdf_sha256=case['declaration']['sha256'],timing_tier=timing['tier'],strict_eligible=False))
    if not packets:raise ValueError('No recoverable cases')
    (out/'diagnostic/packets').mkdir(parents=True);(out/'supervisor').mkdir()
    for p in packets:(out/f'diagnostic/packets/{p["race_id"]}.json').write_text(json.dumps(p,ensure_ascii=False,sort_keys=True)+'\n')
    write_jsonl(out/'diagnostic/tasks.jsonl',[{k:p[k] for k in ('benchmark_version','race_id','date','venue','split','cutoff_utc','track')} for p in packets])
    for name,rows in [('cases',cases),('labels',labels),('exclusions',exclusions),('declaration_audit',audit)]:write_jsonl(out/f'supervisor/{name}.jsonl',rows)
    protocol=dict(version=VERSION,track='publisher_documented',cutoff='23:59 Europe/Madrid on the day before the race',
      population='Subset of frozen v1 with a complete directly parsed official declaration and consistent publisher dates before cutoff',
      availability='Trust official PDF creation/modification and HTTP dates as publisher claims; independent historical byte availability is not established',
      strict_historical_validity=False,withdrawals='Forecast over every declared horse. Later nonstarters remain in field with target mass zero. No post-hoc forecast renormalization.',
      features='Only literal declaration fields; no reconstructed aggregate histories or result-page features',
      identity='NFKC, case, whitespace, accents and apostrophe rendering only; country retained; collisions rejected; no outcome-based aliases',
      market_comparator='Later information, never included in forecast input',legacy_selection_caveat='v1 exclusions and national-coverage limits remain; this is not an independently selected full national population')
    (out/'protocol.json').write_text(json.dumps(protocol,ensure_ascii=False,indent=2)+'\n')
    summary=dict(version=VERSION,created_at=now(),track='publisher_documented',races=len(packets),runners=sum(len(p['runners']) for p in packets),
       splits=dict(Counter(p['split'] for p in packets)),venues=dict(Counter(p['venue'] for p in packets)),
       additional_declared_runners=sum(len(c['extra_declared_runners_absent_from_v1']) for c in cases),excluded_from_v1=len(exclusions),strict_historical_validity=False,
       predecessor_manifest_sha256=digest(root/'manifest.json'),builder_sha256=digest(Path(__file__)),
       recovery_hashes={p:digest(p) for p in RECOVERIES if Path(p).exists()})
    (out/'source').mkdir()
    for source in [Path(__file__),Path(__file__).with_name('recovery.py'),Path(__file__).with_name('benchmark.py')]:shutil.copyfile(source,out/'source'/source.name)
    (out/'README.md').write_text(f'# Spain H1 2026 declaration benchmark v2\n\n{len(packets)} races; {sum(len(p["runners"]) for p in packets)} declared runners. See ../../docs/RECOVERED_BENCHMARK_H1_2026.md.\n\nPublisher-documented inputs: not independently certified historical byte availability. Labels and roster comparisons live only in supervisor/.\n')
    summary['files']={str(p.relative_to(out)):digest(p) for p in out.rglob('*') if p.is_file()}
    (out/'manifest.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    # All comparisons and labels stay in supervisor files; prediction packets have declarations only.
    return summary
