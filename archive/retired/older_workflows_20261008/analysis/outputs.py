"""Clean result publication over retained, unmodified engine output layouts."""
from contextlib import redirect_stdout, redirect_stderr
import json
from pathlib import Path
import shutil
import tempfile

from .provenance import ROOT, digest, envelope, utc_now, verify_inputs, write_json

LAYOUT_VERSION = 2
DIRECTORIES = {'canonical': 'sample_analysis', 'cfdna_associations': 'cfdna_associations',
               'blast_kinetics': 'blast_kinetics', 'data_integrity': '01_data_integrity', 'sample_statistics': '02_sample_statistics',
               'advanced_analysis': '03_advanced_analysis', 'disease_modeling': '04_disease_modeling'}


def prepare_output(path):
    path = Path(path)
    if any(p.is_symlink() for p in (path, *path.parents)) or (path.exists() and (not path.is_dir() or any(path.iterdir()))):
        raise ValueError('Output directory must be new or empty')
    path.mkdir(parents=True, exist_ok=True)


def audit_directory(root, workflow):
    return Path(root) / '.audit' / 'workflows' / DIRECTORIES[workflow]


def engine_directory(path, workflow):
    """Accept a new run root, visible workflow directory, or historical engine root."""
    path = Path(path)
    direct = audit_directory(path, workflow)
    if direct.is_dir():
        return direct
    sibling = audit_directory(path.parent, workflow)
    if path.name == DIRECTORIES[workflow] and sibling.is_dir():
        return sibling
    return path


def manifest_path(path):
    path = Path(path)
    return path / '.audit/run_manifest.json' if (path / '.audit/run_manifest.json').is_file() else path / 'run_manifest.json'


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


# Reviewed presentation contract. Unlisted engine artifacts remain audit-only.
SAMPLE_TABLES = {'kinetics/mrd/pooled_mrd_summary.csv', 'kinetics/mrd/pooled_mrd_settings.json', 'kinetics/mrd/retrospective_mrd_summary.csv', 'inventory/missing_samples_list.csv', 'yield/blood_pellet_summary.csv',
                 'yield/cohort_comparison.csv', 'kinetics/circall_blood_count_summary.csv', 'kinetics/blood_count_summary.csv'}
SAMPLE_FIGURES = {
    'longitudinal/yield_wbc_panels.png', 'longitudinal/yield_wbc_panels.pdf',
    'kinetics/mrd/pooled_mrd_trajectories.png', 'kinetics/mrd/pooled_mrd_status_stacked.png',
    'kinetics/mrd/retrospective_mrd_trajectories.png',
    'longitudinal/trendlines_pooled.png', 'longitudinal/trendlines.png', 'longitudinal/circall/trendlines.png', 'longitudinal/retrospective/trendlines.png',
    'kinetics/retrospective_blast_trajectories.png', 'kinetics/blast_trajectories_by_cohort.png',
    'kinetics/blast_cohort_overlay.png', 'kinetics/blast_cohort_overlay.pdf',
    'volumes/circall_csf_by_site.png', 'kinetics/mrd/circall_mrd_trajectories.png',
    *{f'kinetics/{name}.{ext}' for name, extensions in {
        'circall_blast_trajectories': ('png',), 'circall_wbc_trajectories': ('png',),
        'circall_blast_wbc_trajectories': ('png', 'pdf'),
        'circall_blast_wbc_overlay': ('png', 'pdf')}.items() for ext in extensions},
    *{f'longitudinal/{name}{suffix}.png' for name in ('boxplots', 'trajectories') for suffix in ('', '_pooled')},
    *{f'{folder}/test_plots/{name}.png' for folder in ('longitudinal/circall', 'longitudinal/retrospective', 'pooled')
      for name in ('welch_sample', 'welch_patient_median', 'mannwhitney_patient_median', 'mixed_contrasts')},
    *{f'yield/{name}{suffix}.png' for name in ('dna_concentration_ng_per_uL', 'dna_total_ng', 'dna_ng_per_mL_plasma')
      for suffix in ('', '_pooled')},
    *{f'yield/{x}_vs_{y}.png' for x in ('volume_ml', 'elution_volume_uL')
      for y in ('dna_concentration_ng_per_uL', 'dna_total_ng', 'dna_ng_per_mL_plasma')},
    *{f'yield/blood_pellet_{cohort}_{metric}.png'
      for cohort, metrics in {'circall': ('dna_concentration_ng_per_uL', 'dna_total_ng', 'dna_ng_per_mL_plasma'),
                             'retrospective': ('albumin_ng_per_uL', 'vario_ng_per_uL', 'vario_total_ng')}.items()
      for metric in metrics},
}


