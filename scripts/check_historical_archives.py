"""Check exact recovered document URLs against pre-cutoff Wayback captures."""
import json,sys,hashlib
from pathlib import Path
from datetime import datetime,timezone,timedelta
from urllib.parse import urlencode
from zoneinfo import ZoneInfo
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from horse_racing.recovery import RecoveryCache,pdf_artifact,RateLimited
cache=RecoveryCache();documents=[]
for path in ['data/recovery_h1_2026.json','data/recovery_gha_h1_2026.json','data/recovery_seed_h1_2026.json']:
 if Path(path).exists():documents+=json.loads(Path(path).read_text())['records']
checks=[];rate_limited=False
for d in documents:
 local=datetime.fromisoformat(d['date']).replace(tzinfo=ZoneInfo('Europe/Madrid'))-timedelta(minutes=1)
 cutoff=local.astimezone(timezone.utc);url=d['document']['receipt']['url']
 params=[('url',url),('output','json'),('to',cutoff.strftime('%Y%m%d%H%M%S')),('filter','statuscode:200'),('filter','mimetype:application/pdf'),('limit','-1'),('fl','timestamp,original,statuscode,mimetype,digest')]
 query='https://web.archive.org/cdx/search/cdx?'+urlencode(params)
 check=dict(url=url,date=d['date'],kind=d['kind'],cutoff_utc=cutoff.isoformat(),status='unchecked')
 try:
  if rate_limited and not (cache.root/(hashlib.sha256(query.encode()).hexdigest()+'.json')).exists():raise RateLimited('Remaining archive checks deferred after provider rate limit')
  body,meta=cache.get(query);rows=json.loads(body);check['index_receipt']=meta
  if len(rows)>1:
   stamp,original,status,mime,digest=rows[-1]
   captured=datetime.strptime(stamp,'%Y%m%d%H%M%S').replace(tzinfo=timezone.utc)
   if captured>cutoff or status!='200' or mime!='application/pdf':raise ValueError('Invalid capture metadata')
   capture=f'https://web.archive.org/web/{stamp}id_/{original}'
   b,receipt=cache.get(capture);doc=pdf_artifact(b,receipt)
   check.update(status='verified_capture',available_at=captured.isoformat(),capture_url=capture,archive_receipt=receipt,
          content_matches_current=receipt['sha256']==d['document']['receipt']['sha256'],archived_document=doc)
  else:check['status']='no_pre_cutoff_capture'
 except RateLimited as e:
  rate_limited=True;check.update(status='deferred_rate_limit',error=str(e))
 except Exception as e:check.update(status='lookup_failed',error=str(e))
 checks.append(check);print(d['date'],d['kind'],check['status'],flush=True)
 Path('data/h1_archive_checks.json').write_text(json.dumps(dict(checks=checks),ensure_ascii=False,indent=2)+'\n')
