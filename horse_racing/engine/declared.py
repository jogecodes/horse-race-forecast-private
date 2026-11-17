"""Strict runs from collected declarations, without result reconstruction or labels."""
import json,sqlite3,shutil
from pathlib import Path
from ..db import utc,now,uid
from ..benchmark import digest
from . import ENGINE_VERSION
from .pipeline import forecast
from .model import Audit,Ollama
from .discovery import Explorer
from .leakage import JudgePanel
from .run import audit_run


def declaration_task(db,race_id,cutoff):
    cutoff=utc(cutoff)
    c=sqlite3.connect('file:'+str(Path(db).resolve())+'?mode=ro',uri=True);c.row_factory=sqlite3.Row
    try:
        row=c.execute('''SELECT v.id,v.distance_m,m.race_date,m.venue,s.id snapshot_id,s.sha256,s.observed_at
          FROM race_versions v JOIN races r ON r.id=v.race_id JOIN meetings m ON m.id=r.meeting_id
          JOIN snapshots s ON s.id=v.snapshot_id WHERE v.race_id=? AND v.phase='declaration'
          AND s.observed_at<=? ORDER BY s.observed_at DESC,v.id LIMIT 1''',(race_id,cutoff)).fetchone()
        if row is None:raise ValueError('No collected pre-cutoff declaration exists for this race')
        # No verified actual off is stored: require a preceding local calendar day.
        from zoneinfo import ZoneInfo
        from datetime import datetime
        if datetime.fromisoformat(cutoff).astimezone(ZoneInfo('Europe/Madrid')).date().isoformat()>=row['race_date']:
            raise ValueError('Strict declaration forecasts currently require a cutoff before race day in Europe/Madrid')
        runners=[dict(runner_id='runner_'+uid(race_id,r['horse_id']),horse_name=r['name'],jockey_name=r['jockey_name'],trainer_name=r['trainer_name'],stable_name=r['stable_name']) for r in c.execute('''
          SELECT e.horse_id,h.name,j.name jockey_name,t.name trainer_name,s.name stable_name FROM entries e JOIN entities h ON h.id=e.horse_id
          LEFT JOIN entities j ON j.id=e.jockey_id LEFT JOIN entities t ON t.id=e.trainer_id LEFT JOIN entities s ON s.id=e.stable_id
          WHERE e.race_version_id=? AND e.withdrawn=0 ORDER BY e.cloth''',(row['id'],))]
        if len(runners)<2:raise ValueError('At least two non-withdrawn declared runners required')
        return dict(race_id=race_id,date=row['race_date'],venue=row['venue'],distance_m=row['distance_m'],
                    cutoff_utc=cutoff,track='strict',input_availability='collected_pre_cutoff_declaration',runners=runners),dict(row)
    finally:c.close()


def run_declared(db,race_id,cutoff,out,rounds=2,model_name='llama3.1:8b',seed_urls=(),search_backend='builtin',max_search_queries=12,max_research_pages=12):
    task,proof=declaration_task(db,race_id,cutoff)
    out=Path(out)
    if out.exists():raise FileExistsError(out)
    out.mkdir(parents=True)
    code=Path(__file__).parent
    (out/'source').mkdir()
    for p in code.glob('*.py'):shutil.copyfile(p,out/'source'/p.name)
    audit=Audit(out/'ledgers/declared.jsonl');model=Ollama(audit);panel=JudgePanel(model,audit)
    installed=model.tags();needed={model_name,*panel.models.values()}
    if not needed.issubset({m['name'] for m in installed}):raise ValueError('Required local models unavailable; no automatic download')
    audit.log('declaration_proof',proof=proof,task=task)
    result=forecast(task,model,Explorer(out/'research_cache',audit,model,task,policy='strict',search_backend=search_backend,max_queries=max_search_queries,max_pages=max_research_pages,research_model=model_name),panel,audit,rounds=rounds,
                    planner_model=model_name,forecaster_model=model_name,selector_model=model_name,seed_urls=seed_urls)
    (out/'prediction.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    manifest=dict(engine_version=ENGINE_VERSION,track='strict_declaration',created_at=now(),task=task,declaration_proof=proof,
      installed_models=installed,model=model_name,judges=panel.models,rounds=rounds,seed_urls=list(seed_urls),
      research_policy='strict',search_backend=search_backend,max_search_queries=max_search_queries,max_research_pages=max_research_pages,known_answers='not read or supplied',source_hashes={p.name:digest(p) for p in code.glob('*.py')},
      ledger_sha256={'ledgers/declared.jsonl':digest(audit.path)})
    (out/'run_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    audit_run(out)
    return result
