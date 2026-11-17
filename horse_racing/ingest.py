"""Import JCE rendered text. Reject incomplete/ambiguous tables rather than guessing."""
from __future__ import annotations
import json
import re
from pathlib import Path
from datetime import date
from .db import entity, insert, snapshot, uid

SOURCES = [
 ('jce','Jockey Club Español','https://jockey-club.es/','Public meeting cards and results. Direct HTTP returned 403 in this environment; seed uses web.run rendered text.','Publicly readable does not imply an open redistribution licence. Keep raw extracts private.'),
 ('masdehipodromos','Masdehipódromos','https://www.masdehipodromos.com/','Public seasonal result indexes and historical HTML results; implemented cached, sequential importer with stable provider entity IDs.','Public HTML collected for this private study. No open redistribution licence established; retain raw material privately.'),
 ('gaceta','Gaceta Hipódromo','https://www.gacetahipodromo.com/mapa-web','Advertises results since 2005 plus horse/jockey/trainer records; registration required.','No account access or bulk licence supplied; no collection enabled.')
]
HEADER = re.compile(r'^#{0,6}\s*(\d+)ª Carrera \((nº\s*)?(\d+)\): (.+) - ([\d.]+) m\.(.*)$')


def register_sources(conn):
    for sid,name,url,access,rights in SOURCES:
        insert(conn,'sources',id=sid,name=name,url=url,access_notes=access,rights_notes=rights)


def horse_name(raw):
    s = re.sub(r'\(\d+\)', '', raw.replace('~~',''))
    s = re.sub(r'\s+(?:GAZ|GRO|GOV|GAM|GBL)$', '', s.strip())
    return ' '.join(s.split())


def number(s, integer=False):
    s = s.replace('~~','').strip()
    if s in ('','-','--'):
        return None
    return int(s) if integer else float(s.replace(',','.'))


def parse(text):
    lines = []
    for index,line in enumerate(text.splitlines(),1):
        m = re.match(r'^L(\d+):\s?(.*)$',line)
        lines.append((int(m[1]),m[2]) if m else (index,line))
    races = []
    current = None
    in_table = False
    for lineno,line in lines:
        match = HEADER.match(line.strip())
        if match:
            current = dict(number=int(match[1]),phase='result' if match[2] else 'declaration',
                           external_number=match[3],title=match[4],distance_m=int(match[5].replace('.','')),
                           header_raw=line,conditions_raw=None,rows=[])
            races.append(current)
            in_table = False
            continue
        if current is None:
            continue
        cells = [x.strip() for x in line.split('|')]
        expected = 'Pos' if current['phase']=='result' else 'Nº'
        if cells[0] == expected and len(cells)>2:
            in_table = True
            continue
        if in_table and len(cells)>2:
            expected_len = 10 if current['phase']=='result' else 7
            if len(cells)!=expected_len:
                raise ValueError(f'Malformed table at line {lineno}: {len(cells)} columns, expected {expected_len}')
            # A table cannot silently eat unrelated website content.
            if not re.match(r'^(?:\d+|RET|NP|DIST|DESC|CAI|PAR)', cells[0].replace('~~','')):
                raise ValueError(f'Unknown runner status at line {lineno}: {cells[0]}')
            current['rows'].append((lineno,line,cells))
        else:
            in_table = False
            if line.startswith('Condiciones de carrera:') or (not current['rows'] and line.strip()):
                current['conditions_raw'] = line
    if not races:
        raise ValueError('No JCE declaration/result tables found')
    seen = set()
    for r in races:
        key = (r['number'],r['phase'])
        if key in seen:
            raise ValueError(f'Duplicate race/phase {key}')
        seen.add(key)
        if not r['rows']:
            raise ValueError(f'Empty runner table {key}')
        cloths = [number(c[2] if r['phase']=='result' else c[0],True) for _,_,c in r['rows']]
        if len(set(cloths))!=len(cloths) or any(n is None or n<1 for n in cloths):
            raise ValueError(f'Duplicate/missing cloth number {key}')
        if r['phase']=='result' and not any(re.match(r'^1(?:\s|$)',c[0]) for _,_,c in r['rows']):
            raise ValueError(f'Result has no winner: {key}')
    for r in races:
        if r['phase']=='result':
            card = next((c for c in races if c['number']==r['number'] and c['phase']=='declaration'),None)
            if card:
                card_cloths = {number(c[0],True) for _,_,c in card['rows']}
                result_cloths = {number(c[2],True) for _,_,c in r['rows']}
                if card_cloths!=result_cloths:
                    raise ValueError(f'Incomplete/mismatched card and result for race {r["number"]}')
    return races


