"""Chronological ablations and an outcome-updated, earlier-day horse rating."""
from collections import defaultdict
from copy import deepcopy
import numpy as np
from .statistical import FEATURES, fit, softmax

EXTENDED_FEATURES=FEATURES+('prior_winner_rating',)
GROUPS={'career_form':(0,1),'recent_form':(2,),'distance_form':(3,),
        'recency':(4,),'winner_rating':(6,)}
VARIANTS={
    'legacy_full':tuple(range(6)),
    'full_with_rating':tuple(range(7)),
    **{name+'_only':tuple(sorted(set(indices+(5,)))) for name,indices in GROUPS.items()},
    'recent_and_rating':(2,5,6),
    **{'without_'+name:tuple(i for i in range(7) if i not in indices)
       for name,indices in GROUPS.items() if name!='winner_rating'},
    'without_missing_indicator':(0,1,2,3,4,6),
}


def add_prior_ratings(cases,step=.5):
    """Winner-softmax rating; update after the entire day, never between races.

    The fixed step is a predeclared baseline assumption, not selected on future
    performance. Multiple races on a day use the same earlier-day state.
    """
    if not np.isfinite(step) or step<=0:raise ValueError('Invalid rating step')
    cases=sorted(cases,key=lambda c:(c['date'],c['race_id']))
    ratings=defaultdict(float);output=[];pending=defaultdict(float);last_day=None
    for case in cases:
        if case['date']!=last_day:
            for hid,delta in pending.items():ratings[hid]+=delta
            pending=defaultdict(float);last_day=case['date']
        values=[ratings[hid] for hid in case['runner_ids']]
        result=deepcopy(case)
        result['x']=[row+[value] for row,value in zip(case['x'],values)]
        output.append(result)
        expected=softmax(values)
        for hid,y,p in zip(case['runner_ids'],case['y'],expected):pending[hid]+=step*(y-p)
    for hid,delta in pending.items():ratings[hid]+=delta
    return output,dict(ratings)


def add_frozen_ratings(public_case,ratings):
    result=deepcopy(public_case)
    assert len(result['x'])==len(result['identity_links'])
    result['x']=[row+[ratings.get(link['horse_id'],0.)]
                 for row,link in zip(result['x'],result['identity_links'])]
    return result


def project(cases,indices):
    if not indices or len(set(indices))!=len(indices):raise ValueError('Invalid feature subset')
    return [{**case,'x':[[row[i] for i in indices] for row in case['x']]} for case in cases]


def fit_subset(cases,indices,regularization,steps=1000):
    model=fit(project(cases,indices),regularization,steps)
    model['features']=[EXTENDED_FEATURES[i] for i in indices]
    model['feature_indices']=list(indices)
    return model


def chronological_parts(cases,train_end,tune_end,calibration_end,evaluation_end):
    if not train_end<tune_end<calibration_end<evaluation_end:raise ValueError('Invalid chronological boundaries')
    groups=[[],[],[],[]]
    for case in cases:
        day=case['date']
        index=0 if day<train_end else 1 if day<tune_end else 2 if day<calibration_end else 3 if day<evaluation_end else None
        if index is not None:groups[index].append(case)
    if any(not group for group in groups):raise ValueError('Empty chronological period')
    return groups
