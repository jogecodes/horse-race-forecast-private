import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from horse_racing.recovery import collect_official
r=collect_official();print('Completed',len(r['records']),'documents;',len(r['errors']),'errors')
