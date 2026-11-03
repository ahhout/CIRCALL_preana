"""Sequential, isolated orchestration of the existing scientific engines."""
import argparse
from contextlib import redirect_stderr
from datetime import datetime, timezone
import io
import json
import math
import os
import signal
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

from analysis.configuration import unique_object as _unique_object
from analysis.layer_configuration import read_profile, expand_layers, select_layers
from analysis.provenance import ROOT, artifact_index, digest, envelope, utc_now, verify_inputs, write_json

from .outputs import DIRECTORIES, audit_directory, publish, finish_run, LAYOUT_VERSION, publication_directory

REGISTRY = {'canonical': 'pre_analysis', 'cfdna_associations': 'pre_analysis',
            'blast_kinetics': 'pre_analysis', 'data_integrity': 'pre_analysis', 'sample_statistics': 'pre_analysis',
            'advanced_analysis': 'pre_analysis', 'disease_modeling': 'pre_analysis'}
LAYERED_WORKFLOWS = ('data_integrity', 'sample_statistics', 'advanced_analysis', 'disease_modeling')
PATH_OPTIONS = {'inventory', 'circall', 'donors', 'blood-counts', 'extraction-protocols', 'retrospective-blasts', 'rules', 'definitions'}
STATISTICS = {'pdf-output', 'inventory', 'circall', 'donors', 'cohort', 'include-controls', 'rules', 'definitions', 'assessment-time'}
ADVANCED = {'comparison-switches', 'pdf-output', 'inventory', 'circall', 'donors', 'cohort', 'include-controls', 'rules', 'definitions',
            'predictors', 'pool-cohorts', 'spearman-sensitivity', 'retrospective-wbc-unit', 'sample-selection-seed'}
DISEASE = {'pdf-output', 'inventory', 'circall', 'donors', 'blood-counts', 'retrospective-blasts', 'cohort', 'analysis',
           'include-controls', 'pool-mrd', 'rules', 'definitions', 'blood-count-unit', 'retrospective-blast-unit',
           'baseline-day-max', 'baseline-selection', 'overlay-max-day', 'kinetics-y-scale',
           'mrd-unknown-level', 'mrd-negative-level', 'mrd-positive-nq-level', 'retrospective-mrd-duplicate-policy', 'jitter-seed'}
INTEGRITY = {'inventory', 'circall', 'donors', 'cohort', 'include-controls', 'rules'}
CANONICAL = {'inventory', 'circall', 'donors', 'blood-counts', 'extraction-protocols', 'cohort', 'analysis',
             'mixed-random-slope-sensitivity', 'mixed-outlier-drop-n', 'pool-cohorts', 'pooled-timepoints',
             'pool-mrd', 'mrd-unknown-level', 'mrd-negative-level', 'mrd-positive-nq-level', 'retrospective-mrd-tissue', 'retrospective-mrd-duplicate-policy', 'baseline-day-max', 'baseline-selection',
             'overlay-max-day', 'kinetics-y-scale', 'plot-diagnosis-as-d1', 'retrospective-blasts', 'retrospective-blast-unit',
             'trend-bootstrap-resamples', 'trend-bootstrap-seed', 'trend-bootstrap-method',
             'longitudinal-followups', 'longitudinal-descriptive-visits'}
ASSOCIATIONS = {'inventory', 'sheet', 'phase', 'blood-tissue', 'marrow-tissue', 'nucleic-acid', 'tube', 'log-level', 'predictors', 'circall', 'pool-cohorts', 'spearman-sensitivity', 'retrospective-wbc-unit'}
BOOLEANS = {'pdf-output', 'spearman-sensitivity', 'pool-mrd', 'pool-cohorts', 'plot-diagnosis-as-d1', 'mixed-random-slope-sensitivity', 'include-controls'}
INTEGERS = {'mixed-outlier-drop-n', 'baseline-day-max', 'overlay-max-day', 'trend-bootstrap-resamples', 'trend-bootstrap-seed', 'jitter-seed', 'sample-selection-seed'}
FLOATS = {'mrd-unknown-level', 'mrd-negative-level', 'mrd-positive-nq-level'}


