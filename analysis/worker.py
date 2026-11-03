"""Conda-local validation/execution; stdin contains configuration, never source rows."""
import argparse
from contextlib import redirect_stdout, redirect_stderr
import json
import os
from pathlib import Path
import sys
import warnings

from analysis.pipeline import workflow_args, REGISTRY


def validate_entry(entry):
    name = entry['name']
    if name == 'disease_modeling':
        from analysis.disease_modeling.runner import preflight
        return preflight(workflow_args(entry))
    if name == 'advanced_analysis':
        from analysis.advanced_analysis.runner import preflight
        return preflight(workflow_args(entry))
    if name == 'sample_statistics':
        from analysis.sample_statistics.runner import preflight
        return preflight(workflow_args(entry))
    if name == 'data_integrity':
        from analysis.data_integrity.runner import preflight
        return preflight(workflow_args(entry))
    raise ValueError('Unknown or retired workflow')


def completion(entry, output):
    """Revalidate artifacts independently of worker exit status, in the caller environment."""
    name = entry['name']
    from .outputs import engine_directory
    output = engine_directory(output, name)
    path = Path(output) / 'run_manifest.json'
    record = json.loads(path.read_text())
    if record.get('status') != 'complete' or record.get('workflow') != name or record.get('schema_version') != 1:
        raise ValueError('Missing or invalid completion metadata')
    for key in ('inputs', 'code_sha256', 'resolved_settings', 'packages', 'scientific_contract'):
        if not isinstance(record.get(key), dict):
            raise ValueError('Incomplete worker provenance')
    if name == 'disease_modeling':
        from analysis.disease_modeling.runner import validate_results
        validate_results(output, record)
    elif name == 'advanced_analysis':
        from analysis.advanced_analysis.runner import validate_results
        validate_results(output, record)
    elif name == 'sample_statistics':
        from analysis.sample_statistics.runner import validate_results
        validate_results(output,record)
    elif name == 'data_integrity':
        from analysis.data_integrity.runner import validate_results
        validate_results(output,record)
    else:
        raise ValueError('Unknown registered workflow')
    return record


def execute(entry, output):
    name = entry['name']
    args = workflow_args(entry, output)
    if name == 'disease_modeling':
        from analysis.disease_modeling.runner import run
        return run(args)
    if name == 'advanced_analysis':
        from analysis.advanced_analysis.runner import run
        return run(args)
    if name == 'sample_statistics':
        from analysis.sample_statistics.runner import run
        return run(args)
    if name == 'data_integrity':
        from analysis.data_integrity.runner import run
        return run(args)
    raise ValueError('Unknown registered workflow')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--workflow', required=True, choices=REGISTRY)
    parser.add_argument('--preflight', action='store_true')
    parser.add_argument('--output-dir', type=Path)
    args = parser.parse_args(argv)
    if args.preflight == (args.output_dir is not None):
        parser.error('Select preflight or an output destination')
    try:
        entry = json.load(sys.stdin)
        if entry.get('name') != args.workflow:
            raise ValueError('workflow_mismatch')
        if args.preflight:
            with open(os.devnull, 'w') as quiet, redirect_stdout(quiet), redirect_stderr(quiet), warnings.catch_warnings():
                warnings.simplefilter('ignore')
                record = validate_entry(entry)
            print(json.dumps(record, default=str, allow_nan=False))
            return 0
        with open(os.devnull, 'w') as quiet, redirect_stdout(quiet), redirect_stderr(quiet), warnings.catch_warnings():
            warnings.simplefilter('ignore')
            result = execute(entry, args.output_dir.resolve())
        print('Workflow execution complete' if result == 0 else 'Workflow execution failed; see local manifest')
        return result
    except Exception as error:
        # Exception text can contain a real identifier, including library errors.
        if args.preflight:
            print(json.dumps({'status': 'failed', 'workflow': args.workflow, 'error_code': type(error).__name__}))
        else:
            print(f'Workflow infrastructure failed ({type(error).__name__}); raw values omitted', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
