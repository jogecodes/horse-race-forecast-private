"""Match official FinishLynx start clocks to PMU markets; retain retrospective timing proof."""
import json,re,sqlite3,sys
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urljoin
from zoneinfo import ZoneInfo
from bs4 import BeautifulSoup
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from horse_racing.recovery import RecoveryCache,pdf_artifact,clean_name
from horse_racing.odds import horse_key
from horse_racing.start_times import parse_finish_start,quote_timing
from horse_racing.benchmark import read_jsonl

cache=RecoveryCache();root=Path('benchmarks/h1_2026_v1')
packets=[json.loads(p.read_text()) for p in (root/'diagnostic/packets').glob('*.json')]
c=sqlite3.connect('data/odds_h1_2026.sqlite');c.row_factory=sqlite3.Row
urls={r[0] for r in c.execute("SELECT DISTINCT source_url FROM observations WHERE source='pmu'")}
markets=[]
for u in sorted(urls):
 body,meta=cache.get(u);d=json.loads(body)
 names={horse_key(x['nom']) for x in d['participants'] if x.get('statut')=='PARTANT'}
 markets.append(dict(url=u,names=names,date=datetime.strptime(re.search(r'/programme/(\d{8})/',u)[1],'%d%m%Y').date().isoformat()))
base='https://www.hipodromoa.com'
index=base+'/temporadas_anteriores/_IqQzNPbID9hmdCrEM50YFelRT0DKLYB1'
body,meta=cache.get(index);s=BeautifulSoup(body,'html.parser')
course_urls=list(dict.fromkeys(urljoin(base,a['href']) for a in s.find_all('a',href=True) if '/temporada/reunion/' in a['href']))
starts=[];errors=[];unmatched=[]
for u in course_urls:
 try:
  body,receipt=cache.get(u);s=BeautifulSoup(body,'html.parser')
  photo=next(a['href'] for a in s.find_all('a',href=True) if a.get_text(' ',strip=True)=='Foto finish')
  body,pmeta=cache.get(urljoin(base,photo));pdf=pdf_artifact(body,pmeta)
  actual=parse_finish_start(pdf['text']);local=datetime.fromisoformat(actual).astimezone(ZoneInfo('Europe/Madrid'));day=local.date().isoformat()
  # Full horse identities come from the official arrival table, not truncated photo captions.
  names=set()
  for table in s.find_all('table'):
   if not all(w in table.get_text(' ',strip=True) for w in ['Caballo','Jockey','Entrenador']):continue
   for row in table.find_all('tr'):
    cells=row.find_all('td')
    if len(cells)>=5:
     value=cells[0].get_text(' ',strip=True)
     if not re.match(r'^\d+\s',value):continue
     name=re.sub(r'\s*\(\d+\)','',re.sub(r'^\d+\s+','',value))
     if name:names.add(horse_key(clean_name(name)))
  matched=[market for market in markets if market['date']==day and market['names']==names]
  record=dict(date=day,actual_start_at=actual,local_start=local.isoformat(),precision_seconds=.01,
              proof_kind='official_photo_finish_explicit_start_clock',source_url=pmeta['url'],source_sha256=pmeta['sha256'],
              source_observed_at=pmeta['observed_at'],course_url=u,course_receipt=receipt,photo_metadata=pdf['pdf_metadata'],
              extracted_text=pdf['text'],arrival_names=sorted(names),pmu_url=matched[0]['url'] if len(matched)==1 else None)
  if len(matched)!=1:unmatched.append(record)
  else:starts.append(record)
  print(day,actual,'matched',len(matched),flush=True)
 except Exception as e:errors.append(dict(url=u,error=str(e)));print('ERROR',u,str(e),flush=True)
 Path('data/actual_starts_h1_2026.json').write_text(json.dumps(dict(starts=starts,unmatched=unmatched,errors=errors),ensure_ascii=False,indent=2)+'\n')
comparisons=[]
for start in starts:
 for q in c.execute("SELECT * FROM observations WHERE source_url=? AND source='pmu'",(start['pmu_url'],)):
  delta,classification=quote_timing(q['quote_at'],start['actual_start_at'])
  comparisons.append(dict(observation_id=q['id'],race_id=q['race_id'],runner_id=q['runner_id'],quote_kind=q['quote_kind'],
       decimal_value=q['decimal_value'],quote_at=q['quote_at'],actual_start_at=start['actual_start_at'],seconds_before_actual_start=delta,
       timing_class=classification,
       start_proof_url=start['source_url'],start_proof_sha256=start['source_sha256']))
c.close()
report=dict(actual_starts=len(starts),unmatched=len(unmatched),errors=errors,
 quote_timing_counts={k:sum(q['timing_class']==k for q in comparisons) for k in sorted({q['timing_class'] for q in comparisons})},
 races_with_last_60s_quotes=len({q['race_id'] for q in comparisons if q['timing_class']=='last_60_seconds_before_actual_start'}),
 cross_system_clock_synchronization='Not independently measured; hundredth-second photo precision does not establish clock accuracy or publication latency',
 note='Provider quote timestamps compared against explicit official FinishLynx actual-start clocks. Does not prove the quote was the final available price or its historical dissemination time.',comparisons=comparisons)
Path('data/odds_actual_start_comparison.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:v for k,v in report.items() if k!='comparisons'},indent=2))
