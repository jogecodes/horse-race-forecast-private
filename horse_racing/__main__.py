import argparse
import json
from pathlib import Path
from .db import initialize, now, snapshot, insert, uid, stats, coverage
from .ingest import import_jce, prepare_browser_seed, register_sources
from .gate import create_run, record_vote, decision, export_packet


def main():
    parser = argparse.ArgumentParser(description='Private Spanish horse racing research database')
    parser.add_argument('--db',default='data/racing.sqlite')
    sub = parser.add_subparsers(dest='command',required=True)
    sub.add_parser('init')
    sub.add_parser('stats')
    cov = sub.add_parser('coverage')
    cov.add_argument('--out')
    seed = sub.add_parser('seed')
    seed.add_argument('--manifest',default='data/raw/seed_manifest.json')
    imp = sub.add_parser('import-jce')
    imp.add_argument('--file',required=True)
    imp.add_argument('--date',required=True)
    imp.add_argument('--venue-id',required=True)
    imp.add_argument('--venue',required=True)
    imp.add_argument('--observed-at',required=True,help='Actual acquisition time with timezone, never the race date')
    hist = sub.add_parser('import-mdh-cache')
    hist.add_argument('--cache',default='data/raw/mdh')
    hist.add_argument('--start-date',default='2022-01-01')
    hist.add_argument('--end-date',default='2026-11-05')
    hist.add_argument('--report',default='data/mdh_import_report.json')
    add = sub.add_parser('add-evidence')
    add.add_argument('--file',required=True)
    add.add_argument('--source',required=True)
    add.add_argument('--url',required=True)
    add.add_argument('--kind',choices=['context','declaration','result'],default='context')
    add.add_argument('--race')
    add.add_argument('--locator',required=True)
    run = sub.add_parser('create-run')
    run.add_argument('--race',required=True)
    run.add_argument('--cutoff',required=True)
    run.add_argument('--judges',nargs='+',required=True)
    vote = sub.add_parser('vote')
    vote.add_argument('--run',required=True)
    vote.add_argument('--evidence',required=True)
    vote.add_argument('--judge',required=True)
    vote.add_argument('--model',required=True)
    vote.add_argument('--response-file',required=True)
    vote.add_argument('--prompt-file',required=True)
    check = sub.add_parser('gate')
    check.add_argument('--run',required=True)
    check.add_argument('--evidence',required=True)
    packet = sub.add_parser('export-packet')
    packet.add_argument('--run',required=True)
    packet.add_argument('--out',required=True)
    bench = sub.add_parser('build-benchmark')
    bench.add_argument('--cache',default='data/raw/todoturf_h1_2026')
    bench.add_argument('--out',default='benchmarks/h1_2026_v1')
    base = sub.add_parser('benchmark-baseline')
    base.add_argument('--bundle',default='benchmarks/h1_2026_v1')
    base.add_argument('--kind',choices=['uniform','history'],required=True)
    base.add_argument('--out',required=True)
    evaluate = sub.add_parser('score-benchmark')
    evaluate.add_argument('--bundle',default='benchmarks/h1_2026_v1')
    evaluate.add_argument('--predictions',required=True)
    evaluate.add_argument('--split',choices=['development','validation','test','all'],default='test')
    evaluate.add_argument('--out',required=True)
    args = parser.parse_args()
    if args.command=='build-benchmark':
        from .benchmark import build
        result=build(args.db,args.cache,args.out)
        print(json.dumps({k:v for k,v in result.items() if k!='files'},ensure_ascii=False,indent=2))
        return
    if args.command=='benchmark-baseline':
        from .benchmark import baseline_predictions,write_jsonl
        result=baseline_predictions(args.bundle,args.kind)
        if Path(args.out).exists():raise FileExistsError(args.out)
        write_jsonl(args.out,result)
        print(json.dumps(dict(predictions=len(result),baseline=args.kind,out=args.out)))
        return
    if args.command=='score-benchmark':
        from .benchmark import score
        result=score(args.bundle,args.predictions,args.split)
        if Path(args.out).exists():raise FileExistsError(args.out)
        Path(args.out).parent.mkdir(parents=True,exist_ok=True)
        Path(args.out).write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n')
        print(json.dumps(dict(split=args.split,coverage=result['coverage'],overall=result['overall'],out=args.out),indent=2))
        return
    conn = initialize(args.db)
    if args.command=='init':
        with conn: register_sources(conn)
        result = {'database':args.db,'schema_version':3}
    elif args.command=='stats':
        result = stats(conn)
    elif args.command=='coverage':
        result = coverage(conn)
        if args.out:
            Path(args.out).parent.mkdir(parents=True,exist_ok=True)
            Path(args.out).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    elif args.command=='seed':
        manifest_path = Path(args.manifest)
        manifest = json.loads(manifest_path.read_text())
        for item in manifest['meetings']:
            import_jce(conn,(manifest_path.parent/item['file']).read_text(),item['race_date'],
                       item['venue_id'],item['venue'],manifest['observed_at'])
        result = stats(conn)
    elif args.command=='import-jce':
        result = {'snapshot_id':import_jce(conn,Path(args.file).read_text(),args.date,args.venue_id,args.venue,args.observed_at)}
    elif args.command=='import-mdh-cache':
        from .mdh import import_cache
        report = import_cache(conn,args.cache,args.start_date,args.end_date)
        Path(args.report).parent.mkdir(parents=True,exist_ok=True)
        Path(args.report).write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
        result = dict(validated_result_pages=report['imported'],runner_rows=report['runners'],
                      excluded_pages=len(report['excluded']),rejected_pages=len(report['errors']),
                      missing_downloads=len(report['not_downloaded']),report=args.report)
    elif args.command=='add-evidence':
        body = Path(args.file).read_text()
        with conn:
            sid = snapshot(conn,args.source,args.url,body,now(),'operator-supplied-extract')
            eid = uid(sid,body,args.locator)
            insert(conn,'evidence',id=eid,snapshot_id=sid,text=body,related_race_id=args.race,kind=args.kind,locator=args.locator)
        result = {'evidence_id':eid,'snapshot_id':sid}
    elif args.command=='create-run':
        result = {'run_id':create_run(conn,args.race,args.cutoff,args.judges)}
    elif args.command=='vote':
        result = {'verdict':record_vote(conn,args.run,args.evidence,args.judge,Path(args.response_file).read_text(),
                                         args.model,Path(args.prompt_file).read_text())}
    elif args.command=='gate':
        result = decision(conn,args.run,args.evidence)
    elif args.command=='export-packet':
        result = export_packet(conn,args.run,args.out)
    print(json.dumps(result,ensure_ascii=False,indent=2))
    conn.close()


if __name__=='__main__':
    main()
