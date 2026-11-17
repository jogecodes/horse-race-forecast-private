"""Validated Masdehipodromos public historical result import; post-race data only."""
from __future__ import annotations
import hashlib
import json
import re
import unicodedata
from datetime import date, datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from bs4 import BeautifulSoup, UnicodeDammit
from .db import entity, insert, snapshot, uid
from .ingest import register_sources


class ExcludedPage(ValueError):
    """A real linked page outside the requested date/discipline/venue scope."""


def clean(text):
    return ' '.join(text.split())


def canonical_venue(raw):
    text = unicodedata.normalize('NFKD',raw).encode('ascii','ignore').decode().lower()
    for fragment,name,slug in [
        ('zarzuela','La Zarzuela','zarzuela'),('san sebastian','San Sebastián','san-sebastian'),('lasarte','San Sebastián','san-sebastian'),
        ('dos hermanas','Dos Hermanas','dos-hermanas'),('pineda','Pineda','pineda'),
        ('sanlucar','Sanlúcar de Barrameda','sanlucar'),('zahara','Zahara de los Atunes','zahara'),('vila-seca','Vila-seca','vila-seca'),
        ('vilaseca','Vila-seca','vila-seca'),('loredo','Loredo','loredo'),('laredo','Laredo','laredo'),
        ('antela','Antela','antela'),('mijas','Mijas','mijas')]:
        if fragment in text:
            return name,slug
    raise ExcludedPage(f'Unsupported/non-Spanish venue: {raw}')


def source_id(cell, parameter):
    for a in cell.find_all('a',href=True):
        q = parse_qs(urlparse(a['href']).query.lower())
        value = q.get(parameter.lower(),[None])[0]
        if value and value.isdigit() and int(value)>0:
            return value
    return None


def optional_float(value):
    value = value.strip().replace(',','.')
    if not value or value in ('-','--'):
        return None
    if not re.fullmatch(r'\d+(?:\.\d+)?',value):
        raise ValueError(f'Unrecognized weight: {value!r}')
    number = float(value)
    if not 20<=number<=100:
        raise ValueError(f'Implausible weight: {number}')
    return number


def weights(value):
    parts = value.split('-')
    if len(parts)>2:
        raise ValueError(f'Unrecognized weight pair: {value!r}')
    assigned = optional_float(parts[0])
    carried = optional_float(parts[1]) if len(parts)==2 else None
    return assigned,carried


