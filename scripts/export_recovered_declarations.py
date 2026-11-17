"""Create a queryable declaration database, without benchmark result labels."""
import json,sqlite3,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from horse_racing.benchmark import verify,read_jsonl
bundle=Path('benchmarks/h1_2026_v2');verify(bundle)
c=sqlite3.connect('data/declarations_h1_2026.sqlite');c.execute('PRAGMA foreign_keys=ON')
c.executescript('''CREATE TABLE IF NOT EXISTS documents(sha256 TEXT PRIMARY KEY,url TEXT NOT NULL,observed_at TEXT NOT NULL,timing_tier TEXT NOT NULL,timing_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS races(race_id TEXT PRIMARY KEY,race_date TEXT NOT NULL,venue TEXT NOT NULL,cutoff_utc TEXT NOT NULL,distance_m INTEGER NOT NULL,ordinal INTEGER NOT NULL,document_sha256 TEXT NOT NULL REFERENCES documents(sha256));
CREATE TABLE IF NOT EXISTS entries(runner_id TEXT PRIMARY KEY,race_id TEXT NOT NULL REFERENCES races(race_id),cloth INTEGER NOT NULL,horse_name TEXT NOT NULL,jockey_name TEXT NOT NULL,trainer_name TEXT NOT NULL,stable_name TEXT NOT NULL,age INTEGER NOT NULL,declared_weight_kg REAL NOT NULL,draw INTEGER NOT NULL,prior_form_raw TEXT NOT NULL,UNIQUE(race_id,cloth));''')
for table in ('documents','races','entries'):
 for operation in ('UPDATE','DELETE'):
  c.execute(f"CREATE TRIGGER IF NOT EXISTS {table}_no_{operation.lower()} BEFORE {operation} ON {table} BEGIN SELECT RAISE(ABORT,'append-only'); END")
with c:
 for case in read_jsonl(bundle/'supervisor/cases.jsonl'):
  proof=case['declaration'];rid=case['race_id'];packet=json.loads((bundle/f'diagnostic/packets/{rid}.json').read_text())
  c.execute('INSERT OR IGNORE INTO documents VALUES(?,?,?,?,?)',(proof['sha256'],proof['url'],proof['observed_at'],proof['timing']['tier'],json.dumps(proof['timing'])))
  c.execute('INSERT OR IGNORE INTO races VALUES(?,?,?,?,?,?,?)',(rid,packet['date'],packet['venue'],packet['cutoff_utc'],packet['distance_m'],proof['ordinal'],proof['sha256']))
  for r in packet['runners']:
   c.execute('INSERT OR IGNORE INTO entries VALUES('+','.join('?' for _ in range(11))+')',tuple([r['runner_id'],rid]+[r[k] for k in ['cloth','horse_name','jockey_name','trainer_name','stable_name','age','declared_weight_kg','draw','prior_form_raw']]))
print('Integrity',c.execute('PRAGMA integrity_check').fetchone()[0])
print('Documents/races/entries',[c.execute('SELECT count(*) FROM '+t).fetchone()[0] for t in ['documents','races','entries']]);c.close()
