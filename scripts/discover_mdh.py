import sys,json,time,re,argparse
from pathlib import Path
from urllib.request import urlopen,Request
from urllib.parse import urljoin,urlparse,parse_qs
from bs4 import BeautifulSoup
parser=argparse.ArgumentParser(description='Discover result URLs by following public seasonal archive links')
parser.add_argument('--cache',default='data/raw/mdh')
parser.add_argument('--max-indexes',type=int,default=30)
args=parser.parse_args()
root=Path(args.cache)
root.mkdir(parents=True,exist_ok=True)
queue=['https://www.masdehipodromos.com/articulo.cfm?idArticulo=14430','https://www.masdehipodromos.com/articulo.cfm?idArticulo=14266']
seen=set(); races=set(); indexes=[]
while queue and len(seen)<args.max_indexes:
 url=queue.pop(0); aid=parse_qs(urlparse(url).query.lower()).get('idarticulo',[''])[0]
 if aid in seen: continue
 seen.add(aid)
 p=root/f'index_{aid}.html'
 if p.exists(): b=p.read_bytes()
 else:
  time.sleep(.6)
  try:
   r=urlopen(Request(url,headers={'User-Agent':'HorseRaceResearch/0.2 (private academic toy study; cached collection)'}),timeout=35); b=r.read();p.write_bytes(b)
  except Exception as e: print('FAILED',url,str(e),flush=True);continue
 s=BeautifulSoup(b,'html.parser')
 count=0
 for a in s.find_all('a',href=True):
  u=urljoin(url,a['href']);parsed=urlparse(u);q=parse_qs(parsed.query.lower())
  if parsed.hostname not in ['www.masdehipodromos.com','masdehipodromos.com']:continue
  if parsed.path.lower().endswith('/resultados2.cfm') and 'jidpremio' in q:
   races.add(q['jidpremio'][0]);count+=1
  elif parsed.path.lower().endswith('/articulo.cfm') and 'idarticulo' in q and 'esultados' in a.get_text():
   queue.append('https://www.masdehipodromos.com/articulo.cfm?idArticulo='+q['idarticulo'][0])
 indexes.append(dict(url=url,file=p.name,result_links=count))
 print('INDEX',aid,'links',count,'unique_races',len(races),flush=True)
(root/'discovery.json').write_text(json.dumps(dict(indexes=indexes,race_ids=sorted(races,key=int)),indent=2))
print('DISCOVERED',len(races),'races',len(indexes),'indexes',flush=True)