def parse_result(body, start_date='2022-01-01', end_date='2026-11-05'):
    soup = BeautifulSoup(body,'html.parser')
    headings = [clean(t.get_text(' ',strip=True)) for t in soup.select('font.naranjaPremio')]
    if len(headings)<2:
        raise ValueError('Missing result heading/date')
    date_match = re.match(r'^(.*?)\s+(?:(\d{1,2}:\d{2})\s+)?(\d{2}-\d{2}-\d{4})\b',headings[1])
    if not date_match:
        raise ValueError(f'Unknown meeting heading: {headings[1]}')
    race_date = datetime.strptime(date_match[3],'%d-%m-%Y').date().isoformat()
    if not start_date<=race_date<=end_date:
        raise ExcludedPage(f'Date {race_date} outside {start_date}..{end_date}')
    venue,slug = canonical_venue(date_match[1])
    race_match = re.match(r'^RESULTADO\s+(\d+)ª\s+CARRERA\s*-\s*(\d+)',headings[0],re.I)
    if not race_match:
        raise ValueError(f'Missing result race number: {headings[0]}')
    title = soup.select_one('font.textoPremio')
    if title is None:
        raise ValueError('Missing race title')
    text = clean(soup.get_text(' ',strip=True))
    dist = re.search(r'Distancia:\s*([\d.]+)',text)
    if not dist:
        raise ValueError('Missing race distance')
    distance = int(dist[1].replace('.',''))
    if not 500<=distance<=10000:
        raise ValueError(f'Implausible distance: {distance}')
    header_tr = None
    for tr in soup.find_all('tr'):
        cells = tr.find_all('td',recursive=False)
        if len(cells)==10 and clean(cells[0].get_text())=='Pto.':
            header_tr = tr
            break
    if header_tr is None:
        raise ValueError('Missing result table')
    table = header_tr.find_parent('table')
    rows = []
    for tr in table.find_all('tr'):
        if tr is header_tr or tr.find_parent('table') is not table:
            continue
        cells = tr.find_all('td',recursive=False)
        strings = [clean(c.get_text(' ',strip=True)) for c in cells]
        if not any(strings):
            continue
        if len(cells)!=10:
            # Dividends/footer have a colspan, not runner data.
            if len(cells)==1 and cells[0].get('colspan'):
                continue
            raise ValueError(f'Result row has {len(cells)} columns instead of 10')
        horse_external = source_id(cells[1],'caballoID')
        if not horse_external:
            raise ValueError('Runner is missing a stable horse ID')
        status = strings[0]
        match = re.fullmatch(r'(\d+)(?:\s*\([^)]*\))?',status)
        # 9x are provider status codes, not literal finishing places; never guess their meaning.
        pos = int(match[1]) if match and 0<int(match[1])<90 else None
        if not status:
            raise ValueError('Missing runner status')
        draw = int(strings[6]) if strings[6].isdigit() and int(strings[6])>0 else None
        field_warning = None
        try:
            assigned,carried = weights(strings[2])
        except ValueError as error:
            # Source typos must not become fabricated numeric features or discard a valid result.
            field_warning = str(error)
            try:
                assigned = optional_float(strings[2].split('-')[0])
            except ValueError:
                assigned = None
            carried = None
        anchor = cells[1].find('a')
        raw_name = anchor.get_text(' ',strip=True)
        # IDs, not stripped display names, determine horse identity.
        name = clean(re.sub(r'\(\d+\)','',raw_name.split('\xa0')[0]))
        row = dict(field_warning=field_warning,horse_external=horse_external,horse_name=name,horse_raw=strings[1],
                   status_raw=status,position=pos,draw=draw,weight_raw=strings[2],
                   assigned_weight_kg=assigned,carried_weight_kg=carried,
                   dividend_raw=strings[9],time_or_margin_raw=strings[8],
                   source_line=tr.sourceline or 1,row_raw=' | '.join(strings),
                   jockey=(source_id(cells[3],'idJinete'),strings[3]),
                   trainer=(source_id(cells[4],'idPreparador'),strings[4]),
                   stable=(source_id(cells[5],'idPropietario'),strings[5]))
        rows.append(row)
    if not rows or not any(r['position']==1 for r in rows):
        raise ValueError('No completed result/winner')
    if len({r['horse_external'] for r in rows})!=len(rows):
        raise ValueError('Duplicate horse in result table')
    for row in rows:
        if row['position'] and row['position']>len(rows):
            # E.g. a disqualified runner can carry 9 in an eight-runner source table.
            # Preserve the status without claiming a literal finishing position.
            row['position'] = None
    def between(left,right):
        m = re.search(re.escape(left)+r'\s*(.*?)\s*'+re.escape(right),text)
        return m[1] if m else None
    conditions = between('Condición:','Pto.')
    dividend_match = re.search(r'Dividendos:\s*(.*?)(?:Quienes Somos|$)',text)
    return dict(race_date=race_date,venue=venue,venue_slug=slug,venue_raw=date_match[1],
                race_number=int(race_match[1]),external_number=race_match[2],
                title=clean(title.get_text(' ',strip=True)),distance_m=distance,
                header_raw=' | '.join(headings),conditions_raw=conditions,
                category_raw=between('Categoría:','Pista:'),surface_raw=between('Pista:','Terreno:'),
                going_raw=between('Terreno:','Dotación:'),prize_raw=between('Dotación:','Condición:'),
                start_time_raw=date_match[2],dividends_raw=dividend_match[1] if dividend_match else None,
                rows=rows)


def provider_entity(conn,kind,external_id,name):
    if not name or name in ('-','--'):
        return None
    if not external_id:
        ident = uid('masdehipodromos',kind,'name',name)
        insert(conn,'entities',id=ident,kind=kind,name=name,identity_scope='masdehipodromos:exact-name:provisional')
        return ident
    ident = uid('masdehipodromos',kind,external_id)
    insert(conn,'entities',id=ident,kind=kind,name=name,identity_scope=f'masdehipodromos:id:{external_id}')
    insert(conn,'entity_identifiers',source_id='masdehipodromos',kind=kind,external_id=external_id,entity_id=ident)
    return ident


