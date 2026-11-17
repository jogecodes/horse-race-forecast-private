"""Code-owned article/post extraction and explicit publisher date claims."""
import json,re,ipaddress,socket,unicodedata
from datetime import datetime,time,timezone,timedelta
from urllib.parse import urlparse,parse_qs,urljoin
from zoneinfo import ZoneInfo
from bs4 import BeautifulSoup
from ..db import utc,uid
from .sources import Source,html_passages

SOCIAL={'x.com','www.x.com','twitter.com','www.twitter.com','bsky.app','t.me','www.t.me','www.facebook.com','facebook.com','www.instagram.com','instagram.com'}


def public_url(url,resolve=False):
    try:
        p=urlparse(url);host=(p.hostname or '').lower()
        if p.scheme!='https' or p.username or p.password or p.port not in (None,443) or len(url)>2500:return False
        if not host or '.' not in host or host.endswith(('.localhost','.local','.internal','.test','.invalid')):return False
        try:ipaddress.ip_address(host);return False
        except ValueError:pass
        if resolve:
            addresses=socket.getaddrinfo(host,443,type=socket.SOCK_STREAM)
            if not addresses or any(not ipaddress.ip_address(a[4][0]).is_global for a in addresses):return False
        return True
    except (ValueError,OSError):return False


def date_claim(value,path,kind='published'):
    value=str(value).strip()
    if re.fullmatch(r'\d{2}/\d{2}/\d{4}',value):value=datetime.strptime(value,'%d/%m/%Y').date().isoformat()
    if re.fullmatch(r'20\d{2}-\d{2}-\d{2}',value):
        # Latest possible time on that local date, rather than inventing an early publication time.
        d=datetime.fromisoformat(value).replace(tzinfo=ZoneInfo('Europe/Madrid'))+timedelta(days=1)-timedelta(microseconds=1)
        return dict(kind=kind,path=path,value=d.astimezone(timezone.utc).isoformat(),precision='day_upper_bound')
    try:d=datetime.fromisoformat(value.replace('Z','+00:00'))
    except ValueError:return None
    if d.tzinfo is None:return None
    return dict(kind=kind,path=path,value=d.astimezone(timezone.utc).isoformat(),precision='timestamp')


def json_nodes(value):
    if isinstance(value,dict):
        yield value
        # Only graph entries, not arbitrary recommended/related embedded articles.
        for node in value.get('@graph',[]):yield from json_nodes(node)
    elif isinstance(value,list):
        for node in value:yield from json_nodes(node)


def article_content(body,url):
    soup=BeautifulSoup(body,'html.parser');claims=[];author=None;canonical=url
    for meta in soup.find_all('meta'):
        key=(meta.get('property') or meta.get('name') or '').lower()
        kind='published' if key in ('article:published_time','datepublished','date','pubdate','parsely-pub-date','dc.date.issued') else 'modified' if key in ('article:modified_time','datemodified','lastmod') else None
        if kind:
            c=date_claim(meta.get('content',''),'meta:'+key,kind)
            if c:claims.append(c)
    for script in soup.find_all('script',type='application/ld+json'):
        try:nodes=json_nodes(json.loads(script.string or script.get_text()))
        except (ValueError,TypeError):continue
        for node in nodes:
            types=node.get('@type',[]);types=[types] if isinstance(types,str) else types
            if not any(t in ('Article','NewsArticle','BlogPosting','SocialMediaPosting','ReportageNewsArticle') for t in types):continue
            own=node.get('url') or node.get('mainEntityOfPage')
            if isinstance(own,dict):own=own.get('@id') or own.get('url')
            if isinstance(own,str) and urlparse(own)._replace(fragment='',query='').geturl().rstrip('/')!=urlparse(url)._replace(fragment='',query='').geturl().rstrip('/'):continue
            for key,kind in [('datePublished','published'),('dateModified','modified')]:
                c=date_claim(node.get(key,''),'jsonld:'+key,kind)
                if c:claims.append(c)
            a=node.get('author')
            if isinstance(a,dict):author=a.get('name')
    main=soup.select_one('article.node--view-mode-full') or soup.select_one('article') or soup.select_one('main') or soup
    # Related articles can be nested inside the primary article by malformed publisher HTML.
    # Their dates and text belong to separate publications.
    for related in main.select('article.node--view-mode-teaser, aside, nav, footer'):
        related.decompose()
    for t in main.select('time[datetime], [property="schema:dateCreated"][content], [property="datePublished"][content]'):
        c=date_claim(t.get('datetime') or t.get('content'),'article:time')
        if c:claims.append(c)
    # A few supported publishers expose their publication date outside the body field.
    for t in main.select('.date-display-single, .field--name-field-fecha, .field-name-field-fecha, .field--name-field-date-published, .news-date'):
        raw=t.get('content') or t.get('datetime') or t.get_text(' ',strip=True)
        for value in dict.fromkeys([raw,*re.findall(r'\b\d{2}/\d{2}/\d{4}\b',raw)]):
            c=date_claim(value,'visible_publisher_date')
            if c:claims.append(c)
    p=urlparse(url)
    if p.hostname in ('todoturf.net','www.todoturf.net') and p.path.endswith('/noticia.php'):
        value=parse_qs(p.query).get('fecha',[''])[0]
        try:value=datetime.strptime(value,'%Y-%m-%d %H:%M:%S').replace(tzinfo=ZoneInfo('Europe/Madrid')).isoformat()
        except ValueError:value=''
        c=date_claim(value,'todoturf_news_url')
        if c:claims.append(c)
    passages=()
    for selector in ('.field--name-field-description','[itemprop="articleBody"]','.entry-content','.field--name-body','.field-name-body'):
        content=main.select_one(selector)
        if content is not None:
            passages=html_passages(str(content))
            if passages:break
    if not passages:passages=html_passages(str(main))
    # Full publication header stays attached to every passage; never forward a bare search snippet.
    title=soup.select_one('h1');heading=title.get_text(' ',strip=True) if title else ''
    return passages,claims,dict(author=author,title=heading)