def option_argv(options):
    argv = []
    for key, value in options.items():
        if key == 'comparison-switches':
            if not isinstance(value, dict):
                raise ValueError('comparison-switches must be an object')
            argv.extend(['--comparison-switches', json.dumps(value, allow_nan=False)])
        elif key in BOOLEANS:
            if type(value) is not bool:
                raise ValueError(f'{key} must be Boolean')
            if key == 'mixed-random-slope-sensitivity':
                if value:
                    argv.append('--' + key)
            else:
                argv.append(('--' if value else '--no-') + key)
        elif key in ('pooled-timepoints', 'longitudinal-followups', 'longitudinal-descriptive-visits', 'predictors'):
            if not isinstance(value, list) or (not value and key != 'longitudinal-descriptive-visits') or not all(isinstance(v, str) for v in value) or len(set(value)) != len(value):
                raise ValueError(f'{key} must contain unique labels; only descriptive visits may be empty')
            argv.extend(['--' + key, *value])
        else:
            if key in INTEGERS:
                valid = type(value) is int
            elif key in FLOATS:
                valid = type(value) in (int, float) and math.isfinite(value)
            else:
                valid = isinstance(value, str) and bool(value.strip())
            if not valid:
                raise ValueError(f'Invalid type for option {key}')
            argv.extend(['--' + key, str(value)])
    return argv


def workflow_args(entry, output=None):
    from analysis.cli import arguments
    argv = ['--workflow', entry['name'], *option_argv(entry['options'])]
    if output is not None:
        argv.extend(['--output-dir', str(output)])
    try:
        with redirect_stderr(io.StringIO()):
            return arguments(argv)
    except SystemExit:
        raise ValueError(f"Invalid or incompatible {entry['name']} options; consult --help") from None


def load_config(path):
    config, path, selections, _ = read_profile(path)
    if config.get('schema_version') == 2:
        config = expand_layers(config, {
            'data_integrity': INTEGRITY, 'sample_statistics': STATISTICS,
            'advanced_analysis': ADVANCED, 'disease_modeling': DISEASE})
    if (not isinstance(config, dict) or not {'schema_version', 'workflows'}.issubset(config)
            or set(config) - {'schema_version', 'workflows', 'output-dir', 'validate-only'}
            or type(config['schema_version']) is not int or config['schema_version'] != 1):
        raise ValueError('Pipeline configuration requires schema_version 1 and workflows; optional keys: output-dir, validate-only')
    if 'output-dir' in config:
        value = config['output-dir']
        if not isinstance(value, str) or not value.strip():
            raise ValueError('output-dir must be a nonempty path')
        config['output-dir'] = str((path.parent / Path(value).expanduser()).absolute())
    if 'validate-only' in config and type(config['validate-only']) is not bool:
        raise ValueError('validate-only must be Boolean')
    if not isinstance(config['workflows'], list) or not config['workflows']:
        raise ValueError('Select at least one workflow')
    seen = set()
    for entry in config['workflows']:
        if not isinstance(entry, dict) or not isinstance(entry.get('name'), str) or entry['name'] not in REGISTRY:
            raise ValueError('Unknown registered workflow')
        name = entry['name']
        if name in seen:
            raise ValueError('A workflow may appear only once per run')
        seen.add(name)
        if name == 'blast_kinetics':
            if set(entry) != {'name', 'profile'} or not isinstance(entry['profile'], str) or not entry['profile'].strip():
                raise ValueError('blast_kinetics requires name and profile only')
            entry['profile'] = str((path.parent / Path(entry['profile']).expanduser()).resolve())
            if not Path(entry['profile']).is_file():
                raise ValueError('Kinetics profile file is missing')
        else:
            if set(entry) != {'name', 'options'} or not isinstance(entry['options'], dict):
                raise ValueError(f'{name} requires name and options only')
            allowed = {'canonical': CANONICAL, 'cfdna_associations': ASSOCIATIONS, 'data_integrity': INTEGRITY, 'sample_statistics': STATISTICS,
                       'advanced_analysis': ADVANCED, 'disease_modeling': DISEASE}[name]
            if not set(entry['options']).issubset(allowed):
                raise ValueError(f'Unknown {name} options')
            if name == 'canonical' and 'circall' not in entry['options']:
                raise ValueError('canonical requires an explicitly configured circall workbook')
            for key in entry['options'].keys() & PATH_OPTIONS:
                value = entry['options'][key]
                if not isinstance(value, str) or not value.strip():
                    raise ValueError(f'{key} must be a nonempty path')
                entry['options'][key] = str((path.parent / Path(value).expanduser()).resolve())
            workflow_args(entry)
    for selection in selections:
        config = select_layers(config, selection)
    return config


