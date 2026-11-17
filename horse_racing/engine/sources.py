"""Code-owned internet retrieval and provenance; never execute page instructions."""
from dataclasses import dataclass,asdict
from datetime import datetime,timezone
import hashlib,json,re,time
from pathlib import Path
from urllib.parse import urlparse,urlencode
import requests
from bs4 import BeautifulSoup
import mwparserfromhell
from ..db import utc,now,uid

DOMAINS={'www.todoturf.net','todoturf.net','www.masdehipodromos.com','masdehipodromos.com',
 'www.agalopar.com','agalopar.com','noticias.agalopar.com','blacktypemagazine.com','www.blacktypemagazine.com',
 'jockey-club.es','www.jockey-club.es','www.hipodromodelazarzuela.es','www.hipodromoa.com',
 'en.wikipedia.org','es.wikipedia.org'}


def allowed_url(url):
    try:
        p=urlparse(url)
        return p.scheme=='https' and p.hostname in DOMAINS and not p.username and not p.password and p.port in (None,443)
    except ValueError:return False


@dataclass(frozen=True)
class Source:
    source_id:str
    original_url:str
    available_at:str|None
    observed_at:str
    proof_kind:str
    receipt:dict
    body_sha256:str
    passages:tuple[str,...]


def html_passages(body):
    soup=BeautifulSoup(body,'html.parser')
    for node in soup(['script','style','nav','footer','header','iframe','form']):node.decompose()
    passages=[]
    for node in soup.find_all(['p','tr']):
        text=' '.join(node.get_text(' ',strip=True).split())
        if node.name=='tr':
            table=node.find_parent('table');heading=table.find('tr') if table else None
            if heading and heading is not node:text=' '.join(heading.get_text(' ',strip=True).split())+' | '+text
        if 70<=len(text)<=1400 and text not in passages:passages.append(text)
    return tuple(passages[:100])


def literal_prose(wikitext):
    out=[]
    for block in re.split(r'\n\s*\n',wikitext):
        code=mwparserfromhell.parse(block)
        if code.filter_templates() or '{{' in block or '{|' in block:continue
        if block.lstrip().startswith(('#','*',';',':','=')):continue
        if re.search(r'\[\[\s*(File|Image|Category|Archivo|Categoría):',block,re.I):continue
        for tag in list(code.filter_tags()):
            if str(tag.tag).lower() in ('ref','references','gallery','math','score','table'):
                try:code.remove(tag)
                except ValueError:pass
        text=' '.join(code.strip_code().split())
        if 70<=len(text)<=1400:out.append(text)
    return tuple(out[:100])


