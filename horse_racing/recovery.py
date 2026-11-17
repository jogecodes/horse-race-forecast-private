"""Recover historical pre-race artifacts without treating publisher dates as archive proof."""
import hashlib,io,json,re,time,unicodedata
from datetime import datetime,timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.parse import urljoin,urlparse
import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader
from .db import now,utc


class RateLimited(ValueError):
    pass


class RecoveryCache:
    def __init__(self,root='data/raw/h1_recovery'):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True);self.last=0
        self.session=requests.Session();self.session.headers['User-Agent']='SpanishRacingResearch/0.4 (private study; cached sequential historical documents)'
    def get(self,url):
        key=hashlib.sha256(url.encode()).hexdigest();path=self.root/(key+'.bin');meta=self.root/(key+'.json')
        if path.exists() and meta.exists():
            b=path.read_bytes();m=json.loads(meta.read_text())
            if hashlib.sha256(b).hexdigest()!=m['sha256']:raise ValueError('Recovery cache hash mismatch')
            if m['status']==429:raise RateLimited('Cached rate-limit response; respect provider cooldown')
            if m['status']!=200:raise ValueError(f'Cached HTTP {m["status"]}: {url}')
            return b,m
        time.sleep(max(0,.5-(time.monotonic()-self.last)));self.last=time.monotonic()
        r=self.session.get(url,timeout=20)
        m=dict(url=url,final_url=r.url,status=r.status_code,observed_at=now(),sha256=hashlib.sha256(r.content).hexdigest(),
               headers=dict(r.headers),file=path.name)
        path.write_bytes(r.content);meta.write_text(json.dumps(m,ensure_ascii=False,indent=2)+'\n')
        if r.status_code==429:raise RateLimited('Provider returned HTTP 429; stop this collection pass')
        if r.status_code!=200:raise ValueError(f'HTTP {r.status_code}: {url}')
        return r.content,m


def pdf_artifact(body,receipt):
    if not body.startswith(b'%PDF'):raise ValueError('Expected actual PDF bytes')
    pdf=PdfReader(io.BytesIO(body));metadata={str(k):str(v) for k,v in (pdf.metadata or {}).items()}
    dates={}
    for key,attr in [('pdf_created_at','creation_date'),('pdf_modified_at','modification_date')]:
        try:
            d=getattr(pdf.metadata,attr,None)
            # A PDF clock with no timezone is ambiguous, not a UTC timestamp.
            if d is not None and d.tzinfo is not None:dates[key]=utc(d.isoformat())
        except (ValueError,TypeError):pass
    last=next((v for k,v in receipt['headers'].items() if k.lower()=='last-modified'),None)
    if last:
        try:dates['http_last_modified_at']=utc(parsedate_to_datetime(last).isoformat())
        except (ValueError,TypeError):pass
    return dict(receipt=receipt,pdf_metadata=metadata,date_claims=dates,
                text='\n'.join(page.extract_text(extraction_mode='layout') for page in pdf.pages),pages=len(pdf.pages))


def publisher_timing(document,cutoff):
    dates=document.get('date_claims',{})
    if len(dates)>=2 and all(utc(v)<=utc(cutoff) for v in dates.values()):
        return dict(tier='publisher_dates_consistent_before_cutoff',strict_eligible=False,claimed_available_at=max(dates.values()),date_claims=dates,
                    caveat='Publisher-controlled dates, retrieved retrospectively; not independent archive proof')
    return dict(tier='publication_time_unverified',strict_eligible=False,date_claims=dates)


def clean_name(name):
    name=re.sub(r'\s*\((?:\d+(?:[.,]\d+)?|a)\)','',name,flags=re.I)
    return ' '.join(name.split()).strip()


