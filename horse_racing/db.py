from __future__ import annotations
import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def uid(*parts):
    return hashlib.sha256(json.dumps(parts, ensure_ascii=False).encode()).hexdigest()[:32]


def utc(value):
    dt = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if dt.tzinfo is None:
        raise ValueError('Timestamp must contain a timezone')
    return dt.astimezone(timezone.utc).isoformat(timespec='seconds')


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def connect(path):
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys=ON')
    return conn


def initialize(path):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = connect(path)
    schema = Path(__file__).with_name('schema.sql').read_text()
    version_table = conn.execute("SELECT name FROM sqlite_master WHERE name='schema_version'").fetchone()
    if version_table:
        version = conn.execute('SELECT version FROM schema_version').fetchone()[0]
        if version == 1:
            import re
            definition = re.search(r'CREATE TABLE IF NOT EXISTS results\(.*?\n\);',schema,re.S)[0]
            definition = definition.replace('CREATE TABLE IF NOT EXISTS results(', 'CREATE TABLE results_v2(',1)
            try:
                conn.executescript('BEGIN IMMEDIATE;\n'+definition+"""
                INSERT INTO results_v2 SELECT * FROM results;
                DROP TABLE results;
                ALTER TABLE results_v2 RENAME TO results;
                DROP TABLE schema_version;
                CREATE TABLE schema_version(version INTEGER PRIMARY KEY CHECK(version=2));
                INSERT INTO schema_version VALUES(2);
                COMMIT;
                """)
            except Exception:
                conn.rollback()
                raise
        elif version not in (2,3):
            raise ValueError(f'Unsupported schema version: {version}')
        if version in (1,2):
            # Race-order labels in historical sources can be duplicated by source errors.
            # Keep each source race distinct instead of collapsing it on that label.
            conn.execute('PRAGMA foreign_keys=OFF')
            try:
                conn.executescript("""BEGIN IMMEDIATE;
                CREATE TABLE races_v3(
                  id TEXT PRIMARY KEY,meeting_id TEXT NOT NULL REFERENCES meetings(id),
                  race_number INTEGER NOT NULL CHECK(race_number>0));
                INSERT INTO races_v3 SELECT * FROM races;
                DROP TABLE races;
                ALTER TABLE races_v3 RENAME TO races;
                DROP TABLE schema_version;
                CREATE TABLE schema_version(version INTEGER PRIMARY KEY CHECK(version=3));
                INSERT INTO schema_version VALUES(3);
                """)
                if conn.execute('PRAGMA foreign_key_check').fetchall():
                    raise ValueError('Foreign-key failure during v3 migration')
                conn.commit()
            except Exception:
                conn.rollback()
                raise
            finally:
                conn.execute('PRAGMA foreign_keys=ON')
    conn.executescript(schema)
    # Application operations append new snapshots/versions. Corrections never rewrite provenance.
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name!='schema_version'")]
    for table in tables:
        for op in ('UPDATE', 'DELETE'):
            conn.execute(f"CREATE TRIGGER IF NOT EXISTS immutable_{table}_{op} BEFORE {op} ON {table} BEGIN SELECT RAISE(ABORT,'append-only table'); END")
    conn.commit()
    return conn


def insert(conn, table, **values):
    cols = ','.join(values)
    conn.execute(f"INSERT OR IGNORE INTO {table} ({cols}) VALUES ({','.join('?' for _ in values)})", tuple(values.values()))


def entity(conn, kind, name):
    if not name or name.strip() in ('-', '--'):
        return None
    # Conservative exact source-local matching. Registry IDs/aliases are a later enrichment.
    name = ' '.join(name.split())
    ident = uid('jce',kind,name)
    insert(conn, 'entities', id=ident, kind=kind, name=name, identity_scope='jce:exact-name:provisional')
    return ident