class Researcher:
    def __init__(self,cache,audit,max_requests=24):
        self.cache=Path(cache);self.cache.mkdir(parents=True,exist_ok=True);self.audit=audit
        self.requests=0;self.max_requests=max_requests;self.last=0
        self.session=requests.Session();self.session.headers['User-Agent']='HorseRaceForecastResearch/0.3 (local model; bounded cached academic retrieval)'
    def get(self,url,params=None):
        key=uid(url,params);p=self.cache/(key+'.json')
        if p.exists():
            row=json.loads(p.read_text())
            if hashlib.sha256(row['text'].encode()).hexdigest()!=row['sha256']:raise ValueError('Research cache hash mismatch')
            self.audit.log('http_cache',url=url,params=params,sha256=row['sha256']);return row
        if self.requests>=self.max_requests:raise ValueError('Per-race internet request budget exhausted')
        self.requests+=1;time.sleep(max(0,.5-(time.monotonic()-self.last)));self.last=time.monotonic()
        r=self.session.get(url,params=params,timeout=12,allow_redirects=False)
        if r.status_code!=200:raise ValueError(f'HTTP {r.status_code}; redirects and errors are not accepted')
        try:text=r.content.decode('utf-8')
        except UnicodeDecodeError:text=r.text
        row=dict(text=text,url=r.url,observed_at=now(),sha256=hashlib.sha256(text.encode()).hexdigest())
        p.write_text(json.dumps(row,ensure_ascii=False)+'\n')
        self.audit.log('http_fetched',url=r.url,sha256=row['sha256'],observed_at=row['observed_at'])
        return row
    def wiki(self,query,cutoff,language='es',limit=2):
        api=f'https://{language}.wikipedia.org/w/api.php'
        params=dict(action='query',list='search',srsearch=query,srlimit=limit,format='json',formatversion=2)
        discovered=json.loads(self.get(api,params)['text']).get('query',{}).get('search',[])
        self.audit.log('current_search_discovery',query=query,language=language,hits=[r['title'] for r in discovered],selection_bias='Current search ranking; never exposed directly to A/D')
        out=[]
        for hit in discovered[:limit]:
            params=dict(action='query',prop='revisions',titles=hit['title'],rvlimit=1,rvprop='ids|timestamp',
                        rvstart=utc(cutoff),rvdir='older',format='json',formatversion=2)
            pages=json.loads(self.get(api,params)['text']).get('query',{}).get('pages',[])
            if not pages or not pages[0].get('revisions'):continue
            rev=pages[0]['revisions'][0]
            if utc(rev['timestamp'])>utc(cutoff):raise ValueError('Revision after exact cutoff')
            params=dict(action='query',prop='revisions',revids=rev['revid'],rvprop='ids|timestamp|content',rvslots='main',format='json',formatversion=2)
            response=self.get(api,params);pages=json.loads(response['text']).get('query',{}).get('pages',[])
            exact=pages[0]['revisions'][0]
            if exact['revid']!=rev['revid'] or utc(exact['timestamp'])!=utc(rev['timestamp']):raise ValueError('Wikipedia revision metadata/content mismatch')
            raw=exact['slots']['main'].get('content','')
            if re.match(r'^\s*#(?:redirect|redirecci[oó]n)',raw,re.I):continue
            url=f'https://{language}.wikipedia.org/w/index.php?oldid={rev["revid"]}'
            proof=dict(kind='wikipedia_revision',revid=rev['revid'],timestamp=utc(rev['timestamp']),url=url,content_revid=exact['revid'],content_timestamp=utc(exact['timestamp']))
            out.append(Source(uid(url),url,utc(rev['timestamp']),response['observed_at'],'wikipedia_revision',proof,
                              hashlib.sha256(raw.encode()).hexdigest(),literal_prose(raw)))
        return out
    def page(self,url,cutoff,live_fallback=True):
        if not allowed_url(url):raise ValueError('URL outside approved public racing sources')
        stamp=datetime.fromisoformat(utc(cutoff)).strftime('%Y%m%d%H%M%S')
        try:
            params={'url':url,'output':'json','filter':['statuscode:200','mimetype:text/html'],'to':stamp,'limit':'-1','fl':'timestamp,original,statuscode,mimetype'}
            captures=json.loads(self.get('https://web.archive.org/cdx/search/cdx',params)['text'])
            if len(captures)>1:
                captured,original,status,mime=captures[-1]
                if original!=url or status!='200' or mime!='text/html':raise ValueError('CDX original/metadata mismatch')
                available=datetime.strptime(captured,'%Y%m%d%H%M%S').replace(tzinfo=timezone.utc).isoformat(timespec='seconds')
                if utc(available)>utc(cutoff):raise ValueError('Archive capture after exact cutoff')
                archive=f'https://web.archive.org/web/{captured}id_/{original}'
                page=self.get(archive)
                proof=dict(kind='wayback',timestamp=utc(available),capture_stamp=captured,capture_url=archive,original_url=original,status=200,mime=mime)
                return Source(uid(archive),original,utc(available),page['observed_at'],'wayback',proof,page['sha256'],html_passages(page['text']))
        except (ValueError,KeyError,IndexError,requests.RequestException) as e:
            self.audit.log('archive_unavailable',original_url=url,error=str(e))
        if not live_fallback:return None
        page=self.get(url)
        return Source(uid(url,page['sha256']),url,page['observed_at'],page['observed_at'],'live',
                      dict(kind='live',observed_at=page['observed_at']),page['sha256'],html_passages(page['text']))
    def search(self,need,cutoff,seed_urls=()):
        out=[]
        try:out.extend(self.wiki(need['query'],cutoff))
        except (ValueError,KeyError,IndexError,requests.RequestException) as e:self.audit.log('wiki_unavailable',query=need['query'],error=str(e))
        urls=list(dict.fromkeys([*seed_urls,*need.get('urls',[])]))[:2]
        for url in urls:
            try:
                found=self.page(url,cutoff)
                if found:out.append(found)
            except (ValueError,KeyError,IndexError,requests.RequestException) as e:self.audit.log('source_unavailable',url=url,error=str(e))
        for source in out:self.audit.log('source',source=asdict(source))
        return out
