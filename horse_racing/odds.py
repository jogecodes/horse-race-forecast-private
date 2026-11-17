"""Betting-price provenance. Settlement figures never become pre-start quotes."""
import hashlib,json,math,re,sqlite3,time
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlparse
import requests
from .benchmark import read_jsonl,name_key,verify
from .db import uid,utc,now

PMU='https://online.turfinfo.api.pmu.fr/rest/client/1/programme/'


def odds_db(path):
    Path(path).parent.mkdir(parents=True,exist_ok=True)
    c=sqlite3.connect(path);c.row_factory=sqlite3.Row
    c.executescript('''CREATE TABLE IF NOT EXISTS observations(
      id TEXT PRIMARY KEY,race_id TEXT NOT NULL,runner_id TEXT NOT NULL,source TEXT NOT NULL,
      quote_kind TEXT NOT NULL,decimal_value REAL,raw_value TEXT NOT NULL,
      quote_at TEXT,scheduled_start_at TEXT,actual_start_at TEXT,observed_at TEXT NOT NULL,
      source_url TEXT NOT NULL,source_sha256 TEXT NOT NULL,market TEXT NOT NULL,
      timing_class TEXT NOT NULL,proof_basis TEXT NOT NULL,
      CHECK(decimal_value IS NULL OR decimal_value>=1));
      CREATE INDEX IF NOT EXISTS odds_race ON observations(race_id,runner_id);
      CREATE TRIGGER IF NOT EXISTS odds_no_update BEFORE UPDATE ON observations BEGIN SELECT RAISE(ABORT,'append-only');END;
      CREATE TRIGGER IF NOT EXISTS odds_no_delete BEFORE DELETE ON observations BEGIN SELECT RAISE(ABORT,'append-only');END;''')
    return c


def decimal(raw):
    raw=raw.strip().replace(',','.')
    if not re.fullmatch(r'\d+(?:\.\d+)?',raw):return None
    value=float(raw)
    return value if math.isfinite(value) and value>=1 else None


def millis(value):
    return datetime.fromtimestamp(value/1000,timezone.utc).isoformat(timespec='seconds') if value is not None else None


def classify(quote,scheduled,actual=None,preplay=False):
    if actual and quote and preplay and utc(quote)<utc(actual):return 'provider_timestamped_before_actual_start'
    if quote and scheduled:return 'before_scheduled_start_only' if utc(quote)<utc(scheduled) else 'at_or_after_scheduled_start'
    return 'time_unverified'


def add(c,**row):
    row['id']=uid(*[row[k] for k in sorted(row)])
    with c:c.execute(f'INSERT OR IGNORE INTO observations({",".join(row)}) VALUES({",".join("?" for _ in row)})',tuple(row.values()))


def horse_key(value):
    return re.sub(r'\s*\([A-Z]{2,3}\)$','',name_key(value)).strip()


class CachedPmu:
    def __init__(self,root):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True);self.last=0
        self.session=requests.Session();self.session.headers['User-Agent']='HorseRaceResearch/0.3 (cached historical prices; sequential requests)'
    def get(self,url):
        key=hashlib.sha256(url.encode()).hexdigest();path=self.root/(key+'.json');meta=self.root/(key+'.meta.json')
        if path.exists() and meta.exists():
            b=path.read_bytes();m=json.loads(meta.read_text())
            if hashlib.sha256(b).hexdigest()!=m['sha256']:raise ValueError('PMU cache hash mismatch')
            return json.loads(b),m
        time.sleep(max(0,.5-(time.monotonic()-self.last)));self.last=time.monotonic()
        r=self.session.get(url,timeout=25);r.raise_for_status();b=r.content
        m=dict(url=url,observed_at=now(),sha256=hashlib.sha256(b).hexdigest())
        path.write_bytes(b);meta.write_text(json.dumps(m,indent=2)+'\n')
        return r.json(),m


