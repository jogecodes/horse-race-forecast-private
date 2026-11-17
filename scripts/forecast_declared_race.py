"""Forecast a declaration collected before the cutoff; never read result labels."""
import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from horse_racing.engine.declared import run_declared
p=argparse.ArgumentParser()
p.add_argument('--db',default='data/racing.sqlite');p.add_argument('--race',required=True)
p.add_argument('--cutoff',required=True);p.add_argument('--out',required=True)
p.add_argument('--model',default='llama3.1:8b');p.add_argument('--rounds',type=int,default=2)
p.add_argument('--seed-url',action='append',default=[])
p.add_argument('--search-backend',choices=['builtin','stdio'],default='builtin')
p.add_argument('--max-search-queries',type=int,default=12);p.add_argument('--max-research-pages',type=int,default=12)
a=p.parse_args()
print(json.dumps(run_declared(a.db,a.race,a.cutoff,a.out,a.rounds,a.model,a.seed_url,a.search_backend,a.max_search_queries,a.max_research_pages),indent=2,ensure_ascii=False))
