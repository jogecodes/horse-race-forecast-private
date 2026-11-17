"""Race-level statistical baselines from strictly earlier-day result histories.

Historical result rosters and availability are retrospective assumptions. No target
race outcome, result field, market price or same-day result is a feature.
"""
from __future__ import annotations
from collections import defaultdict
from datetime import date
import math
import sqlite3
import unicodedata

import numpy as np

FEATURES = ('log_smoothed_win_rate', 'log_recorded_appearances',
            'recent_finish_strength', 'distance_weighted_win_rate',
            'log_days_since_recorded_appearance', 'history_missing')


def identity(name):
    name = name.replace('´', "'").replace('’', "'").replace('‘', "'")
    return ''.join(c for c in unicodedata.normalize('NFKD', name.upper())
                   if not unicodedata.combining(c) and not c.isspace())


def features(history, day, distance):
    earlier = [h for h in history if h['date'] < day]
    n = len(earlier)
    rate = (sum(h['win_share'] for h in earlier) + 1) / (n + 10)
    recent = earlier[-3:]
    strength = sum(h['finish_strength'] for h in recent) / len(recent) if recent else .5
    weights = [math.exp(-abs(h['distance_m']-distance)/400) for h in earlier]
    suited = (sum(w*h['win_share'] for w,h in zip(weights,earlier))+1)/(sum(weights)+10)
    days = (date.fromisoformat(day)-date.fromisoformat(earlier[-1]['date'])).days if earlier else 365
    return [math.log(rate), math.log1p(n), strength, suited,
            math.log1p(min(days,730)), float(n==0)]


def historical_cases(db):
    c = sqlite3.connect('file:' + str(db) + '?mode=ro', uri=True)
    c.row_factory = sqlite3.Row
    try:
        rows = c.execute('''SELECT x.race_id,x.horse_id,x.position,e.name,m.race_date,
            m.venue,m.id meeting_id,v.distance_m FROM latest_results x
            JOIN entities e ON e.id=x.horse_id JOIN races r ON r.id=x.race_id
            JOIN meetings m ON m.id=r.meeting_id
            JOIN race_versions v ON v.id=x.race_version_id
            WHERE m.race_date < '2026-01-01'
            ORDER BY m.race_date,x.race_id,x.horse_id''').fetchall()
    finally:
        c.close()
    races = defaultdict(list)
    for row in rows:
        races[row['race_id']].append(dict(row))
    histories, aliases = defaultdict(list), defaultdict(set)
    cases, pending, last_day, exclusions = [], [], None, []
    for rid, field in races.items():
        first = field[0]
        day, distance = first['race_date'], first['distance_m']
        if day != last_day:
            for hid, observation in pending:
                histories[hid].append(observation)
            pending = []
            last_day = day
        winners = [r for r in field if r['position']==1]
        if len(field)<2 or not winners or not distance:
            exclusions.append(dict(race_id=rid, reason='invalid_field_winner_or_distance'))
            continue
        x = [features(histories[r['horse_id']],day,distance) for r in field]
        y = [1/len(winners) if r['position']==1 else 0 for r in field]
        cases.append(dict(race_id=rid,date=day,meeting_id=first['meeting_id'],venue=first['venue'],
            x=x,y=y,runner_ids=[r['horse_id'] for r in field]))
        for r, win in zip(field,y):
            aliases[identity(r['name'])].add(r['horse_id'])
            # Unknown/non-finishing status stays explicitly neutral; never treated
            # as an observed last-place finish or used to remove a target runner.
            strength = ((len(field)-r['position'])/(len(field)-1)
                        if r['position'] is not None and 1<=r['position']<=len(field) else .5)
            pending.append((r['horse_id'],dict(date=day,distance_m=distance,
                win_share=win,finish_strength=strength)))
    for hid, observation in pending:
        histories[hid].append(observation)
    return cases, dict(histories), {k:sorted(v) for k,v in aliases.items()}, exclusions


