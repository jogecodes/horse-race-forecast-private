import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from horse_racing.recovered_benchmark import score
p=argparse.ArgumentParser();p.add_argument('--bundle',default='benchmarks/h1_2026_v2');p.add_argument('--predictions',required=True)
p.add_argument('--split',choices=['development','validation','test','all'],default='test');p.add_argument('--out',required=True);a=p.parse_args()
out=Path(a.out)
if out.exists():raise FileExistsError(out)
result=score(a.bundle,a.predictions,a.split);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(result['overall'],indent=2))
