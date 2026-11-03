"""Test-only constructors for historical single-layer result layouts; no public CLI."""
from contextlib import redirect_stdout, redirect_stderr
import json
from pathlib import Path
import shutil
import tempfile

from analysis.provenance import ROOT, digest, envelope, utc_now, verify_inputs, write_json

from analysis.outputs import LAYOUT_VERSION, DIRECTORIES, audit_directory, publish, finish_run

def prepare_output(path):
    path = Path(path)
    if any(p.is_symlink() for p in (path, *path.parents)) or (path.exists() and (not path.is_dir() or any(path.iterdir()))):
        raise ValueError('Output directory must be new or empty')
    path.mkdir(parents=True, exist_ok=True)


def start_run(root, workflow, settings):
    prepare_output(root)
    audit = Path(root) / '.audit'
    (audit / 'logs').mkdir(parents=True)
    (audit / 'workflows').mkdir()
    record = envelope(workflow, settings, {}, [ROOT / 'run.py', *sorted((ROOT / 'analysis').rglob('*.py'))])
    record.update(output_layout_version=LAYOUT_VERSION, publications=[])
    write_json(audit / 'resolved_config.json', settings)
    write_json(audit / 'run_manifest.json', record)
    return record


def run_standalone(workflow, root, settings, execute, complete):
    """Construct a legacy layout to exercise historical readers and engine failures."""
    root = Path(root)
    record = start_run(root, workflow, settings)
    source = audit_directory(root, workflow)
    log_path = root / '.audit/logs' / (DIRECTORIES[workflow] + '.log')
    code = 1
    try:
        with log_path.open('w') as log, redirect_stdout(log), redirect_stderr(log):
            code = execute(source)
            if code == 0:
                details = complete(source)
                verify_inputs(details['inputs'])
                record.update(provenance=details, inputs=details['inputs'],
                              unavailable_analyses=[e for e in details.get('analysis_status', []) if e['status'] == 'unavailable'])
                record['publications'] = publish(root, workflow, source, details)
                verify_inputs(details['inputs'])
                record['status'] = 'complete'
                if workflow in ('data_integrity', 'sample_statistics', 'advanced_analysis', 'disease_modeling'):
                    record.update(quality_status=details['quality_status'],
                                  report_generation_status=details['report_generation_status'])
                    if details['quality_status']=='errors_found':
                        code=1
            else:
                record.update(status='failed', returncode=code)
    except Exception as error:
        code = 1
        record.update(status='failed', error_code=type(error).__name__)
    except KeyboardInterrupt:
        code = 1
        record.update(status='interrupted')
    finally:
        try:
            finish_run(root, record)
        except Exception:
            code = 1
    print(f"{record['status'].capitalize()}: {root}")
    if workflow in ('data_integrity', 'sample_statistics', 'advanced_analysis', 'disease_modeling') and record.get('quality_status'):
        print('Data quality: '+record['quality_status'])
    if record['status'] != 'complete':
        print(f'Inspect {log_path} and {root / ".audit/run_manifest.json"}')
    return code


def layer_main(name, argv):
    """Exercise an internal engine and build historical artifacts for reader tests."""
    import importlib
    from copy import copy
    from analysis.worker import completion
    module = importlib.import_module('analysis.' + name + '.runner')
    args = module.arguments(argv)
    try:
        if args.output_dir is not None and (args.output_dir.exists() or any(p.is_symlink() for p in (args.output_dir, *args.output_dir.parents))):
            return 1
        evidence = module.preflight(args)
        if args.validate_only:
            return int(evidence.get('validation_quality') == 'errors_found')
        if args.output_dir is None:
            raise ValueError('Test fixture requires explicit output')
        def execute(native):
            verify_inputs(evidence['inputs'])
            worker = copy(args)
            worker.output_dir = native
            return module.run(worker)
        return run_standalone(name, args.output_dir, evidence['resolved_settings'], execute,
                              lambda native: completion({'name': name}, native))
    except (ValueError, OSError):
        return 1
