"""Read-only completeness checks shared by historical/current result comparators."""
import json
from pathlib import Path

from analysis.provenance import artifact_index
from analysis.outputs import DIRECTORIES


def checked_index(root):
    """Reconcile the complete non-cache file population, not just listed hashes."""
    root = Path(root)
    index = json.loads((root/'.audit/artifact_index.json').read_text())
    actual = {item['path']: item for item in artifact_index(root, DIRECTORIES)['artifacts']}
    listed = index['artifacts']
    expected = {item['path']: item for item in listed}
    if len(expected) != len(listed) or set(expected) != set(actual):
        raise ValueError('Indexed artifact population differs from actual files')
    for relative, item in expected.items():
        if any(item[field] != actual[relative][field] for field in ('sha256', 'workflow', 'size_bytes')):
            raise ValueError('Indexed artifact mismatch')
    manifest = json.loads((root/'.audit/run_manifest.json').read_text())
    if manifest.get('publications', []) != index.get('publications', []):
        raise ValueError('Publication inventory differs from run manifest')
    return index


def scope_states(record, status_key):
    states = {c['cohort']: (c['report_status'], c[status_key]) for c in record['cohorts']}
    if len(states) != len(record['cohorts']):
        raise ValueError('Duplicate report scope')
    return states


def matching_figures(left, right):
    """Require symmetric PNG/PDF populations; PNG content is checked by callers."""
    def paths(root):
        return {p.relative_to(root) for p in root.rglob('*')
                if p.is_file() and '.cache' not in p.parts and p.suffix in ('.png', '.pdf')}
    figures = paths(left)
    if figures != paths(right):
        raise ValueError('Figure artifact populations differ')
    return sorted(p for p in figures if p.suffix == '.png')


def workflow_files(root, workflow, index):
    """Other layers can legitimately have different identifier-export contracts."""
    return [Path(root)/item['path'] for item in index['artifacts']
            if item['workflow'] in (workflow, 'pipeline')]