def deliverables(workflow, source, record):
    """Map native relative paths to visible relative paths, without reading rows."""
    if workflow == 'canonical':
        selected = {name: name for name in SAMPLE_TABLES | SAMPLE_FIGURES}
        selected.update({f'spreadsheet/{scope}_statistics.xlsx': f'{scope}_statistics.xlsx'
                         for scope in ('circall', 'retrospective', 'combined')})
    elif workflow == 'cfdna_associations':
        selected = {}
        scopes = record['details'].get('scopes')
        if scopes is not None:
            for name in ('diagnosis_availability.csv','diagnosis_settings.json'):
                selected['cfdna_associations/'+name] = name
        else:
            scopes = [dict(relative_dir='',predictors=record['details']['predictors'],
                           descriptive_predictors=record['details'].get('descriptive_predictors',[]))]
        for scope in scopes:
            prefix = scope['relative_dir']+'/' if scope['relative_dir'] else ''
            for name in ('cohort_summary.csv','predictor_descriptions.csv'):
                selected['cfdna_associations/'+prefix+name] = prefix+name
            for predictor in scope['predictors']:
                for name in ('results.csv',(predictor.get("figure_name") or f"log10_cfDNA_vs_{predictor['variable']}.png")):
                    relative = f"{prefix}{predictor['output_name']}/{name}"
                    selected['cfdna_associations/'+relative] = relative
            for predictor in scope['descriptive_predictors']:
                for name in ('descriptive_summary.csv',(predictor.get("figure_name") or f"log10_cfDNA_vs_{predictor['variable']}.png")):
                    relative = f"{prefix}{predictor['output_name']}/{name}"
                    selected['cfdna_associations/'+relative] = relative
    elif workflow == 'blast_kinetics':
        selected = {name: name for name in ('scatter.png', 'mixed_model.png', 'model_summary.txt', 'cohort_summary.json')}
    elif workflow == 'disease_modeling':
        reports = {c['cohort']: c for c in record['cohorts'] if c['report_status'] == 'complete'}
        selected = {a['path']: a['path'] for a in record['artifacts']
                    if a['path'].split('/')[0] in reports
                    and (a['path'] == a['path'].split('/')[0]+'/disease_modeling.xlsx'
                         or (reports[a['path'].split('/')[0]]['disease_status'] == 'complete'
                             and '/figures/' in a['path'] and Path(a['path']).suffix in ('.png', '.pdf')))}
    elif workflow == 'advanced_analysis':
        reports = {c['cohort']: c for c in record['cohorts'] if c['report_status'] == 'complete'}
        selected = {a['path']: a['path'] for a in record['artifacts']
                    if a['path'].split('/')[0] in reports
                    and (a['path'] == a['path'].split('/')[0]+'/associations.xlsx'
                         or (reports[a['path'].split('/')[0]]['association_status'] == 'complete'
                             and '/figures/' in a['path'] and Path(a['path']).suffix in ('.png', '.pdf')))}
    elif workflow == 'sample_statistics':
        reports = {c['cohort']: c for c in record['cohorts'] if c['report_status']=='complete'}
        selected = {a['path']: a['path'] for a in record['artifacts']
                    if a['path'].split('/')[0] in reports
                    and (a['path'] == a['path'].split('/')[0]+'/statistics.xlsx'
                         or (reports[a['path'].split('/')[0]]['statistics_status']=='complete'
                             and Path(a['path']).suffix in ('.png', '.pdf'))) }
    elif workflow == 'data_integrity':
        selected = {c['cohort']+'/integrity_report.xlsx': c['cohort']+'/integrity_report.xlsx'
                    for c in record['cohorts'] if c['report_status']=='complete'}
    else:
        raise ValueError('Unknown registered workflow')
    return {old: new for old, new in sorted(selected.items()) if (source / old).is_file()}


def publication_directory(root, workflow):
    """Single-layer runs expose cohorts directly; mixed runs stay grouped."""
    root = Path(root)
    if workflow in ('data_integrity', 'sample_statistics', 'advanced_analysis', 'disease_modeling'):
        manifest = root / '.audit/run_manifest.json'
        if manifest.is_file():
            record = json.loads(manifest.read_text())
            selected = [w['name'] for w in record.get('workflows', [])]
            if record.get('workflow') == workflow or selected == [workflow]:
                return root
    return root / DIRECTORIES[workflow]