def arguments(argv=None):
    parser = argparse.ArgumentParser(description='Run the layered pipeline from its master configuration', allow_abbrev=False)
    parser.add_argument('--config', default=ROOT / 'configs/pipeline_layers.json', type=Path,
                        help='Pipeline JSON (default: repository configs/pipeline_layers.json; compatibility: configs/pipeline_all.json)')
    parser.add_argument('--layers', nargs='+', type=int, choices=(1, 2, 3, 4),
                        help='Run only these enabled layers from the selected profile')
    parser.add_argument('--output-dir', type=Path, help='Fresh destination; existing directories are refused')
    parser.add_argument('--pdf-output', action=argparse.BooleanOptionalAction, default=None,
                        help='Override PDF figure output for Layers 2–4; PNGs are always saved')
    parser.add_argument('--validate-only', action=argparse.BooleanOptionalAction, default=None,
                        help='Validate all sources, headers and environments without publishing results')
    args = parser.parse_args(argv)
    args.config = args.config.expanduser().resolve()
    if args.output_dir is not None:
        args.output_dir = args.output_dir.expanduser().absolute()
    return args


def worker_command(name, preflight=False, output=None):
    command = ['conda', 'run', '--no-capture-output', '-n', REGISTRY[name], 'python', '-B',
               '-m', 'analysis.worker', '--workflow', name]
    if preflight:
        command.append('--preflight')
    else:
        command.extend(['--output-dir', str(output)])
    return command


def worker_environment(output=None):
    environment = os.environ.copy()
    environment.update(PYTHONDONTWRITEBYTECODE='1', MPLBACKEND='Agg')
    if output is not None:
        cache = output.parent / '.cache' / output.name
        environment.update(MPLCONFIGDIR=str(cache / 'matplotlib'), XDG_CACHE_HOME=str(cache))
    return environment


def run_worker(command, entry, destination, log):
    """Terminate the worker process group on interruption, preserving partial results."""
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=log, stderr=subprocess.STDOUT,
                               text=True, cwd=ROOT, env=worker_environment(destination), start_new_session=True)
    try:
        process.communicate(input=json.dumps(entry))
    except BaseException:
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
        raise
    return subprocess.CompletedProcess(command, process.returncode)


def verify_preflight(record):
    verify_inputs(record['inputs'])
    if record.get('workflow') == 'disease_modeling':
        from analysis.disease_modeling.runner import verify_source_states
        verify_source_states(record['source_states'])
    if record.get('workflow') in ('data_integrity', 'sample_statistics', 'advanced_analysis'):
        from analysis.source_state import verify_source_states
        verify_source_states(record['source_states'])


