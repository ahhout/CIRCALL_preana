"""Clean result publication over retained, unmodified engine output layouts."""
import json
from pathlib import Path
import shutil
import tempfile

from .provenance import digest, utc_now, write_json

LAYOUT_VERSION = 2
DIRECTORIES = {'data_integrity': '01_data_integrity', 'sample_statistics': '02_sample_statistics',
               'advanced_analysis': '03_advanced_analysis', 'disease_modeling': '04_disease_modeling'}


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


# Reviewed presentation contract. Unlisted engine artifacts remain audit-only.
def deliverables(workflow, source, record):
    """Map native relative paths to visible relative paths, without reading rows."""
    if workflow == 'disease_modeling':
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
    """Resolve grouped current ownership and historical flat-layout ownership."""
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
        # Ownership retains caches and empty directories for audit accounting.
        index['owned_files'] = sorted({str(p.relative_to(root)) for p in root.rglob('*') if p.is_file()} | {'.audit/artifact_index.json'})
        index['owned_directories'] = sorted(str(p.relative_to(root)) for p in root.rglob('*') if p.is_dir())
        write_json(root / '.audit/artifact_index.json', index)
    except Exception:
        record.update(status='failed', error='Artifact indexing or publication verification failed')
        write_json(path, record)
        raise