def snapshot(conn, source_id, url, body, observed_at, method='web.run-rendered-extract', media_type='text/plain; charset=utf-8'):
    observed_at = utc(observed_at)
    digest = hashlib.sha256(body.encode()).hexdigest()
    ident = uid(url,digest,observed_at)
    insert(conn,'snapshots',id=ident,source_id=source_id,url=url,observed_at=observed_at,
           media_type=media_type,body=body,sha256=digest,collection_method=method)
    return ident


def stats(conn):
    tables = ['sources','snapshots','meetings','races','race_versions','entities','entries','results','quality_issues','evidence','forecast_runs','judge_votes','packet_exports','entity_identifiers','race_identifiers','race_details','result_details']
    counts = {t:conn.execute(f'SELECT count(*) FROM {t}').fetchone()[0] for t in tables}
    counts['entities_by_kind'] = dict(conn.execute('SELECT kind,count(*) FROM entities GROUP BY kind'))
    counts['meetings_detail'] = [dict(r) for r in conn.execute('SELECT id,race_date,venue FROM meetings ORDER BY race_date')]
    counts['foreign_key_errors'] = [tuple(r) for r in conn.execute('PRAGMA foreign_key_check')]
    counts['integrity'] = conn.execute('PRAGMA integrity_check').fetchone()[0]
    return counts


def coverage(conn):
    """Actual canonical race coverage, with a documented current-label selection policy."""
    result = {'schema_version':conn.execute('SELECT version FROM schema_version').fetchone()[0]}
    for name,table in [('races','races'),('meetings','meetings'),('source_result_rows','results'),
                       ('selected_runner_rows','latest_results'),('source_snapshots','snapshots')]:
        result[name] = conn.execute(f'SELECT count(*) FROM {table}').fetchone()[0]
    result['date_range'] = dict(conn.execute('SELECT min(race_date) AS first,max(race_date) AS last FROM meetings').fetchone())
    result['by_year'] = [dict(r) for r in conn.execute('''
      SELECT substr(m.race_date,1,4) AS year,count(DISTINCT x.race_id) AS races,
             count(*) AS runner_rows,count(DISTINCT m.id) AS meetings
      FROM latest_results x JOIN races r ON r.id=x.race_id JOIN meetings m ON m.id=r.meeting_id
      GROUP BY year ORDER BY year''')]
    result['by_venue'] = [dict(r) for r in conn.execute('''
      SELECT m.venue,count(DISTINCT x.race_id) AS races,count(*) AS runner_rows,
             min(m.race_date) AS first,max(m.race_date) AS last
      FROM latest_results x JOIN races r ON r.id=x.race_id JOIN meetings m ON m.id=r.meeting_id
      GROUP BY m.venue ORDER BY races DESC''')]
    result['by_source'] = [dict(r) for r in conn.execute('''
      SELECT s.source_id,count(DISTINCT v.race_id) AS races,count(*) AS runner_rows,
             min(m.race_date) AS first,max(m.race_date) AS last
      FROM results x JOIN race_versions v ON v.id=x.race_version_id
      JOIN snapshots s ON s.id=v.snapshot_id JOIN races r ON r.id=v.race_id
      JOIN meetings m ON m.id=r.meeting_id GROUP BY s.source_id''')]
    result['provider_horse_ids'] = dict(conn.execute("SELECT source_id,count(*) FROM entity_identifiers WHERE kind='horse' GROUP BY source_id"))
    result['quality_issues'] = dict(conn.execute('SELECT code,count(*) FROM quality_issues GROUP BY code'))
    result['snapshot_observation_range'] = dict(conn.execute('SELECT min(observed_at) AS first,max(observed_at) AS last FROM snapshots').fetchone())
    result['foreign_key_errors'] = [tuple(r) for r in conn.execute('PRAGMA foreign_key_check')]
    result['integrity'] = conn.execute('PRAGMA integrity_check').fetchone()[0]
    result['historical_feature_eligibility'] = 'Newly collected current pages are not evidence of pre-race historical availability.'
    return result
