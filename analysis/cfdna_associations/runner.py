"""Isolated cfDNA workflow dispatch; scientific preparation stays in the engine."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

from analysis.provenance import digest, write_json
from analysis.outputs import prepare_output
from analysis.provenance import git_state, contract, settings_digest

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / 'analysis/cfdna_associations'
CATALOG = ROOT / 'configs/source_catalog.json'
ENVIRONMENT = 'pre_analysis'


class CatalogHashMismatch(ValueError):
    """The explicitly catalogued workbook revision no longer matches its pin."""


def arguments(argv=None):
    parser = argparse.ArgumentParser(description='Selected exploratory predictor regressions against log10(cfDNA)',
                                     allow_abbrev=False)
    parser.add_argument('--workflow', choices=['cfdna_associations'], default='cfdna_associations')
    parser.add_argument('--inventory', type=Path, help='Override the hash-pinned regression source')
    parser.add_argument('--circall', type=Path, help='Add CIRCALL diagnosis associations from this explicit inventory')
    parser.add_argument('--pool-cohorts', action=argparse.BooleanOptionalAction, default=True, help='Add descriptive pooled diagnosis views when both cohorts are available')
    parser.add_argument('--output-dir', type=Path, help='New or empty run directory')
    for name, default in [('sheet', 'Inventaire'), ('phase', 'diag'), ('blood-tissue', 'Sang'),
                          ('marrow-tissue', 'Moelle'), ('nucleic-acid', 'cfDNA'), ('tube', 'Roche')]:
        parser.add_argument('--' + name, default=default)
    parser.add_argument('--retrospective-wbc-unit', choices=['unknown', 'x10^9/L'], default='unknown',
                        help='Explicitly confirmed GB_per_L unit; required for pooled WBC (default: unknown)')
    parser.add_argument('--log-level', choices=['DEBUG', 'INFO', 'WARNING', 'ERROR'], default='INFO')
    from .analyze_blast_cfdna import add_predictor_argument, select_predictors
    add_predictor_argument(parser)
    args = parser.parse_args(argv)
    try:
        select_predictors(args.predictors)
    except ValueError as error:
        parser.error(str(error))
    args.output_dir = (args.output_dir or ROOT / 'output' / datetime.now(timezone.utc).strftime(
        'run_%Y-%m-%d_%H-%M-%S.%f_UTC')).expanduser().absolute()
    if args.circall is not None:
        args.circall = args.circall.expanduser().resolve()
        if args.phase.strip().casefold() != 'diag':
            parser.error('Two-cohort diagnosis associations require --phase diag')
    if args.inventory is not None:
        args.inventory = args.inventory.expanduser().resolve()
    return args


def resolve_source(override):
    if override is not None:
        path, expected, selection = override, None, 'explicit'
    else:
        entries = [entry for entry in json.loads(CATALOG.read_text())['sources']
                   if entry['workflow'] == 'cfdna_associations']
        if len(entries) != 1:
            raise ValueError('Source catalog must contain exactly one cfdna_associations source')
        entry = entries[0]
        path, expected, selection = (ROOT / entry['path']).resolve(), entry['sha256'], 'catalog'
    if not path.is_file():
        raise ValueError('Association input is missing; supply --inventory PATH or restore the catalog workbook')
    source = {'path': str(path), 'sha256': digest(path), 'expected_sha256': expected, 'selection': selection}
    return path, source


def run(args):
    try:
        prepare_output(args.output_dir)
    except ValueError as error:
        print(f'Error: {error}', file=sys.stderr)
        return 1
    output = args.output_dir
    (output / 'logs').mkdir()
    manifest = {'workflow': 'cfdna_associations', 'status': 'running',
                'started_utc': datetime.now(timezone.utc).isoformat(), 'arguments': vars(args),
                'environment_name': ENVIRONMENT, 'inputs': {}}
    manifest.update(schema_version=1, scientific_contract=contract('cfdna_associations'), **git_state())
    manifest_path = output / 'run_manifest.json'
    write_json(manifest_path, manifest)
    try:
        code = [ROOT / 'run.py', *sorted((ROOT / 'analysis').rglob('*.py')), *sorted(WORKFLOW.glob('*.py'))]
        manifest['code_sha256'] = {str(path.relative_to(ROOT)): digest(path) for path in code}
        manifest['import_provenance'] = json.loads((WORKFLOW / 'import_provenance.json').read_text())
        manifest['environment_lock_sha256'] = digest(ROOT / 'environments/conda-linux-64.lock')
        path, source = resolve_source(args.inventory)
        manifest['inputs']['inventory'] = source
        if source['selection'] == 'catalog':
            manifest['source_catalog_sha256'] = digest(CATALOG)
        write_json(manifest_path, manifest)
        if source['expected_sha256'] and source['sha256'] != source['expected_sha256']:
            raise CatalogHashMismatch('Catalog source hash mismatch; restore the pinned workbook or explicitly select --inventory PATH')
        settings = {name: getattr(args, name) for name in (
            'sheet', 'phase', 'blood_tissue', 'marrow_tissue', 'nucleic_acid', 'tube', 'log_level', 'predictors', 'spearman_sensitivity', 'retrospective_wbc_unit')}
        settings['inventory'] = str(path)
        settings['circall'] = str(args.circall) if args.circall is not None else None
        settings['pool_cohorts'] = args.pool_cohorts
        if args.circall is not None:
            manifest['inputs']['circall'] = {'path': str(args.circall), 'sha256': digest(args.circall)}
        manifest['settings'] = settings
        manifest['resolved_settings'] = settings
        manifest['resolved_settings_sha256'] = settings_digest(settings)
        settings_path = output / 'resolved_settings.json'
        write_json(settings_path, settings)
        command = ['conda', 'run', '--no-capture-output', '-n', ENVIRONMENT, 'python', '-m',
                   'analysis.cfdna_associations.worker', '--settings', str(settings_path)]
        manifest['command'] = command
        write_json(manifest_path, manifest)
        environment = os.environ.copy()
        environment.update(MPLBACKEND='Agg', MPLCONFIGDIR=str(output / '.cache/matplotlib'),
                           XDG_CACHE_HOME=str(output / '.cache'), PYTHONDONTWRITEBYTECODE='1')
        # Child logs contain only validated metadata and aggregate counts. Conda errors stay local.
        with (output / 'logs/workflow.log').open('w') as log:
            result = subprocess.run(command, cwd=ROOT, env=environment, stdout=log,
                                    stderr=subprocess.STDOUT, check=False)
        details_path = output / 'workflow_details.json'
        if details_path.is_file():
            manifest['details'] = json.loads(details_path.read_text())
        if result.returncode:
            if not details_path.is_file():
                raise ValueError('Cannot start the association worker; verify conda and the pre_analysis environment. '
                                 'Create it with conda create -n pre_analysis --file environments/conda-linux-64.lock; '
                                 'see logs/workflow.log')
            raise ValueError(manifest['details'].get('error', 'Association worker failed'))
        if not details_path.is_file() or manifest['details'].get('status') != 'complete':
            raise ValueError('Association worker did not produce completion metadata')
        from analysis.artifacts import associations
        predictors = [SimpleNamespace(**value) for value in manifest['details']['predictors']]
        manifest['analysis_status'] = associations(output / 'cfdna_associations', predictors,
            [SimpleNamespace(**p) for p in manifest['details'].get('descriptive_predictors', [])],
            scopes=manifest['details'].get('scopes'))
        manifest.update({key: manifest['details'][key] for key in ('packages', 'python', 'executable')})
        if any(digest(Path(item['path'])) != item['sha256'] for item in manifest['inputs'].values()):
            raise ValueError('Input changed during the run; results are not validated')
        manifest['status'] = 'complete'
    except FileNotFoundError:
        manifest.update(status='failed', error='Required file or conda executable missing; verify the installation and workflow files')
    except ValueError as error:
        manifest.update(status='failed', error=str(error))
    except Exception as error:
        manifest.update(status='failed', error=f'{type(error).__name__}: workflow infrastructure failed')
    finally:
        manifest['finished_utc'] = datetime.now(timezone.utc).isoformat()
        write_json(manifest_path, manifest)
    if manifest['status'] == 'failed':
        print(f"Error: {manifest['error']}", file=sys.stderr)
    print(f"{manifest['status'].capitalize()}: {output}")
    return 0 if manifest['status'] == 'complete' else 1