def parse_declaration(text,expected_date):
    """Read table columns from the declaration itself, never discover horse names from labels."""
    dates=re.findall(r'(?:Programa del d[ií]a|Participantes definitivos)\s+(\d{2}/\d{2}/\d{4})',text,re.I)
    if not dates:
        months={'ENERO':1,'FEBRERO':2,'MARZO':3,'ABRIL':4,'MAYO':5,'JUNIO':6}
        named=re.search(r'PARTICIPANTES DEFINITIVOS PARA LAS CARRERAS DEL\s+[^,]+,\s*(\d+) DE (\w+) DE (20\d{2})',text,re.I)
        if named and named[2].upper() in months:dates=[f'{int(named[1]):02}/{months[named[2].upper()]:02}/{named[3]}']
    if not dates or any(datetime.strptime(d,'%d/%m/%Y').date().isoformat()!=expected_date for d in dates):
        raise ValueError('Declaration date absent or inconsistent')
    races=[];race=None;bounds=None;issues=[]
    for line in text.splitlines():
        header=re.search(r'^\s*(\d+)\s*[ªºa]?\s+CARRERA\s*-?\s*((?:Gran\s+)?Premi(?:o)?\b.*)',line,re.I)
        if header:
            race=dict(ordinal=int(header[1]),title=header[2].strip(),distance_m=None,runners=[],issues=[])
            when=re.search(r'Hora:\s*(\d{1,2}:\d{2})',line)
            race['scheduled_time_local']=when[1] if when else None
            races.append(race);bounds=None
            distance=re.search(r'([\d.,]+)\s*(?:mts?\.|metros)',line,re.I)
            if distance:race['distance_m']=int(re.sub(r'\D','',distance[1]))
            continue
        if race is None:continue
        distance=re.search(r'(?:Distancia:\s*)?([\d.,]+)\s*(?:mts?\.|metros)',line,re.I)
        if distance and race['distance_m'] is None:race['distance_m']=int(re.sub(r'\D','',distance[1]))
        when=re.search(r'Hora:\s*(\d{1,2}:\d{2})',line)
        if when:race['scheduled_time_local']=when[1]
        if all(w in line for w in ('CABALLO','EDAD','JINETE')) and ('ENTRENADOR' in line or 'PREPARADOR' in line):
            labels=['CABALLO','EDAD','KG','JINETE','CUADRA','ENTRENADOR' if 'ENTRENADOR' in line else 'PREPARADOR','CAJ']
            centers=[(line.index(w)+(len(w)/2)) for w in labels]
            # Column headings are centered while names are left aligned. Use header gaps to split
            # horse/age/weight; the connection columns are split by whitespace runs below.
            bounds=centers;continue
        if not bounds:continue
        if re.match(r'^\s*\d+\s+\S',line):
            m=re.match(r'^\s*(\d+)\s+(.+?)\s+(\d+)(?:\s+a[ñn]os)?\s+([\d,\.]+)\s+(.*)$',line)
            if not m:race['issues'].append(dict(code='unparsed_entry',line=line.strip()));continue
            form=re.search(r'\[[^\]]*\]\s*$',m[5])
            tail=re.split(r'\s{2,}',m[5][:form.start()].strip())+[form[0].strip()] if form else re.split(r'\s{2,}',m[5].strip())
            if len(tail)>5 and all(p.startswith('(') for p in tail[1:-4]):tail=[' '.join(tail[:-4]),*tail[-4:]]
            if len(tail)!=5 or not re.fullmatch(r'\d+',tail[3]) or not re.fullmatch(r'(?:\[[^\]]*\]|[\w,./-]+|Debutante)',tail[4],re.I):
                race['issues'].append(dict(code='unparsed_connections',line=line.strip()));continue
            race['runners'].append(dict(cloth=int(m[1]),horse_name=clean_name(m[2]),age=int(m[3]),
                weight_kg=float(m[4].replace(',','.')),jockey_name=tail[0],stable_name=tail[1],trainer_name=tail[2],
                draw=int(tail[3]),prior_form_raw=tail[4]))
    if not races:raise ValueError('No declaration races parsed')
    for r in races:
        if len({x['cloth'] for x in r['runners']})!=len(r['runners']):r['issues'].append(dict(code='duplicate_cloth'))
        if r['distance_m'] is None:r['issues'].append(dict(code='missing_distance'))
        if not r['runners']:r['issues'].append(dict(code='empty_field'))
    return races


def collect_official(bundle='benchmarks/h1_2026_v1',out='data/recovery_h1_2026.json',cache_root='data/raw/h1_recovery'):
    from .benchmark import verify,read_jsonl
    verify(bundle);tasks=read_jsonl(Path(bundle)/'diagnostic/tasks.jsonl');cache=RecoveryCache(cache_root)
    meetings=sorted({(t['date'],t['venue']) for t in tasks});records=[];errors=[]
    for day,venue in meetings:
        url='https://www.hipodromodelazarzuela.es/carreras/jornada/'+day.replace('-','')
        try:
            body,meta=cache.get(url);soup=BeautifulSoup(body,'html.parser')
            for a in soup.find_all('a',href=True):
                label=a.get_text(' ',strip=True).lower()
                if label not in ('partant definitivo','programa de mano'):continue
                target=urljoin(url,a['href'])
                try:
                    pdf,receipt=cache.get(target);doc=pdf_artifact(pdf,receipt)
                    key=receipt['sha256'];(cache.root/(key+'.txt')).write_text(doc['text'])
                    record=dict(date=day,venue=venue,kind='declaration' if label=='partant definitivo' else 'race_programme',
                                discovery_receipt=meta,document=doc)
                    if record['kind']=='declaration':
                        try:record['races']=parse_declaration(doc['text'],day)
                        except ValueError as e:record['parse_error']=str(e)
                    records.append(record)
                except Exception as e:errors.append(dict(url=target,date=day,error=str(e)))
        except Exception as e:errors.append(dict(url=url,date=day,error=str(e)))
        print(json.dumps(dict(date=day,venue=venue,documents_so_far=len(records),errors_so_far=len(errors))),flush=True)
        Path(out).write_text(json.dumps(dict(records=records,errors=errors,cache_root=str(cache.root)),ensure_ascii=False,indent=2)+'\n')
    return dict(records=records,errors=errors,cache_root=str(cache.root))