def collect(bundle,db_path,odds_path,cache_dir,report_path):
    verify(bundle);root=Path(bundle);c=odds_db(odds_path)
    source=sqlite3.connect('file:'+str(Path(db_path).resolve())+'?mode=ro',uri=True);source.row_factory=sqlite3.Row
    tasks={t['race_id']:t for t in read_jsonl(root/'diagnostic/tasks.jsonl')}
    cases=read_jsonl(root/'supervisor/cases.jsonl');case_map={x['race_id']:x for x in cases}
    report=dict(expected_races=len(tasks),provider_meetings=[],errors=[],unmatched_participants=[])
    for case in cases:
        for runner,hid in case['runner_mapping'].items():
            row=source.execute('''SELECT d.dividend_raw,s.url,s.sha256,s.observed_at FROM latest_results x
             JOIN result_details d ON d.result_id=x.id JOIN race_versions v ON v.id=x.race_version_id
             JOIN snapshots s ON s.id=v.snapshot_id WHERE x.race_id=? AND x.horse_id=?''',(case['source_race_id'],hid)).fetchone()
            if row and row['dividend_raw'].strip():
                add(c,race_id=case['race_id'],runner_id=runner,source='masdehipodromos',quote_kind='post_result_DG',
                    decimal_value=decimal(row['dividend_raw']),raw_value=row['dividend_raw'],quote_at=None,scheduled_start_at=None,actual_start_at=None,
                    observed_at=row['observed_at'],source_url=row['url'],source_sha256=row['sha256'],market='reported_DG_semantics_not_independently_verified',
                    timing_class='post_result_not_preoff',proof_basis='Result-table field; no quote timestamp; never use as pre-race odds')
    source.close();api=CachedPmu(cache_dir)
    for day in sorted({t['date'] for t in tasks.values()}):
        stamp=datetime.strptime(day,'%Y-%m-%d').strftime('%d%m%Y');url=PMU+stamp
        try:programme,meta=api.get(url)
        except (requests.RequestException,ValueError) as e:
            report['errors'].append(dict(date=day,stage='programme',error=str(e)));continue
        for meeting in programme.get('programme',{}).get('reunions',[]):
            if meeting.get('pays',{}).get('code')!='ESP':continue
            label=meeting.get('hippodrome',{}).get('libelleCourt','').upper()
            venue='San Sebastián' if 'SEBASTIAN' in label else 'La Zarzuela' if ('MADRID' in label or 'ZARZUELA' in label) else 'Dos Hermanas' if 'HERMANAS' in label else None
            if venue is None:continue
            report['provider_meetings'].append(dict(date=day,venue=venue,provider_reunion=meeting['numOfficiel']))
            for course in meeting.get('courses',[]):
                matching=[case for case in cases if tasks[case['race_id']]['date']==day and tasks[case['race_id']]['venue']==venue]
                # Cross-check distance and exact normalized horse set before accepting a provider match.
                if not matching:continue
                course_no=course['numOrdre'];course_url=f'{url}/R{meeting["numOfficiel"]}/C{course_no}/participants'
                try:data,receipt=api.get(course_url)
                except (requests.RequestException,ValueError) as e:
                    report['errors'].append(dict(date=day,url=course_url,error=str(e)));continue
                participants=data.get('participants',[])
                provider_names={horse_key(p['nom']) for p in participants if p.get('statut')=='PARTANT'}
                matched=None;packet=None
                for case in matching:
                    trial=json.loads((root/f'diagnostic/packets/{case["race_id"]}.json').read_text())
                    names=[horse_key(r['horse_name']) for r in trial['runners']]
                    if len(names)==len(set(names)) and set(names)==provider_names and trial['distance_m']==course.get('distance'):
                        if matched is not None:raise ValueError('Ambiguous PMU race mapping')
                        matched=case;packet=trial
                if not matched:
                    report['unmatched_participants'].append(dict(url=course_url,date=day,venue=venue));continue
                runner_map={horse_key(r['horse_name']):r['runner_id'] for r in packet['runners']}
                scheduled=millis(course.get('heureDepart'))
                for p in participants:
                    runner=runner_map.get(horse_key(p['nom']))
                    if not runner:continue
                    for key in ['dernierRapportDirect','dernierRapportReference']:
                        q=p.get(key)
                        if not q or q.get('typePari')!='SIMPLE_GAGNANT':continue
                        value=decimal(str(q.get('rapport','')))
                        if value is None:continue
                        quoted=millis(q.get('dateRapport'))
                        add(c,race_id=matched['race_id'],runner_id=runner,source='pmu',quote_kind=key,
                            decimal_value=value,raw_value=json.dumps(q,ensure_ascii=False),quote_at=quoted,
                            scheduled_start_at=scheduled,actual_start_at=None,observed_at=receipt['observed_at'],
                            source_url=course_url,source_sha256=receipt['sha256'],market='PMU_SIMPLE_GAGNANT_probable_return',
                            timing_class=classify(quoted,scheduled),proof_basis='PMU-reported quote timestamp and scheduled start; actual off unverified')
    report['observations_by_kind']={r[0]:r[1] for r in c.execute('SELECT quote_kind,count(*) FROM observations GROUP BY quote_kind')}
    report['observations_by_timing']={r[0]:r[1] for r in c.execute('SELECT timing_class,count(*) FROM observations GROUP BY timing_class')}
    report['races_with_pmu_quotes']=c.execute("SELECT count(DISTINCT race_id) FROM observations WHERE source='pmu'").fetchone()[0]
    report['races_with_post_result_DG']=c.execute("SELECT count(DISTINCT race_id) FROM observations WHERE source='masdehipodromos'").fetchone()[0]
    report['verified_last_60_seconds_before_actual_start']=c.execute("SELECT count(*) FROM observations WHERE timing_class='provider_timestamped_before_actual_start' AND (julianday(actual_start_at)-julianday(quote_at))*86400 BETWEEN 0 AND 60").fetchone()[0]
    report['forecast_cutoff_note']='Benchmark forecasts close on the previous day. Even genuine same-day pre-off prices are a later-information comparator, not admissible features for that cutoff.'
    report['exact_preoff_status']='Unavailable unless actual-start evidence and timestamped preplay ticks are supplied. PMU scheduled-time comparisons and post-result DG are not exact closing odds.'
    report['integrity']=c.execute('PRAGMA integrity_check').fetchone()[0];c.close()
    Path(report_path).parent.mkdir(parents=True,exist_ok=True);Path(report_path).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    return report
