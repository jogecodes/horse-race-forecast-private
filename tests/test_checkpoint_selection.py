"""Explicit pilot selection must not cross the frozen split boundary."""
import json
from pathlib import Path
import pytest
from horse_racing.engine.run import run_benchmark

BUNDLE = Path(__file__).resolve().parents[1] / 'benchmarks/h1_2026_v2'

@pytest.mark.parametrize('selection', ['validation', 'duplicate', 'empty'])
def test_explicit_selection_rejects_invalid_ids_before_creating_run(tmp_path, selection):
    tasks = [json.loads(line) for line in (BUNDLE / 'diagnostic/tasks.jsonl').read_text().splitlines()]
    development = next(t['race_id'] for t in tasks if t['split'] == 'development')
    validation = next(t['race_id'] for t in tasks if t['split'] == 'validation')
    ids = {'validation': [validation], 'duplicate': [development, development], 'empty': []}[selection]
    out = tmp_path / 'rejected'
    with pytest.raises(ValueError, match='outside selected split|nonempty and unique'):
        run_benchmark(BUNDLE, out, split='development', track='publisher-documented', race_ids=ids)
    assert not out.exists()
