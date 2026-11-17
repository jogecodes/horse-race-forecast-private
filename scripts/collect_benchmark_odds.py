from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from horse_racing.odds import collect
r=collect('benchmarks/h1_2026_v1','data/racing.sqlite','data/odds_h1_2026.sqlite',
          'data/raw/pmu_h1_2026','data/odds_h1_2026_report.json')
print({k:v for k,v in r.items() if k not in ('provider_meetings','unmatched_participants','errors')})

# Human-readable export, retaining every timing/provenance field.
import csv,sqlite3
c=sqlite3.connect('data/odds_h1_2026.sqlite');c.row_factory=sqlite3.Row
rows=c.execute('SELECT * FROM observations ORDER BY race_id,runner_id,source,quote_kind').fetchall()
with open('data/odds_h1_2026.csv','w',newline='') as f:
    writer=csv.DictWriter(f,fieldnames=rows[0].keys() if rows else [])
    writer.writeheader();writer.writerows(dict(r) for r in rows)
c.close()
