#!/usr/bin/env python3
"""Capture a local provider export or evaluate one receipt-backed T-60 snapshot."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from horse_racing.market_watch import capture_export,inspect_market,persist_check

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--snapshot',type=Path,required=True)
    parser.add_argument('--prediction',type=Path)
    parser.add_argument('--capture-export',action='store_true')
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    if args.capture_export:
        snapshot=capture_export(args.snapshot,args.out)
        print(json.dumps(dict(status='captured_local_export',captured_at=snapshot['captured_at'])))
    else:
        if args.prediction is None:parser.error('--prediction is required when evaluating a snapshot')
        snapshot=json.loads(args.snapshot.read_text());prediction=json.loads(args.prediction.read_text())
        report=inspect_market(snapshot,prediction)
        persist_check(args.out,snapshot,prediction,report)
        print(json.dumps(report,ensure_ascii=False,indent=2))