def publisher_source(url,response,passages,claims,allow_undated=False,**extra):
    published=[c for c in claims if c and c['kind']=='published']
    if not published:
        if not allow_undated:raise ValueError('No supported explicit publication date; article/post remains unavailable')
        receipt=dict(kind='unverified_dating',original_url=url,observed_at=response['observed_at'],
            date_claims=[c for c in claims if c],claimed_available_at=None,
            edit_history='Publication time and historical availability unknown; content requires exploratory semantic review',**extra)
        return Source(uid(url,response['sha256']),url,None,response['observed_at'],'unverified_dating',receipt,response['sha256'],tuple(passages))
    claims=[c for c in claims if c]
    available=max((datetime.fromisoformat(c['value']) for c in claims)).isoformat()
    receipt=dict(kind='publisher_dated',original_url=url,observed_at=response['observed_at'],date_claims=claims,
          claimed_available_at=available,edit_history='Not independently verified; later edits without date changes may be present',**extra)
    return Source(uid(url,response['sha256']),url,available,response['observed_at'],'publisher_dated',receipt,response['sha256'],tuple(passages))


def x_post_id(url):
    p=urlparse(url)
    if p.hostname not in ('x.com','www.x.com','twitter.com','www.twitter.com'):return None
    m=re.fullmatch(r'/[^/]+/status/(\d+)(?:/.*)?',p.path)
    return m[1] if m else None


def x_oembed(url,response):
    value=json.loads(response['text']);pid=x_post_id(url)
    if not pid or x_post_id(value.get('url',''))!=pid:raise ValueError('Post response identity mismatch')
    soup=BeautifulSoup(value['html'],'html.parser');block=soup.select_one('blockquote.twitter-tweet')
    if block is None:raise ValueError('No complete public post text')
    p=block.find('p')
    if p is None or not p.get_text(' ',strip=True):raise ValueError('Empty public post')
    # Snowflake creation time is a publisher identifier claim, not immutable text/version proof.
    created=datetime.fromtimestamp(((int(pid)>>22)+1288834974657)/1000,timezone.utc).isoformat()
    claim=date_claim(created,'x_status_id')
    return publisher_source(url,response,[p.get_text(' ',strip=True)],[claim],source_type='social_post',platform='X',
             author=value.get('author_name'),author_url=value.get('author_url'),post_id=pid,transport_url=response.get('url','https://publish.x.com/oembed'))


def telegram_post(url,response):
    soup=BeautifulSoup(response['text'],'html.parser');p=urlparse(url);post=p.path.strip('/')
    node=soup.select_one('[data-post]')
    if node is None or node.get('data-post')!=post:raise ValueError('Telegram post identity mismatch')
    text=node.select_one('.tgme_widget_message_text');stamp=node.select_one('time[datetime]')
    if text is None or stamp is None:raise ValueError('No public post body and timestamp')
    return publisher_source(url,response,[text.get_text(' ',strip=True)],[date_claim(stamp['datetime'],'telegram:datetime')],
                            source_type='social_post',platform='Telegram',post_id=post)
