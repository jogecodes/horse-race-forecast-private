"""Cache the public Spain H1-2026 index, meeting pages and linked race results."""
import hashlib,json,time
from datetime import datetime,timezone
from pathlib import Path
from urllib.parse import urlparse,parse_qs,urljoin
import requests
from bs4 import BeautifulSoup

ROOT=Path('data/raw/todoturf_h1_2026')
ROOT.mkdir(parents=True,exist_ok=True)
SESSION=requests.Session()
SESSION.headers['User-Agent']='HorseRaceBenchmark/0.1 (private study; cached sequential requests)'
LAST=0.


def fetch(url,key,data=None):
    global LAST
    path=ROOT/(key+'.html');meta=ROOT/(key+'.json')
    if path.exists() and meta.exists():
        b=path.read_bytes();m=json.loads(meta.read_text())
        if hashlib.sha256(b).hexdigest()!=m['sha256']:raise ValueError('Cache hash mismatch')
        return b,m
    time.sleep(max(0,.5-(time.monotonic()-LAST)));LAST=time.monotonic()
    r=SESSION.post(url,data=data,timeout=40) if data else SESSION.get(url,timeout=40)
    r.raise_for_status();b=r.content
    m=dict(url=url,method='POST' if data else 'GET',parameters=data,observed_at=datetime.now(timezone.utc).isoformat(timespec='seconds'),sha256=hashlib.sha256(b).hexdigest())
    path.write_bytes(b);meta.write_text(json.dumps(m,indent=2)+'\n')
    return b,m


body,_=fetch('https://www.todoturf.net/resultados.php','index',{'ano':'2026','hipodromo':'ESPANA','Submit':'Buscar'})
s=BeautifulSoup(body,'html.parser');meetings=[];races=[]
for tr in s.select('table tbody tr'):
    c=tr.find_all('td',recursive=False);a=tr.find('a',href=True)
    if not a:continue
    q=parse_qs(urlparse(a['href']).query);d=q['fecha'][0][:10]
    if '2026-01-01'<=d<='2026-06-30':
        meetings.append(dict(date=d,venue=q['hipodromo'][0],expected_races=int(c[2].get_text(strip=True)),url=urljoin('https://www.todoturf.net/',a['href'])))
for i,meeting in enumerate(meetings,1):
    key='meeting_'+hashlib.sha256(meeting['url'].encode()).hexdigest()[:16]
    body,_=fetch(meeting['url'],key);s=BeautifulSoup(body,'html.parser');found=[]
    for tr in s.select('table tbody tr'):
        c=tr.find_all('td',recursive=False)
        a=tr.find('a',href=lambda h:h and h.startswith('resultados3.php'))
        if not a:continue
        found.append(dict(date=meeting['date'],venue=meeting['venue'],ordinal=int(c[0].get_text(strip=True)),
                          title=c[1].get_text(' ',strip=True),distance_raw=c[2].get_text(' ',strip=True),url=urljoin(meeting['url'],a['href'])))
    if len(found)!=meeting['expected_races']:raise ValueError(f'Incomplete meeting: {meeting}')
    races.extend(found)
    print('Meeting',i,'/',len(meetings),flush=True)
for i,race in enumerate(races,1):
    key='race_'+hashlib.sha256(race['url'].encode()).hexdigest()[:16]
    _,meta=fetch(race['url'],key)
    race.update(file=key+'.html',metadata=key+'.json',sha256=meta['sha256'],observed_at=meta['observed_at'])
    if i%20==0:print('Race',i,'/',len(races),flush=True)
(ROOT/'manifest.json').write_text(json.dumps(dict(meetings=meetings,races=races),ensure_ascii=False,indent=2)+'\n')
print('COMPLETE',len(meetings),'meetings',len(races),'races',flush=True)
