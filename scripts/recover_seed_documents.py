import json,re,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from horse_racing.recovery import RecoveryCache,pdf_artifact,parse_declaration
cache=RecoveryCache();records=[];errors=[]
for seed in json.loads(Path('data/h1_document_seeds.json').read_text()):
 try:
  match=re.search(r'/d/([^/]+)',seed['original_url']) if 'drive.google.com' in seed['original_url'] else None
  url='https://drive.google.com/uc?export=download&id='+match[1] if match else seed['original_url']
  body,receipt=cache.get(url);doc=pdf_artifact(body,receipt)
  record=dict(seed,document=doc)
  try:record['races']=parse_declaration(doc['text'],seed['date'])
  except ValueError as e:record['parse_error']=str(e)
  records.append(record);print(seed['date'],len(record.get('races',[])),record.get('parse_error'),flush=True)
 except Exception as e:errors.append(dict(seed=seed,error=str(e)));print(str(e),flush=True)
 Path('data/recovery_seed_h1_2026.json').write_text(json.dumps(dict(records=records,errors=errors,cache_root=str(cache.root)),ensure_ascii=False,indent=2)+'\n')