def publish(root, workflow, source, record):
    """Validate copies, then expose the workflow directory in one rename."""
    root, source = Path(root), Path(source)
    target = publication_directory(root, workflow)
    flat = target == root
    if not flat and (target.exists() or target.is_symlink()):
        raise ValueError('Visible workflow destination already exists')
    selected = deliverables(workflow, source, record)
    if not selected:
        raise ValueError('Completed workflow has no reviewed deliverables')
    temporary = root / '.audit' / 'publication'
    temporary.mkdir(exist_ok=True)
    mappings = []
    with tempfile.TemporaryDirectory(prefix=workflow + '-', dir=temporary) as name:
        stage = Path(name) / 'results'
        stage.mkdir()
        for old, new in selected.items():
            origin, destination = source / old, stage / new
            if Path(new).is_absolute() or '..' in Path(new).parts or not origin.resolve().is_relative_to(source.resolve()):
                raise ValueError('Invalid publication path')
            if any(p.is_symlink() for p in (origin, *origin.parents) if p.is_relative_to(source)):
                raise ValueError('Symlinks cannot be published')
            destination.parent.mkdir(parents=True, exist_ok=True)
            before = digest(origin)
            shutil.copyfile(origin, destination)
            if digest(destination) != before or digest(origin) != before:
                raise ValueError('Artifact changed during publication')
            mappings.append({'workflow': workflow, 'source': str(origin.relative_to(root)),
                             'path': str((target / new).relative_to(root)), 'sha256': before})
        if flat:
            children = sorted(stage.iterdir())
            if any((root / child.name).exists() or (root / child.name).is_symlink() for child in children):
                raise ValueError('Visible cohort destination already exists')
            moved = []
            try:
                for child in children:
                    destination = root / child.name
                    child.rename(destination)
                    moved.append(destination)
            except Exception:
                for destination in reversed(moved):
                    destination.rename(stage / destination.name)
                raise
        else:
            if target.exists() or target.is_symlink():
                raise ValueError('Visible workflow destination appeared during publication')
            stage.rename(target)
    return mappings


def finish_run(root, record):
    from .provenance import artifact_index
    root = Path(root)
    record['finished_utc'] = utc_now()
    path = root / '.audit/run_manifest.json'
    write_json(path, record)
    try:
        for mapping in record.get('publications', []):
            if digest(root / mapping['source']) != mapping['sha256'] or digest(root / mapping['path']) != mapping['sha256']:
                raise ValueError('Published artifact changed')
        index = artifact_index(root, DIRECTORIES)
        index.update(output_layout_version=LAYOUT_VERSION, publications=record.get('publications', []))
        # Ownership includes caches and empty directories for strict --force checks.
        index['owned_files'] = sorted({str(p.relative_to(root)) for p in root.rglob('*') if p.is_file()} | {'.audit/artifact_index.json'})
        index['owned_directories'] = sorted(str(p.relative_to(root)) for p in root.rglob('*') if p.is_dir())
        write_json(root / '.audit/artifact_index.json', index)
    except Exception:
        record.update(status='failed', error='Artifact indexing or publication verification failed')
        write_json(path, record)
        raise


def validate_owned_run(root, workflow):
    """Explicit replacement may only touch a complete, indexed run of this workflow."""
    root = Path(root)
    if any(p.is_symlink() for p in (root, *root.parents)) or not root.is_dir():
        raise ValueError('Output is not an owned run directory')
    paths = list(root.rglob('*'))
    if any(p.is_symlink() for p in paths):
        raise ValueError('Output contains symlinks not owned by the pipeline')
    try:
        record = json.loads((root / '.audit/run_manifest.json').read_text())
        index = json.loads((root / '.audit/artifact_index.json').read_text())
        if record['workflow'] != workflow or record['status'] != 'complete' or record['output_layout_version'] != LAYOUT_VERSION:
            raise ValueError('Output is not a complete owned run')
        files = {str(p.relative_to(root)) for p in paths if p.is_file()}
        dirs = {str(p.relative_to(root)) for p in paths if p.is_dir()}
        if files != set(index['owned_files']) or dirs != set(index['owned_directories']):
            raise ValueError('Output contains files or directories not owned by the pipeline')
        for item in index['artifacts']:
            relative = Path(item['path'])
            if relative.is_absolute() or '..' in relative.parts or digest(root / relative) != item['sha256']:
                raise ValueError('Owned output changed since publication')
    except (OSError, KeyError, TypeError, json.JSONDecodeError):
        raise ValueError('Output is not an indexed owned run') from None


def run_standalone(workflow, root, settings, execute, complete):
    """Use the same audit/publication contract for direct and integrated entrypoints."""
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