def preflight(config, output):
    if output.exists() or any(path.is_symlink() for path in (output, *output.parents)):
        raise ValueError('Integrated output destination already exists; choose a fresh path')
    records, errors = {}, []
    for entry in config['workflows']:
        name = entry['name']
        try:
            result = subprocess.run(worker_command(name, preflight=True), input=json.dumps(entry),
                                    cwd=ROOT, env=worker_environment(), capture_output=True, text=True, check=False)
            if result.returncode:
                # Never relay unvalidated library/Conda output to root metadata.
                try:
                    details = json.loads(result.stdout)
                    reason = details.get('error_code', 'worker_failed')
                except ValueError:
                    reason = 'worker_unavailable'
                if reason == 'CatalogHashMismatch':
                    errors.append(f'{name}: workbook hash differs from configs/source_catalog.json; review the workbook revision and update its pin, or explicitly select --inventory PATH')
                else:
                    errors.append(f'{name}: {reason}; verify environment, configuration, sources and headers')
                continue
            record = json.loads(result.stdout)
            if record.get('status') != 'complete' or record.get('workflow') != name or record.get('schema_version') != 1 or record.get('environment_name') != REGISTRY[name] or not isinstance(record.get('inputs'), dict):
                raise ValueError('invalid_preflight_metadata')
            verify_preflight(record)
            records[name] = record
        except OSError:
            errors.append(f'{name}: conda or worker could not be launched')
        except (ValueError, KeyError, TypeError):
            errors.append(f'{name}: invalid preflight metadata or changed input')
    if errors:
        raise ValueError('Preflight failed: ' + '; '.join(errors))
    return records


