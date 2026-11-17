import json
from scripts.queue_article_component_v2 import quality_gate


def save(path,data):path.parent.mkdir(parents=True,exist_ok=True);path.write_text(json.dumps(data))


def reference_run(tmp_path):
    policy=dict(minimum_reference_accuracy=.9,critical_false_current_recommendations=0,maximum_schema_failures=0,minimum_correct_january_opposed_references=2)
    rows=[dict(runner_id='a',date='2026-02-01',horse='SHUTTERWOOD (FR)',expected='unknown',correct=True,reference_group='existing_regression'),
          dict(runner_id='b',date='2026-02-01',horse='BE TRUE (FR)',expected='unknown',correct=True,reference_group='existing_regression'),
          dict(runner_id='c',date='2026-01-04',horse='OTTO',expected='opposed',correct=True,reference_group='additional_source_review'),
          dict(runner_id='d',date='2026-01-04',horse='FARNESIO (IRE)',expected='opposed',correct=True,reference_group='additional_source_review')]
    save(tmp_path/'manifest.json',dict(quality_gate=policy))
    save(tmp_path/'extraction_summary.json',dict(reference_rows=rows,reference_scored=4,reference_expected=4,reference_accuracy=1.,statuses={'complete':4}))
    tasks=[dict(race={'date':r['date']},runner={'runner_id':r['runner_id']}) for r in rows]
    save(tmp_path/'tasks.json',tasks)
    for r in rows:save(tmp_path/'runners'/(r['runner_id']+'.json'),dict(status='complete',assessment=r['expected']))
    return tmp_path


def test_gate_requires_correct_critical_roles_and_january_opposition(tmp_path):
    out=reference_run(tmp_path);report=quality_gate(out)
    assert report['passed'] and report['training_assessments']['opposed']==2
    summary=json.loads((out/'extraction_summary.json').read_text())
    summary['reference_rows'][0]['correct']=False
    # Even an externally supplied high aggregate accuracy must not mask a critical error.
    save(out/'extraction_summary.json',summary)
    report=quality_gate(out)
    assert not report['passed'] and not report['checks']['no_critical_false_recommendations']


def test_gate_rejects_failed_inference_and_incomplete_reference_coverage(tmp_path):
    out=reference_run(tmp_path);summary=json.loads((out/'extraction_summary.json').read_text())
    summary['statuses']['failed']=1;summary['reference_scored']=3
    save(out/'extraction_summary.json',summary);report=quality_gate(out)
    assert not report['passed']
    assert not report['checks']['no_failed_extractions'] and not report['checks']['all_references_scored']
