import subprocess,json
from pathlib import Path
runs=[]
for model,label in [('llama3.1:8b','llama'),('gemma3:4b','gemma')]:
 out='runs/event_grounded_v2_'+label+'_replay_20261106'
 args=['.venv/bin/python','-u','scripts/evaluate_semantic_review.py','--dataset','data/event_grounded_review_v1/dataset.json','--out',out,'--ollama-base','http://127.0.0.1:11438','--policies','event-grounded','--model',model]
 print(json.dumps(dict(starting=model,out=out)),flush=True)
 result=subprocess.run(args)
 runs.append(dict(model=model,out=out,exit_code=result.returncode))
 Path('data/event_grounded_review_v1/model_comparison_status.json').write_text(json.dumps(runs,indent=2)+'\n')
 if result.returncode:raise SystemExit(result.returncode)
