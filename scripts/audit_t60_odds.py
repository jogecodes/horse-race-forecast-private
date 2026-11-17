#!/usr/bin/env python3
"""Read-only historical coverage audit; never reads race outcomes."""
import argparse
from collections import Counter
from datetime import datetime,timedelta,timezone
import hashlib
import json
from pathlib import Path
import sqlite3


def audit(db,out):
    if out.exists():raise FileExistsError(out)
    before=hashlib.sha256(db.read_bytes()).hexdigest()
    c=sqlite3.connect('file:'+str(db.resolve())+'?mode=ro',uri=True);c.row_factory=sqlite3.Row
    try:rows=[dict(r) for r in c.execute('SELECT * FROM observations')]
    finally:c.close()
    counts=Counter();race_ids=set();lead_times=[]
    for r in rows:
        if r['quote_kind']=='post_result_DG':counts['post_result_rows_excluded']+=1;continue
        counts['timestamped_pmu_rows']+=1;race_ids.add(r['race_id'])
        start=datetime.fromisoformat(r['scheduled_start_at']);cutoff=start-timedelta(hours=1)
        quote=datetime.fromisoformat(r['quote_at']);capture=datetime.fromisoformat(r['observed_at'])
        lead_times.append((start-quote).total_seconds()/60)
        if quote<=cutoff:counts['quote_timestamp_at_or_before_T60']+=1
        if quote<=cutoff and capture<=cutoff:counts['quote_and_capture_at_or_before_T60']+=1
        if r['market']=='PMU_SIMPLE_GAGNANT_probable_return':counts['pool_estimates_not_fixed_odds']+=1
    report=dict(created_at=datetime.now(timezone.utc).isoformat(),database=str(db),sha256=before,
        counts=dict(counts),historical_pmu_races=len(race_ids),
        quote_timestamp_at_or_before_T60=counts['quote_timestamp_at_or_before_T60'],
        quote_and_capture_at_or_before_T60=counts['quote_and_capture_at_or_before_T60'],
        eligible_fixed_odds_T60_races=0,
        earliest_saved_quote_minutes_before_scheduled_start=max(lead_times) if lead_times else None,
        interpretation='No eligible fixed-odds T-60 replay in the existing observations. '
            'Provider quote time and our actual capture time are separate requirements. '
            'No later prices or post-result dividends substituted; no outcomes read.')
    assert hashlib.sha256(db.read_bytes()).hexdigest()==before
    out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--db',required=True,type=Path);parser.add_argument('--out',required=True,type=Path)
    args=parser.parse_args();audit(args.db,args.out)