def import_result(conn,body,url,observed_at,start_date='2022-01-01',end_date='2026-11-05'):
    p = parse_result(body,start_date,end_date)
    q = parse_qs(urlparse(url).query.lower())
    external_id = q.get('jidpremio',[None])[0]
    if not external_id or not external_id.isdigit():
        raise ValueError('Result URL missing jidPremio')
    # Known same-date/same-venue races reuse the canonical race identity across providers.
    existing = conn.execute('SELECT id FROM meetings WHERE race_date=? AND venue=?',(p['race_date'],p['venue'])).fetchall()
    if len(existing)>1:
        raise ValueError('Ambiguous canonical meeting; explicit reconciliation needed')
    mid = existing[0]['id'] if existing else f'mdh:{p["race_date"]}:{p["venue_slug"]}'
    mapped = conn.execute('SELECT race_id FROM race_identifiers WHERE source_id=? AND external_id=?',
                          ('masdehipodromos',external_id)).fetchone()
    candidates = conn.execute("""SELECT DISTINCT v.race_id FROM race_versions v JOIN races r ON r.id=v.race_id
      JOIN snapshots s ON s.id=v.snapshot_id
      WHERE s.source_id='jce' AND r.meeting_id=? AND v.external_number=?
        AND r.race_number=? AND v.distance_m=?""",
        (mid,p['external_number'],p['race_number'],p['distance_m'])).fetchall()
    if mapped:
        rid = mapped['race_id']
    elif len(candidates)==1:
        # Match official versions on venue/date, annual number, ordinal and distance.
        # Same-provider page IDs always remain distinct: annual numbers also contain typos.
        rid = candidates[0]['race_id']
    elif len(candidates)>1:
        raise ValueError('Ambiguous annual race number; explicit reconciliation needed')
    else:
        rid = f'{mid}:mdh:{external_id}'
    decoded = UnicodeDammit(body).unicode_markup if isinstance(body,bytes) else body
    with conn:
        register_sources(conn)
        sid = snapshot(conn,'masdehipodromos',url,decoded,observed_at,'direct-http-public-html','text/html')
        prior_version = conn.execute('SELECT id FROM race_versions WHERE race_id=? AND snapshot_id=? AND phase=?',
                                     (rid,sid,'result')).fetchone()
        if prior_version:
            return dict(race_id=rid,snapshot_id=sid,runner_count=len(p['rows']),race_date=p['race_date'],venue=p['venue'])
        insert(conn,'meetings',id=mid,source_id='masdehipodromos',external_id=p['venue_slug'],race_date=p['race_date'],venue=p['venue'])
        insert(conn,'races',id=rid,meeting_id=mid,race_number=p['race_number'])
        insert(conn,'race_identifiers',source_id='masdehipodromos',external_id=external_id,race_id=rid)
        ordinal_conflicts = conn.execute('SELECT id FROM races WHERE meeting_id=? AND race_number=? AND id<>?',
                                         (mid,p['race_number'],rid)).fetchall()
        if ordinal_conflicts:
            detail = json.dumps(dict(displayed_race_number=p['race_number'],external_number=p['external_number'],
                                     other_races=[r['id'] for r in ordinal_conflicts]))
            insert(conn,'quality_issues',id=uid(sid,rid,'ordinal-conflict'),snapshot_id=sid,race_id=rid,
                   code='conflicting_source_race_ordinal',detail=detail)
        annual_conflicts = conn.execute("""SELECT DISTINCT v.race_id FROM race_versions v
          JOIN races r ON r.id=v.race_id JOIN snapshots s ON s.id=v.snapshot_id
          WHERE r.meeting_id=? AND v.external_number=? AND v.race_id<>?
            AND s.source_id='masdehipodromos'""",(mid,p['external_number'],rid)).fetchall()
        if annual_conflicts:
            detail = json.dumps(dict(external_number=p['external_number'],
                                     other_races=[r['race_id'] for r in annual_conflicts]))
            insert(conn,'quality_issues',id=uid(sid,rid,'annual-conflict'),snapshot_id=sid,race_id=rid,
                   code='conflicting_source_annual_number',detail=detail)
        vid = uid(rid,sid,'result')
        insert(conn,'race_versions',id=vid,race_id=rid,snapshot_id=sid,phase='result',
               external_number=p['external_number'],title=p['title'],distance_m=p['distance_m'],
               header_raw=p['header_raw'],conditions_raw=p['conditions_raw'])
        details = {k:p[k] for k in ['category_raw','surface_raw','going_raw','start_time_raw','prize_raw','dividends_raw']}
        insert(conn,'race_details',race_version_id=vid,**details)
        for r in p['rows']:
            hid = provider_entity(conn,'horse',r['horse_external'],r['horse_name'])
            result_id = uid(vid,hid)
            insert(conn,'results',id=result_id,race_version_id=vid,cloth=None,horse_id=hid,position=r['position'],
                   status_raw=r['status_raw'],margin_raw=r['time_or_margin_raw'] if r['position'] and r['position']>1 else None,
                   jockey_id=provider_entity(conn,'jockey',*r['jockey']),trainer_id=provider_entity(conn,'trainer',*r['trainer']),
                   stable_id=provider_entity(conn,'stable',*r['stable']),weight_kg=r['carried_weight_kg'],draw=r['draw'],
                   horse_raw=r['horse_raw'],source_line=r['source_line'],row_raw=r['row_raw'])
            insert(conn,'result_details',result_id=result_id,**{k:r[k] for k in ['weight_raw','assigned_weight_kg','carried_weight_kg','dividend_raw','time_or_margin_raw']})
            snippet = f'{p["race_date"]} | {p["venue"]} | race {p["race_number"]} | result\n{p["title"]}\n{r["row_raw"]}'
            insert(conn,'evidence',id=uid(sid,result_id,'evidence'),snapshot_id=sid,text=snippet,entity_id=hid,
                   related_race_id=rid,kind='result',locator=f'HTML:L{r["source_line"]}')
            if r['field_warning']:
                detail = json.dumps(dict(horse_external=r['horse_external'],weight_raw=r['weight_raw'],reason=r['field_warning']))
                insert(conn,'quality_issues',id=uid(sid,result_id,'weight-parse'),snapshot_id=sid,race_id=rid,
                       code='invalid_source_weight',detail=detail)
            if r['position'] is None:
                detail = json.dumps(dict(horse_external=r['horse_external'],status_raw=r['status_raw']))
                insert(conn,'quality_issues',id=uid(sid,result_id,'unclassified-status'),snapshot_id=sid,race_id=rid,
                       code='provider_status_not_finishing_place',detail=detail)
    return dict(race_id=rid,snapshot_id=sid,runner_count=len(p['rows']),race_date=p['race_date'],venue=p['venue'])


