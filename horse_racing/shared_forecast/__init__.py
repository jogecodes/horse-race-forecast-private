"""Study-owned adapter; orchestration is imported from the sibling project."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sqlite3
import sys

SYSTEM_ROOT = Path('/app/more_studies/forecast-cal-dev')
sys.path.insert(0, str(SYSTEM_ROOT))
from forecast_system import Question, Source, HistoricalEnvironment  # noqa: E402
from forecast_system.contracts import timestamp  # noqa: E402

RUNNER_FIELDS = ('runner_id', 'horse_name', 'age', 'cloth', 'draw',
                 'declared_weight_kg', 'jockey_name', 'trainer_name',
                 'stable_name', 'prior_form_raw')
RACE_FIELDS = ('race_id', 'date', 'venue', 'distance_m', 'cutoff_utc')


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    """Atomically replace progress/results; traces remain append-only."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + '\n')
    tmp.replace(path)


def public_packet(packet):
    if packet.get('split') != 'development':
        raise ValueError('This experiment is development-only')
    result = {k: packet[k] for k in RACE_FIELDS}
    timestamp(result['cutoff_utc'])
    result['runners'] = [{k: r[k] for k in RUNNER_FIELDS if k in r}
                         for r in packet['runners']]
    ids = [r['runner_id'] for r in result['runners']]
    if len(ids) < 2 or len(set(ids)) != len(ids):
        raise ValueError('Invalid declared field')
    return result


def question_for(packet, runner_id):
    if packet.get('split', 'development') != 'development':
        raise ValueError('This experiment is development-only')
    packet = public_packet({**packet, 'split': 'development'})
    target = next(r for r in packet['runners'] if r['runner_id'] == runner_id)
    return Question(
        id=packet['race_id'] + ':' + runner_id,
        question=(f"Will {target['horse_name']} be an official winner of the race "
                  f"at {packet['venue']} on {packet['date']}? "
                  'Current official declaration (publisher-documented retrospective input): '
                  + json.dumps(packet, ensure_ascii=False)),
        resolution_criteria=('YES if the named horse is an official first-place finisher '
                             'in this identified race; NO otherwise, including a later nonstarter. '
                             'A dead-heat first-place finisher counts YES. Forecast a binary '
                             'event, not a share of a distribution. Use information available '
                             'by the stated cutoff; declarations do not establish actual starts.'),
        forecast_time=packet['cutoff_utc'])


def declaration_sources(db):
    """Export development declarations only, with original timing/capture receipts.

    Archive mode here uses the explicit publisher-documented availability assumption;
    it does not claim independently certified historical byte availability.
    """
    conn = sqlite3.connect('file:' + str(Path(db).resolve()) + '?mode=ro', uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute('''SELECT r.*, e.*, d.url, d.observed_at, d.timing_json
            FROM races r JOIN entries e USING(race_id)
            JOIN documents d ON d.sha256=r.document_sha256
            WHERE r.race_date >= '2026-01-01' AND r.race_date < '2026-03-01'
            ORDER BY r.race_date,r.race_id,e.cloth''').fetchall()
    finally:
        conn.close()
    sources = []
    for row in rows:
        timing = json.loads(row['timing_json'])
        available = timing['claimed_available_at']
        if timestamp(available) > timestamp(row['cutoff_utc']):
            raise ValueError('Declaration has a post-cutoff publisher date')
        content = {k: row[k] for k in RUNNER_FIELDS}
        # Explicitly identified structured extraction, never presented as an original title.
        text = (f"Structured declaration extraction: {row['venue']}, {row['race_date']}, "
                f"race {row['ordinal']}, {row['distance_m']} metres. "
                'These are declared conditions and literal printed prior form; '
                'they do not establish race results or actual participation. '
                + json.dumps(content, ensure_ascii=False))
        sources.append(Source(
            id='declaration:' + row['runner_id'],
            title=f"Declaration extraction: {row['horse_name']} — {row['race_date']}",
            text=text, url=row['url'], available_at=available, kind='archive',
            provenance=json.dumps(dict(document_sha256=row['document_sha256'],
                observed_at=row['observed_at'], timing=timing,
                extraction='Frozen outcome-free declarations_h1_2026.sqlite; structured row',
                availability_assumption='publisher-documented; not independent archive proof'),
                ensure_ascii=False)))
    return sources


def environment_for(sources, cutoff, arm):
    if arm not in {'declaration_only', 'declaration_research'}:
        raise ValueError('Unknown experiment arm')
    return HistoricalEnvironment(sources if arm == 'declaration_research' else [], as_of=cutoff)


def score_rows(rows, labels):
    """Evaluator-only binary scoring. Never called by a forecasting worker."""
    scored = []
    for row in rows:
        p = row.get('probability')
        if p is None:
            continue
        import math
        if isinstance(p, bool) or not isinstance(p, (float, int)) or not math.isfinite(p) or not 0 <= p <= 1:
            raise ValueError('Invalid probability; no repair allowed')
        y = float(labels[row['race_id']][row['runner_id']] > 0)
        n = row['field_size']
        scored.append({**row, 'outcome': y, 'brier': (p-y)**2,
                       'uniform_brier': (1/n-y)**2})
    return scored