def run(args):
    try:
        configuration_paths = read_profile(args.config)[3]
        configuration_source = {('configuration' if i == 0 else f'configuration_{i}'):
                                {'path': str(path), 'sha256': digest(path)}
                                for i, path in enumerate(configuration_paths)}
        config = load_config(args.config)
        if getattr(args, 'layers', None) is not None:
            config = select_layers(config, args.layers)
        if getattr(args, 'pdf_output', None) is not None:
            if any(e['name'] not in LAYERED_WORKFLOWS for e in config['workflows']):
                raise ValueError('--pdf-output/--no-pdf-output supports layered workflows only')
            for entry in config['workflows']:
                if entry['name'] != 'data_integrity':
                    entry['options']['pdf-output'] = args.pdf_output
        layered = len(config['workflows']) > 1 and all(e['name'] in LAYERED_WORKFLOWS for e in config['workflows'])
        if args.output_dir is None:
            if config.get('output-dir'):
                args.output_dir = Path(config['output-dir'])
            elif layered:
                args.output_dir = ROOT / 'outputs/layered' / datetime.now(timezone.utc).strftime('run_%Y%m%dT%H%M%S%fZ')
            elif [entry['name'] for entry in config['workflows']] == ['disease_modeling']:
                from analysis.disease_modeling.runner import default_output_dir
                args.output_dir = default_output_dir()
            elif [entry['name'] for entry in config['workflows']] == ['advanced_analysis']:
                from analysis.advanced_analysis.runner import default_output_dir
                args.output_dir = default_output_dir()
            elif [entry['name'] for entry in config['workflows']] == ['sample_statistics']:
                from analysis.sample_statistics.runner import default_output_dir
                args.output_dir = default_output_dir()
            elif [entry['name'] for entry in config['workflows']] == ['data_integrity']:
                from analysis.data_integrity.runner import default_output_dir
                args.output_dir = default_output_dir()
            else:
                args.output_dir = ROOT / 'output' / datetime.now(timezone.utc).strftime('run_%Y-%m-%d_%H-%M-%S.%f_UTC')
        if args.validate_only is None:
            args.validate_only = config.get('validate-only', False)
        evidence = preflight(config, args.output_dir)
        verify_inputs(configuration_source)
    except (OSError, ValueError) as error:
        print(f'Error: {error}', file=sys.stderr)
        return 1
    if args.validate_only:
        if any(r.get('validation_quality') == 'errors_found' for r in evidence.values()):
            print('Preflight found blocked disease cohorts; full execution can publish independent and blocked reports')
            return 1
        print('Preflight complete: ' + ', '.join(evidence))
        return 0
    output = args.output_dir
    try:
        output.mkdir(parents=True, exist_ok=False)
    except OSError:
        print('Error: cannot reserve a fresh output directory', file=sys.stderr)
        return 1
    (output / '.audit/logs').mkdir(parents=True)
    (output / '.audit/workflows').mkdir()
    code = [ROOT / 'run.py', *sorted((ROOT / 'analysis').rglob('*.py'))]
    if layered:
        code.append(ROOT / 'run_all_layers.sh')
    manifest = envelope('pipeline', config, {key: value['path'] for key, value in configuration_source.items()}, code)
    if layered:
        manifest.update(run_id=uuid4().hex, pipeline_kind='layered', failure_policy={
            'preflight_infrastructure': 'abort_before_execution',
            'workflow_failure': 'continue_independent_workflows',
            'cohort_quality': 'preserve_gates_and_publish_independent_reports',
            'source_change': 'invalidate_affected_workflows',
            'interruption': 'stop_and_mark_remaining_not_run',
        })
    manifest['workflows'] = [{'name': e['name'], 'environment_name': REGISTRY[e['name']], 'status': 'pending',
                              'preflight': evidence[e['name']]} for e in config['workflows']]
    manifest.update(output_layout_version=LAYOUT_VERSION, publications=[])
    path = output / '.audit/run_manifest.json'
    write_json(output / '.audit/resolved_config.json', config)
    write_json(path, manifest)
    interrupted = False
    try:
        for entry, state in zip(config['workflows'], manifest['workflows']):
            name = entry['name']
            destination = audit_directory(output, name)
            state.update(status='running', started_utc=utc_now(), output_dir=str(publication_directory(output,name).relative_to(output)), audit_dir=str(destination.relative_to(output)),
                         command=worker_command(name, output=destination))
            write_json(path, manifest)
            label = f'Layer {LAYERED_WORKFLOWS.index(name) + 1} ({name})' if layered else name
            print(f'Running {label}', flush=True)
            try:
                verify_inputs(manifest['inputs'])
                verify_preflight(state['preflight'])
                with (output / '.audit/logs' / f'{name}.log').open('w') as log:
                    result = run_worker(state['command'], entry, destination, log)
                state['returncode'] = result.returncode
                if result.returncode:
                    raise ValueError('worker_failed')
                from analysis.worker import completion
                details = completion(entry, destination)
                verify_inputs(details['inputs'])
                verify_preflight(state['preflight'])
                manifest['publications'].extend(publish(output, name, destination, details))
                verify_inputs(details['inputs'])
                state.update(status='complete', provenance=details,
                             unavailable_analyses=[e for e in details.get('analysis_status', []) if e['status'] == 'unavailable'])
                if name in ('data_integrity', 'sample_statistics', 'advanced_analysis', 'disease_modeling'):
                    state.update(quality_status=details['quality_status'],
                                 report_generation_status=details['report_generation_status'])
            except Exception as error:
                state.update(status='failed', error_code=type(error).__name__,
                             error='Workflow failed or artifacts invalid; see its local log and manifest')
            finally:
                state['finished_utc'] = utc_now()
                write_json(path, manifest)
    except KeyboardInterrupt:
        interrupted = True
        for state in manifest['workflows']:
            if state['status'] in ('pending', 'running'):
                state.update(status='interrupted' if state['status'] == 'running' else 'not_run', finished_utc=utc_now())
    finally:
        for state in manifest['workflows']:
            try:
                verify_preflight(state['preflight'])
            except ValueError:
                state.update(status='failed', error='An input changed during the integrated run')
        manifest.update(status='failed' if interrupted or any(s['status'] != 'complete' or s.get('quality_status') == 'errors_found' for s in manifest['workflows']) else 'complete',
                        finished_utc=utc_now())
        try:
            verify_inputs(manifest['inputs'])
        except ValueError:
            manifest.update(status='failed', error='Configuration changed during the run')
        write_json(path, manifest)
        try:
            finish_run(output, manifest)
        except (ValueError, OSError):
            manifest.update(status='failed', error='Artifact indexing failed; inspect local output ownership')
            write_json(path, manifest)
    print(f"{manifest['status'].capitalize()}: {output}", flush=True)
    if manifest['status'] != 'complete':
        print(f"Inspect {output / '.audit/logs'} and {path}", flush=True)
    return 0 if manifest['status'] == 'complete' else 1


def main(argv=None):
    previous = signal.getsignal(signal.SIGTERM)
    def interrupt(signum, frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM, interrupt)
    try:
        return run(arguments(argv))
    finally:
        signal.signal(signal.SIGTERM, previous)
