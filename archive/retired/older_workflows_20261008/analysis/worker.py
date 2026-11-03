"""Conda-local validation/execution; stdin contains configuration, never source rows."""
import argparse
from contextlib import redirect_stdout, redirect_stderr
from dataclasses import asdict
import json
import os
from pathlib import Path
import sys
import warnings
from types import SimpleNamespace

from analysis.pipeline import workflow_args, REGISTRY
from analysis.provenance import ROOT, envelope, utc_now, verify_inputs


def kinetics_modules():
    from analysis.blast_kinetics import config
    from analysis.blast_kinetics import data_io
    from analysis.blast_kinetics import preprocessing
    from analysis.blast_kinetics import pipeline
    return config, data_io, preprocessing, pipeline


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
    code = [ROOT / 'run.py', *sorted((ROOT / 'analysis').rglob('*.py'))]
    if name == 'canonical':
        from analysis.sample_analysis.runner import selection
        from analysis.sample_analysis.adapters import prepare
        from analysis.sample_analysis.extraction import load_protocols
        from analysis.sample_analysis.policies import SETTINGS
        args = workflow_args(entry)
        cohorts, tasks, inputs = selection(args)
        settings = {'arguments': {k: v for k, v in vars(args).items() if k != 'output_dir'}, 'policies': SETTINGS}
        record = envelope(name, settings, inputs, code, ROOT / 'environments/conda-linux-64.lock')
        prepare(args.inventory, args.circall, args.donors, cohorts)
        load_protocols(args.extraction_protocols)
        if 'kinetics' in tasks:
            from analysis.sample_analysis.blood_counts import observations
            if 'circall' in cohorts:
                observations(args.blood_counts)
            if args.retrospective_blasts is not None:
                from analysis.sample_analysis.retrospective_blasts import observations as retrospective_observations
                retrospective_observations(args.retrospective_blasts, unit=args.retrospective_blast_unit)
        if 'mrd' in tasks:
            from analysis.sample_analysis import mrd, retrospective_mrd
            if 'retrospective' in cohorts:
                retrospective_mrd.observations(args.inventory, tissue=args.retrospective_mrd_tissue,
                        duplicate_policy=args.retrospective_mrd_duplicate_policy)
            if 'circall' in cohorts:
                mrd.observations(args.circall, unknown_level=args.mrd_unknown_level, negative_level=args.mrd_negative_level)
    elif name == 'cfdna_associations':
        from analysis.cfdna_associations.runner import resolve_source, CATALOG, CatalogHashMismatch
        from analysis.cfdna_associations import analyze_blast_cfdna as engine
        args = workflow_args(entry)
        path, source = resolve_source(args.inventory)
        if source['expected_sha256'] and source['sha256'] != source['expected_sha256']:
            raise CatalogHashMismatch()
        settings = {k: v for k, v in vars(args).items() if k not in ('output_dir', 'workflow')}
        settings['inventory'] = str(path)
        cohort = engine.CohortConfig(**{k: settings[k] for k in ('phase', 'blood_tissue', 'marrow_tissue', 'nucleic_acid', 'tube')})
        settings.update(cohort_config=asdict(cohort), predictors=[asdict(p) for p in engine.select_predictors(args.predictors)])
        inputs = {'inventory': path}
        if args.circall is not None:
            inputs['circall'] = args.circall
        if source['selection'] == 'catalog':
            inputs['source_catalog'] = CATALOG
        record = envelope(name, settings, inputs, code + sorted((ROOT / 'analysis/cfdna_associations').glob('*.py')),
                          ROOT / 'environments/conda-linux-64.lock')
        _, counts = engine.prepare_cohort(engine.load_dataset(path, args.sheet, cohort.patient_columns), cohort)
        if args.circall is not None:
            from analysis.cfdna_associations.diagnosis import prepare_circall
            _, circall_counts = prepare_circall(args.circall)
            counts = {'retrospective': counts, 'circall': circall_counts}
        record.update(filtering_counts=counts, source_selection=source['selection'])
    elif name == 'blast_kinetics':
        config, data_io, preprocessing, _ = kinetics_modules()
        loaded = config.load_config(entry['profile'])
        record = envelope(name, loaded.data, {'profile': loaded.path, 'measurement': loaded.data['input']['path']},
                          code + sorted((ROOT / 'analysis/blast_kinetics').glob('*.py')),
                          ROOT / 'environments/conda-linux-64.lock')
        prepared = preprocessing.prepare_data(data_io.load_input(loaded.data), loaded.data)
        record['filtering_counts'] = prepared.summary
    else:
        raise ValueError('Unknown registered workflow')
    verify_inputs(record['inputs'])
    record.update(status='complete', finished_utc=utc_now())
    return record


def completion(entry, output):
    """Revalidate artifacts independently of worker exit status, in the caller environment."""
    name = entry['name']
    from .outputs import engine_directory
    output = engine_directory(output, name)
    path = Path(output) / ('run_metadata.json' if name == 'blast_kinetics' else 'run_manifest.json')
    record = json.loads(path.read_text())
    if record.get('status') != 'complete' or record.get('workflow') != name or record.get('schema_version') != 1:
        raise ValueError('Missing or invalid completion metadata')
    for key in ('inputs', 'code_sha256', 'resolved_settings', 'packages', 'scientific_contract'):
        if not isinstance(record.get(key), dict):
            raise ValueError('Incomplete worker provenance')
    if name == 'canonical':
        from analysis import artifacts
        record['analysis_status'] = artifacts.canonical(output, workflow_args(entry, output))
    elif name == 'cfdna_associations':
        from analysis import artifacts
        predictors = [SimpleNamespace(**value) for value in record['details']['predictors']]
        record['analysis_status'] = artifacts.associations(Path(output) / 'cfdna_associations', predictors,
            [SimpleNamespace(**p) for p in record['details'].get('descriptive_predictors', [])],
            scopes=record['details'].get('scopes'))
    elif name == 'blast_kinetics':
        from analysis import artifacts
        artifacts.kinetics(output, record['resolved_settings'])
    elif name == 'disease_modeling':
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
    if name == 'blast_kinetics':
        config, _, _, pipeline = kinetics_modules()
        loaded = config.load_config(entry['profile'])
        loaded.data['output']['root'] = str(output.parent)
        loaded.data['run']['name'] = output.name
        _, destination = pipeline.execute(loaded.data, profile_path=loaded.path)
        return 0
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
    if name == 'canonical':
        from analysis.sample_analysis.runner import run
        return run(args)
    if name == 'cfdna_associations':
        from analysis.cfdna_associations.runner import run
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
