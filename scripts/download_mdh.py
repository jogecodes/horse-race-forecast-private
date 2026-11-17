"""Download only race URLs discovered in public archive links; resume from immutable files."""
import argparse
import hashlib
import json
import time
from pathlib import Path
import requests
from datetime import datetime,timezone


def main():
    p=argparse.ArgumentParser()
    p.add_argument('--cache',default='data/raw/mdh')
    p.add_argument('--interval',type=float,default=.5,help='Minimum seconds between request starts (one request at a time)')
    p.add_argument('--limit',type=int)
    args=p.parse_args()
    if args.interval<.5: p.error('Minimum supported interval is 0.5 seconds')
    root=Path(args.cache);root.mkdir(parents=True,exist_ok=True)
    ids=json.loads((root/'discovery.json').read_text())['race_ids']
    if args.limit: ids=ids[:args.limit]
    events=root/'download_events.jsonl'
    session=requests.Session()
    session.headers['User-Agent']='HorseRaceResearch/0.2 (private study; sequential cached collector)'
    last=0.; totals={'cached':0,'downloaded':0,'failed':0}
    for i,race in enumerate(ids,1):
        raw=root/f'result_{race}.html';meta=root/f'result_{race}.json'
        if raw.exists() and meta.exists():
            saved=json.loads(meta.read_text())
            if hashlib.sha256(raw.read_bytes()).hexdigest()!=saved['sha256']:
                raise ValueError(f'Cache hash mismatch: {raw}')
            totals['cached']+=1
        else:
            url=f'https://www.masdehipodromos.com/resultados2.cfm?jidPremio={race}'
            time.sleep(max(0,args.interval-(time.monotonic()-last)));last=time.monotonic()
            try:
                with session.get(url,timeout=30) as response:
                    response.raise_for_status()
                    body=response.content
                    metadata={'url':url,'observed_at':datetime.now(timezone.utc).isoformat(timespec='seconds'),
                              'sha256':hashlib.sha256(body).hexdigest(),'bytes':len(body),
                              'content_type':response.headers.get('Content-Type'), 'status':response.status_code}
                raw.write_bytes(body);meta.write_text(json.dumps(metadata,indent=2)+'\n')
                event=dict(race_id=race,**metadata);totals['downloaded']+=1
            except (requests.RequestException,TimeoutError,OSError) as error:
                event={'race_id':race,'url':url,'error':str(error)};totals['failed']+=1
                with events.open('a') as out: out.write(json.dumps(event)+'\n')
                print('DOWNLOAD ERROR',json.dumps(event),flush=True)
                if isinstance(error,requests.HTTPError) and error.response.status_code in (401,403,429):
                    print('Stopped on access/rate-limit response; rerun later through an authorized path.',flush=True)
                    break
                continue
            with events.open('a') as out: out.write(json.dumps(event)+'\n')
        if i%25==0: print(json.dumps({'processed':i,'total':len(ids),**totals}),flush=True)
    print('DOWNLOAD COMPLETE',json.dumps(totals),flush=True)


if __name__=='__main__': main()
