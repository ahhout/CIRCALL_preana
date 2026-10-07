"""Shared, dependency-free provenance and atomic metadata writes."""
from datetime import datetime, timezone
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / 'docs/workflow_contracts.md'
PACKAGES = ('numpy', 'pandas', 'scipy', 'statsmodels', 'matplotlib', 'openpyxl', 'seaborn', 'PyYAML')


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def settings_digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str, allow_nan=False).encode()).hexdigest()


def write_json(path, value):
    """Replace only the caller's metadata file, never expose a half-written manifest."""
    path = Path(path)
    payload = json.dumps(value, indent=2, default=str, ensure_ascii=False, allow_nan=False) + '\n'
    with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                     prefix='.' + path.name, delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(payload)
    try:
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def package_versions():
    versions = {}
    for name in PACKAGES:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            continue
    return versions


def git_state():
    try:
        revision = subprocess.run(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'],
                                  capture_output=True, text=True, check=False)
        status = subprocess.run(['git', '-C', str(ROOT), 'status', '--porcelain'],
                                capture_output=True, text=True, check=False)
        return {'code_revision': revision.stdout.strip() if revision.returncode == 0 else None,
                'code_dirty': bool(status.stdout) if status.returncode == 0 else None}
    except OSError:
        return {'code_revision': None, 'code_dirty': None}


def contract(workflow):
    return {'id': workflow, 'version': 2 if workflow in ('canonical', 'cfdna_associations') else 1, 'path': str(CONTRACT.relative_to(ROOT)),
            'sha256': digest(CONTRACT)}


def envelope(workflow, settings, inputs, code, lock=None, command=None):
    return {'schema_version': 1, 'workflow': workflow, 'status': 'running',
            'started_utc': utc_now(), 'finished_utc': None,
            'command': command or [sys.executable, *sys.argv],
            'resolved_settings': settings, 'resolved_settings_sha256': settings_digest(settings),
            'scientific_contract': contract(workflow),
            'inputs': {name: {'path': str(Path(path).resolve()), 'sha256': digest(path)}
                       for name, path in inputs.items()},
            'code_sha256': {str(Path(p).relative_to(ROOT)): digest(p) for p in sorted(set(code))},
            'python': sys.version, 'executable': sys.executable, 'packages': package_versions(),
            'environment_name': os.environ.get('CONDA_DEFAULT_ENV'),
            'environment_lock_sha256': digest(lock) if lock else None, **git_state()}


def verify_inputs(inputs):
    for source in inputs.values():
        path = Path(source['path'])
        if not path.is_file() or digest(path) != source['sha256']:
            raise ValueError('An input changed during validation/execution; use a fresh run')


def artifact_index(output, owners):
    """Index results and hidden audit evidence; exclude caches and publication staging."""
    from .outputs import DIRECTORIES, publication_directory
    output = Path(output)
    by_directory = {value: key for key, value in DIRECTORIES.items()}
    flat_workflow = next((w for w in ('data_integrity', 'sample_statistics', 'advanced_analysis', 'disease_modeling')
                          if publication_directory(output, w) == output), None)
    records = []
    for path in sorted(output.rglob('*')):
        relative = path.relative_to(output)
        if path.is_symlink():
            raise ValueError('Symlinks are not valid run artifacts')
        if any(part.startswith('.') and part != '.audit' for part in relative.parts) or 'publication' in relative.parts or path.name == 'artifact_index.json':
            continue
        if path.is_file():
            parts = relative.parts
            owner = by_directory.get(parts[0], parts[0] if parts[0] in owners else 'pipeline')
            if flat_workflow and parts[0] in ('retrospective', 'circall', 'pooled', 'comparisons'):
                owner = flat_workflow
            if parts[:2] == ('.audit', 'workflows') and len(parts) > 2:
                owner = by_directory.get(parts[2], 'pipeline')
            if parts[:2] == ('.audit', 'logs'):
                owner = by_directory.get(path.stem, path.stem if path.stem in owners else 'pipeline')
            records.append({'path': str(relative), 'workflow': owner,
                            'size_bytes': path.stat().st_size, 'sha256': digest(path)})
    return {'schema_version': 1, 'artifacts': records}
