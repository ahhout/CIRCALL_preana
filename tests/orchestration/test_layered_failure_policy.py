"""Run-level failures retain independent layer work and truthful final status."""
import json
import subprocess
from unittest.mock import patch

import pytest

from analysis import pipeline
from analysis.provenance import digest, ROOT


@pytest.mark.parametrize('failure', ['worker', 'quality', 'source_change', 'interruption'])
def test_layered_failure_policy(tmp_path, failure):
    source = tmp_path/'synthetic.txt'
    source.write_text('synthetic source')
    inputs = {'source': {'path': str(source), 'sha256': digest(source)}}
    evidence = {name: {'inputs': inputs} for name in pipeline.LAYERED_WORKFLOWS}
    output = tmp_path/'run'
    calls = []

    def worker(command, entry, destination, log):
        calls.append(entry['name'])
        if len(calls) == 1:
            if failure == 'interruption':
                raise KeyboardInterrupt
            if failure == 'source_change':
                source.write_text('changed synthetic source')
            if failure == 'worker':
                return subprocess.CompletedProcess(command, 1)
        return subprocess.CompletedProcess(command, 0)

    def completion(entry, destination):
        return dict(inputs=inputs, quality_status='errors_found' if failure == 'quality' and len(calls) == 1 else 'no_issues_detected',
                    report_generation_status='complete')

    with patch.object(pipeline, 'preflight', return_value=evidence), \
         patch.object(pipeline, 'run_worker', side_effect=worker), \
         patch('analysis.worker.completion', side_effect=completion), \
         patch.object(pipeline, 'publish', return_value=[]):
        assert pipeline.main(['--config', str(ROOT/'configs/pipeline_layers.json'), '--output-dir', str(output)]) == 1
    manifest = json.loads((output/'.audit/run_manifest.json').read_text())
    assert manifest['status'] == 'failed'
    assert manifest['failure_policy']['workflow_failure'] == 'continue_independent_workflows'
    states = [w['status'] for w in manifest['workflows']]
    if failure == 'worker':
        assert calls == list(pipeline.LAYERED_WORKFLOWS)
        assert states == ['failed', 'complete', 'complete', 'complete']
        assert (output/'.audit/logs/data_integrity.log').exists()
    elif failure == 'quality':
        assert calls == list(pipeline.LAYERED_WORKFLOWS)
        assert states == ['complete'] * 4
        assert manifest['workflows'][0]['quality_status'] == 'errors_found'
    elif failure == 'source_change':
        assert len(calls) == 1 and states == ['failed'] * 4
    else:
        assert len(calls) == 1 and states == ['interrupted', 'not_run', 'not_run', 'not_run']
    assert manifest['started_utc'] and manifest['finished_utc']


def test_layered_default_destination_and_preflight_infrastructure_failure(tmp_path):
    args = pipeline.arguments(['--config', str(ROOT/'configs/pipeline_layers.json'), '--validate-only'])
    with patch.object(pipeline, 'preflight', return_value={}):
        assert pipeline.run(args) == 0
    assert args.output_dir.parent == ROOT/'outputs/layered'
    assert not args.output_dir.exists()
    target = tmp_path/'failed_preflight'
    with patch.object(pipeline, 'preflight', side_effect=ValueError('synthetic infrastructure failure')), \
         patch.object(pipeline, 'run_worker') as worker:
        assert pipeline.main(['--config', str(ROOT/'configs/pipeline_layers.json'), '--output-dir', str(target)]) == 1
    worker.assert_not_called()
    assert not target.exists()
