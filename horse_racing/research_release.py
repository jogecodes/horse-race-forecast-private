"""Cohort-preserving research release; saved extractions are optional evidence."""
import numpy as np
from .agent_features import form_tokens, form_vector, fit_offset, predict_offset
from .forecast_comparison import score_predictions


def feature_case(packet, baseline, labels, extraction=None, *, augmented=False):
    """Keep deterministic form even when the optional extractor fails.

    Failed raw replies remain failed. The new model explicitly treats their
    semantic evidence as unavailable; it never repairs those extraction results.
    Article availability is encoded by the existing known-feature columns.
    """
    ids=[r['runner_id'] for r in packet['runners']]
    available=extraction is not None and extraction.get('status')=='complete'
    x=[]
    for r in packet['runners']:
        vector=form_vector(*form_tokens(r['prior_form_raw']))
        if augmented:
            extra=extraction['features'][r['runner_id']][6:] if available else [0.]*5
            if len(extra)!=5 or not np.isfinite(extra).all():raise ValueError('Invalid optional feature vector')
            vector+=extra
        x.append(vector)
    return dict(race_id=packet['race_id'],runner_ids=ids,x=x,
        baseline=[baseline[k] for k in ids],y=[labels[k] for k in ids])


def fit_arms(packets, baseline, labels, extractions):
    train=[p for p in packets if p['date']<'2026-02-01']
    test=[p for p in packets if '2026-02-01'<=p['date']<'2026-03-01']
    if not train or not test:raise ValueError('Both chronological cohorts are required')
    predictions={'baseline':{p['race_id']:baseline[p['race_id']] for p in test}}
    models={}
    for name,augmented in [('deterministic_form',False),('optional_agent',True)]:
        def case(p):
            rid=p['race_id']
            return feature_case(p,baseline[rid],labels[rid],extractions.get(rid),augmented=augmented)
        model=fit_offset([case(p) for p in train],regularization=1.,steps=1000)
        models[name]=dict(model=model,training_ids=[p['race_id'] for p in train],evaluation_ids=[p['race_id'] for p in test])
        predictions[name]={}
        for p in test:
            c=case(p);predictions[name][p['race_id']]=dict(zip(c['runner_ids'],predict_offset(c,model)))
    return predictions,models


def paired_interval(predictions, reference, labels, meetings, *, samples=4000, seed=20261112):
    """Percentile bootstrap resamples whole meetings, weights races equally."""
    if set(predictions)!=set(reference):raise ValueError('Pair cohorts must match exactly')
    _,a=score_predictions(predictions,labels);_,b=score_predictions(reference,labels)
    if set(a)!=set(predictions) or set(b)!=set(reference):raise ValueError('Invalid paired forecast')
    groups={}
    for rid in a:groups.setdefault(meetings[rid],[]).append(rid)
    keys=sorted(groups);rng=np.random.default_rng(seed)
    result=dict(races=len(a),meeting_clusters=len(keys),samples=samples,seed=seed,
        method='Meeting-cluster percentile bootstrap; races equally weighted; exploratory fixed-model development uncertainty, not training uncertainty')
    for metric in ['brier','log_loss']:
        diffs={rid:a[rid][metric]-b[rid][metric] for rid in a}
        if not diffs:result[metric]=None;continue
        sums=np.array([sum(diffs[r] for r in groups[k]) for k in keys])
        counts=np.array([len(groups[k]) for k in keys])
        draws=rng.integers(len(keys),size=(samples,len(keys)))
        values=sums[draws].sum(1)/counts[draws].sum(1)
        result[metric]=dict(difference=float(np.mean(list(diffs.values()))),
            interval_95=[float(v) for v in np.quantile(values,[.025,.975])])
    return result


def reliability(predictions, labels):
    """Fixed ten-bin runner-level diagnostic; no calibration fitted here."""
    report,_=score_predictions(predictions,labels)
    if report['errors']:raise ValueError('Invalid forecasts for reliability')
    bins=[dict(lower=i/10,upper=(i+1)/10,count=0,predicted_sum=0.,outcome_sum=0.) for i in range(10)]
    for rid,rows in predictions.items():
        for k,p in rows.items():
            b=bins[min(int(p*10),9)];b['count']+=1;b['predicted_sum']+=p;b['outcome_sum']+=labels[rid][k]
    total=sum(b['count'] for b in bins);ece=0.
    for b in bins:
        n=b['count'];b['mean_probability']=b.pop('predicted_sum')/n if n else None
        b['observed_win_share']=b.pop('outcome_sum')/n if n else None
        if n:ece+=n*abs(b['mean_probability']-b['observed_win_share'])/total
    return dict(bins=bins,runners=total,ece=ece,
        interpretation='Descriptive pooled-runner ten-bin ECE. Small development cohort; bins are dependent within races. Not certified calibration or per-horse uncertainty.')
