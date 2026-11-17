"""Materialize quote/start evidence separately from the immutable original odds observations."""
import csv,json,sqlite3,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from horse_racing.benchmark import digest,read_jsonl,write_jsonl
from horse_racing.recovered_benchmark import score
report=json.loads(Path('data/odds_actual_start_comparison.json').read_text())
starts=json.loads(Path('data/actual_starts_h1_2026.json').read_text())['starts']
path=Path('data/odds_with_actual_starts.sqlite');c=sqlite3.connect(path)
c.executescript('''CREATE TABLE IF NOT EXISTS start_evidence(source_sha256 TEXT PRIMARY KEY,payload_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS comparisons(observation_id TEXT PRIMARY KEY,race_id TEXT NOT NULL,runner_id TEXT NOT NULL,
quote_kind TEXT NOT NULL,decimal_value REAL NOT NULL,quote_at TEXT NOT NULL,actual_start_at TEXT NOT NULL,
seconds_before_actual_start REAL NOT NULL,timing_class TEXT NOT NULL,start_proof_url TEXT NOT NULL,start_proof_sha256 TEXT NOT NULL REFERENCES start_evidence(source_sha256));
CREATE TRIGGER IF NOT EXISTS comparisons_no_update BEFORE UPDATE ON comparisons BEGIN SELECT RAISE(ABORT,'append-only'); END;
CREATE TRIGGER IF NOT EXISTS comparisons_no_delete BEFORE DELETE ON comparisons BEGIN SELECT RAISE(ABORT,'append-only'); END;
CREATE TRIGGER IF NOT EXISTS starts_no_update BEFORE UPDATE ON start_evidence BEGIN SELECT RAISE(ABORT,'append-only'); END;
CREATE TRIGGER IF NOT EXISTS starts_no_delete BEFORE DELETE ON start_evidence BEGIN SELECT RAISE(ABORT,'append-only'); END;''')
c.execute('PRAGMA foreign_keys=ON')
with c:
 for s in starts:c.execute('INSERT OR IGNORE INTO start_evidence VALUES(?,?)',(s['source_sha256'],json.dumps(s,ensure_ascii=False)))
 for q in report['comparisons']:
  c.execute('INSERT OR IGNORE INTO comparisons VALUES('+','.join('?' for _ in q)+')',tuple(q[k] for k in ['observation_id','race_id','runner_id','quote_kind','decimal_value','quote_at','actual_start_at','seconds_before_actual_start','timing_class','start_proof_url','start_proof_sha256']))
print('Integrity',c.execute('PRAGMA integrity_check').fetchone()[0]);c.close()
for name,rows in [('odds_actual_start_comparison',report['comparisons']),('odds_preoff_last60s',[q for q in report['comparisons'] if q['timing_class']=='last_60_seconds_before_actual_start'])]:
 with Path('data/'+name+'.csv').open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=rows[0].keys() if rows else []);w.writeheader();w.writerows(rows)
# A later-information market comparator, only on complete recorded-starter price vectors.
for bundle in ['benchmarks/h1_2026_v1','benchmarks/h1_2026_v2']:
 if not Path(bundle).exists():continue
 labels={r['race_id']:r['target'] for r in read_jsonl(Path(bundle)/'supervisor/labels.jsonl')};prices={}
 for q in report['comparisons']:
  if q['timing_class']=='last_60_seconds_before_actual_start' and q['quote_kind']=='dernierRapportDirect':prices.setdefault(q['race_id'],{})[q['runner_id']]=q['decimal_value']
 predictions=[];excluded=[]
 for rid,values in prices.items():
  if rid not in labels:continue
  # A declared-field benchmark may contain nonstarters. Do not infer zero win chance from future withdrawals.
  if set(values)!=set(labels[rid]):excluded.append(dict(race_id=rid,reason='Incomplete prices for declared field; no imputation or post-cutoff withdrawal adjustment'));continue
  inverse={k:1/v for k,v in values.items()};total=sum(inverse.values())
  predictions.append(dict(race_id=rid,probabilities={k:v/total for k,v in inverse.items()}))
 target=Path('data/market_comparators')/Path(bundle).name;target.mkdir(parents=True,exist_ok=True)
 pred=target/'preoff_predictions.jsonl';write_jsonl(pred,predictions)
 result=score(bundle,pred,'validation');result.update(comparator='Normalized inverse PMU probable win returns, latest stored direct quotes timestamped within 60s before actual off',
  protocol='Later-information comparator, forbidden in previous-evening forecast inputs. Full price vectors only; no missing-price imputation.',excluded_incomplete_fields=excluded,
  source_report_sha256=digest('data/odds_actual_start_comparison.json'))
 (target/'scores.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
 print(bundle,'complete market vectors',len(predictions),'incomplete declared fields',len(excluded))
