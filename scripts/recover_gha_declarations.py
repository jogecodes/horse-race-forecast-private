import json,re,sys
from pathlib import Path
from bs4 import BeautifulSoup
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from horse_racing.recovery import RecoveryCache,pdf_artifact,parse_declaration
cache=RecoveryCache()
u='https://www.granhipodromodeandalucia.es/?rest_route=/tribe/events/v1/events&start_date=2026-01-01&end_date=2026-06-30&per_page=50'
body,meta=cache.get(u);events=json.loads(body)['events'];records=[];errors=[]
for event in events:
 day=event['start_date'][:10]
 for a in BeautifulSoup(event['description'],'html.parser').find_all('a',href=True):
  label=a.get_text(' ',strip=True)
  if 'PARTICIPANTES DEFINITIVOS' not in label or 'LOTOTURF' in label:continue
  original=a['href'];m=re.search(r'/d/([^/]+)',original)
  if not m:errors.append(dict(url=original,error='Unrecognized public document URL'));continue
  url='https://drive.google.com/uc?export=download&id='+m[1]
  try:
   data,receipt=cache.get(url);doc=pdf_artifact(data,receipt)
   record=dict(date=day,venue='Dos Hermanas',kind='declaration',discovery_receipt=meta,discovery_url=event['url'],original_url=original,
        publisher_event_created_at=event.get('date_utc'),publisher_event_modified_at=event.get('modified_utc'),document=doc)
   try:record['races']=parse_declaration(doc['text'],day)
   except ValueError as e:record['parse_error']=str(e)
   records.append(record);print(day,'races',len(record.get('races',[])),flush=True)
  except Exception as e:errors.append(dict(url=url,error=str(e)))
 Path('data/recovery_gha_h1_2026.json').write_text(json.dumps(dict(records=records,errors=errors,cache_root=str(cache.root)),ensure_ascii=False,indent=2)+'\n')
