import argparse,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from horse_racing.recovered_benchmark import build
p=argparse.ArgumentParser();p.add_argument('--out',default='benchmarks/h1_2026_v2');a=p.parse_args()
print(json.dumps(build(a.out),indent=2,ensure_ascii=False))