def import_jce(conn, text, race_date, venue_id, venue, observed_at, method='web.run-rendered-extract'):
    date.fromisoformat(race_date)
    parsed = parse(text)  # Validate all rows before touching the database.
    url = f'https://jockey-club.es/datos-de-jornada/?date={race_date.replace("-", "")}&id={venue_id}'
    mid = f'jce:{race_date}:{venue_id}'
    with conn:
        register_sources(conn)
        sid = snapshot(conn,'jce',url,text,observed_at,method)
        insert(conn,'meetings',id=mid,source_id='jce',external_id=str(venue_id),race_date=race_date,venue=venue)
        for r in parsed:
            rid = f'{mid}:r{r["number"]}'
            vid = uid(rid,sid,r['phase'])
            insert(conn,'races',id=rid,meeting_id=mid,race_number=r['number'])
            insert(conn,'race_versions',id=vid,race_id=rid,snapshot_id=sid,phase=r['phase'],
                   external_number=r['external_number'],title=r['title'],distance_m=r['distance_m'],
                   header_raw=r['header_raw'],conditions_raw=r['conditions_raw'])
            for lineno,raw,c in r['rows']:
                if r['phase']=='declaration':
                    cloth,horse,weight,jockey,stable,trainer,draw = c
                    cloth = number(cloth,True)
                    values = dict(cloth=cloth,horse_id=entity(conn,'horse',horse_name(horse)),
                                  jockey_id=entity(conn,'jockey',jockey.replace('~~','')),
                                  trainer_id=entity(conn,'trainer',trainer.replace('~~','')),
                                  stable_id=entity(conn,'stable',stable.replace('~~','')),
                                  weight_kg=number(weight),draw=number(draw,True),horse_raw=horse,
                                  source_line=lineno,row_raw=raw,race_version_id=vid)
                    insert(conn,'entries',id=uid(vid,cloth),withdrawn=int('~~' in c[0]),**values)
                else:
                    status,horse,cloth,margin,jockey,weight,draw,trainer,stable,breeder = c
                    cloth = number(cloth,True)
                    pos = re.match(r'^(\d+)',status)
                    insert(conn,'results',id=uid(vid,cloth),race_version_id=vid,cloth=cloth,
                           horse_id=entity(conn,'horse',horse_name(horse)),position=int(pos[1]) if pos else None,
                           status_raw=status,margin_raw=margin,jockey_id=entity(conn,'jockey',jockey),
                           trainer_id=entity(conn,'trainer',trainer),stable_id=entity(conn,'stable',stable),
                           breeder_id=entity(conn,'breeder',breeder),weight_kg=number(weight),draw=number(draw,True),
                           horse_raw=horse,source_line=lineno,row_raw=raw)
                # Each evidence item carries the race context. No raw mixed page goes to agents.
                snippet = f'{race_date} | {venue} | race {r["number"]} | {r["phase"]}\n{r["header_raw"]}\n{raw}'
                insert(conn,'evidence',id=uid(sid,vid,cloth,'evidence'),snapshot_id=sid,text=snippet,
                       entity_id=entity(conn,'horse',horse_name(horse)),related_race_id=rid,
                       kind='result' if r['phase']=='result' else 'declaration',locator=f'L{lineno}')
        discrepancies = conn.execute('''
          SELECT a.race_id,e.cloth,e.horse_raw AS declared,z.horse_raw AS actual,e.withdrawn,z.position
          FROM race_versions a JOIN entries e ON e.race_version_id=a.id
          JOIN race_versions b ON b.race_id=a.race_id AND b.snapshot_id=a.snapshot_id AND b.phase='result'
          JOIN results z ON z.race_version_id=b.id AND z.cloth=e.cloth
          WHERE a.snapshot_id=? AND (e.horse_id<>z.horse_id OR (e.withdrawn=1 AND z.position IS NOT NULL))
        ''',(sid,)).fetchall()
        for row in discrepancies:
            detail = json.dumps(dict(row),ensure_ascii=False)
            insert(conn,'quality_issues',id=uid(sid,detail),snapshot_id=sid,race_id=row['race_id'],
                   code='declaration_result_difference',detail=detail)
    return sid


def prepare_browser_seed(bundle_path, output_dir):
    """Merge overlapping numbered viewports, preserving the original bundle alongside them."""
    bundle = json.loads(Path(bundle_path).read_text())
    pages = {}
    pattern = re.compile(r'Datos de Jornada[^\n]*\((https://jockey-club.es/datos-de-jornada/\?date=(\d{8})&id=(\d+))\)\n(.*?)(?=\n-{5,}\n|\Z)',re.S)
    for extract in bundle['extracts']:
        for m in pattern.finditer(extract['text']):
            page = pages.setdefault(m[2],dict(url=m[1],venue_id=m[3],lines={},conflicts=[]))
            for line in m[4].splitlines():
                lm = re.match(r'^L(\d+):\s?(.*)$',line)
                if lm:
                    n,s = int(lm[1]),lm[2]
                    if n in page['lines'] and page['lines'][n]!=s:
                        page['conflicts'].append(n)
                    page['lines'].setdefault(n,s)
    # These bounds were inspected in the public source; include every declaration and result.
    bounds = {'20261101':(316,533),'20261025':(329,516)}
    out = Path(output_dir)
    out.mkdir(parents=True,exist_ok=True)
    manifest = []
    for d,(lo,hi) in bounds.items():
        p = pages[d]
        missing = sorted(set(range(lo,hi+1))-p['lines'].keys())
        if missing:
            raise ValueError(f'Missing browser lines for {d}: {missing}')
        path = out/f'jce_{d}_1.txt'
        path.write_text('\n'.join(f'L{n}: {p["lines"][n]}' for n in range(lo,hi+1))+'\n')
        manifest.append(dict(file=path.name,url=p['url'],race_date=f'{d[:4]}-{d[4:6]}-{d[6:]}',
                             venue_id=p['venue_id'],venue='La Zarzuela',line_start=lo,line_end=hi,
                             overlapping_line_differences=sorted(set(p['conflicts']))))
    return manifest