def declaration_case(packet, histories, aliases):
    if packet['split'] != 'development':
        raise ValueError('Only development packets are authorized in this experiment')
    if packet['date'] < '2026-01-01':
        raise ValueError('Frozen histories require a 2026 target')
    x, links = [], []
    for runner in packet['runners']:
        candidates = aliases.get(identity(runner['horse_name']), [])
        hid = candidates[0] if len(candidates)==1 else None
        history = histories.get(hid, [])
        # Explicit guard against accidentally using updated/future history stores.
        if any(h['date'] >= '2026-01-01' for h in history):
            raise ValueError('Historical feature store exceeds the frozen boundary')
        x.append(features(history,packet['date'],packet['distance_m']))
        links.append(dict(runner_id=runner['runner_id'],horse_id=hid,
            status='matched' if hid else 'ambiguous' if candidates else 'no_history'))
    return dict(race_id=packet['race_id'],date=packet['date'],venue=packet['venue'],
        cutoff_utc=packet['cutoff_utc'],runner_ids=[r['runner_id'] for r in packet['runners']],
        x=x,identity_links=links)


def softmax(logits):
    scores = np.asarray(logits,dtype=float)
    if scores.ndim!=1 or len(scores)<2 or not np.isfinite(scores).all():
        raise ValueError('Invalid race scores')
    weights = np.exp(scores - scores.max())
    # This is the declared statistical model link, not repair of model outputs.
    return weights/weights.sum()


def fit(cases, regularization, steps=1000):
    x = np.asarray([row for c in cases for row in c['x']],dtype=float)
    y = np.asarray([value for c in cases for value in c['y']],dtype=float)
    sizes = np.asarray([len(c['x']) for c in cases]); starts = np.r_[0,np.cumsum(sizes)[:-1]]
    center, scale = x.mean(axis=0), x.std(axis=0)
    scale[scale<1e-8] = 1
    z = (x-center)/scale
    w, m, v = np.zeros(x.shape[1]), np.zeros(x.shape[1]), np.zeros(x.shape[1])
    for t in range(1,steps+1):
        logits=z@w
        maxima=np.maximum.reduceat(logits,starts)
        exp=np.exp(logits-np.repeat(maxima,sizes))
        p=exp/np.repeat(np.add.reduceat(exp,starts),sizes)
        gradient=z.T@(p-y)/len(cases)+regularization*w
        m=.9*m+.1*gradient; v=.999*v+.001*gradient**2
        w-=.03*(m/(1-.9**t))/(np.sqrt(v/(1-.999**t))+1e-8)
    if not np.isfinite(w).all():
        raise ValueError('Nonfinite learned coefficients')
    return dict(weights=w.tolist(),center=center.tolist(),scale=scale.tolist(),
                regularization=regularization,steps=steps,features=list(FEATURES))


def predict(case, kind, model=None, temperature=1.):
    x=np.asarray(case['x'],dtype=float)
    if temperature<=0:
        raise ValueError('Temperature must be positive')
    if kind=='uniform': return softmax(np.zeros(len(x))).tolist()
    if kind=='smoothed_history': return softmax(x[:,0]).tolist()
    if kind!='linear_race' or model is None: raise ValueError('Unknown model')
    z=(x-np.asarray(model['center']))/np.asarray(model['scale'])
    return softmax(z@np.asarray(model['weights'])/temperature).tolist()


def evaluate(probabilities, target):
    p=np.asarray(probabilities,dtype=float);y=np.asarray(target,dtype=float)
    if p.shape!=y.shape or not np.isfinite(p).all() or (p<0).any() or (p>1).any() or abs(p.sum()-1)>1e-6:
        raise ValueError('Invalid distribution; no repair allowed')
    top=p==p.max()
    return dict(brier=float(((p-y)**2).sum()),
        binary_brier_mean=float(((p-y)**2).mean()),
        log_loss=float(-(y*np.log(np.maximum(p,1e-15))).sum()),
        top1_fractional_accuracy=float(y[top].mean()))


def mean_metrics(cases, kind, model=None, temperature=1.):
    values=[evaluate(predict(c,kind,model,temperature),c['y']) for c in cases]
    return dict(races=len(cases),**{k:sum(v[k] for v in values)/len(values) for k in values[0]})