def import_cache(conn,cache_dir,start_date='2022-01-01',end_date='2026-11-05'):
    root = Path(cache_dir)
    report = dict(imported=0,excluded=[],errors=[],runners=0)
    discovered = json.loads((root/'discovery.json').read_text())['race_ids']
    report['discovered_links'] = len(discovered)
    report['not_downloaded'] = []
    for external in discovered:
        raw = root/f'result_{external}.html'; meta = root/f'result_{external}.json'
        if not raw.exists() or not meta.exists():
            report['not_downloaded'].append(external)
            continue
        try:
            metadata = json.loads(meta.read_text())
            body = raw.read_bytes()
            if hashlib.sha256(body).hexdigest()!=metadata['sha256']:
                raise ValueError('Raw cache SHA-256 mismatch')
            item = import_result(conn,body,metadata['url'],metadata['observed_at'],start_date,end_date)
            report['imported']+=1
            report['runners']+=item['runner_count']
        except ExcludedPage as e:
            report['excluded'].append(dict(external_id=external,reason=str(e)))
        except (ValueError,TypeError) as e:
            report['errors'].append(dict(external_id=external,reason=str(e)))
        if (report['imported']+len(report['errors'])+len(report['excluded']))%100==0:
            print(json.dumps({k:v if not isinstance(v,list) else len(v) for k,v in report.items()}),flush=True)
    return report
