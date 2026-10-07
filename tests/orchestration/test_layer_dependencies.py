"""All released layers execute with the older scientific packages absent."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import pytest

from analysis.provenance import ROOT, digest
from tests.advanced_analysis.test_execution import sources as association_sources
from tests.disease_modeling.fixtures import sources as disease_sources, inventory


@pytest.mark.parametrize('blocked', [False, True])
def test_all_layers_standalone_and_integrated_without_older_packages(tmp_path, blocked):
    isolated = tmp_path/'retained_repository'
    isolated.mkdir()
    excluded = ('sample_analysis', 'cfdna_associations', 'blast_kinetics')
    shutil.copytree(ROOT/'analysis', isolated/'analysis',
                    ignore=shutil.ignore_patterns(*excluded, '__pycache__'))
    for folder in ('configs', 'environments', 'docs'):
        shutil.copytree(ROOT/folder, isolated/folder)
    shutil.copyfile(ROOT/'run.py', isolated/'run.py')
    shutil.copyfile(ROOT/'run_all_layers.sh', isolated/'run_all_layers.sh')
    assert not any((isolated/'analysis'/name).exists() for name in excluded)
    assoc_dir, disease_dir = tmp_path/'association_sources', tmp_path/'disease_sources'
    assoc_dir.mkdir()
    disease_dir.mkdir()
    retro, circall, donors = association_sources(assoc_dir)
    common = dict(inventory=str(retro), circall=str(circall), donors=str(donors), cohort='all')
    disease = {key.replace('_', '-'): str(path) for key, path in disease_sources(disease_dir).items()}
    if blocked:
        inventory(Path(disease['circall']), 'circall',
                  [dict(circall_id='001-9001-X-Z', MRD_TP1='PRIVATE_BAD_CLINICAL_NOTE')])
    disease.update({'blood-count-unit': 'x10^9/L', 'retrospective-blast-unit': 'x10^9/L'})
    entries = [
        dict(name='data_integrity', options=common),
        dict(name='sample_statistics', options={**common, 'assessment-time': '2026-10-06T12:00:00+00:00'}),
        dict(name='advanced_analysis', options={**common, 'retrospective-wbc-unit': 'x10^9/L'}),
        dict(name='disease_modeling', options=disease),
    ]
    profile = isolated/'configs/pipeline_layers.json'
    profile.write_text(json.dumps(dict(schema_version=1, workflows=entries)))
    env = dict(os.environ, PYTHONPATH=str(isolated), PYTHONDONTWRITEBYTECODE='1',
               MPLBACKEND='Agg', MPLCONFIGDIR=str(tmp_path/'mpl'))

    def run(*args, expected=0, shell=False):
        command = ['bash', str(isolated/'run_all_layers.sh'), *args] if shell else [
            'conda', 'run', '--no-capture-output', '-n', 'pre_analysis', 'python', '-B', *args]
        result = subprocess.run(command, cwd=isolated, env=env,
                                text=True, capture_output=True, check=False)
        assert result.returncode == expected, result.stdout+result.stderr

    master = isolated/'master'
    run('--output-dir', str(master), '--validate-only', shell=True, expected=int(blocked))
    assert not master.exists()
    # Standalone module CLIs are exercised independently of master dispatch.
    for entry in entries:
        args = [item for key, value in entry['options'].items() for item in ('--'+key, value)]
        run('-m', 'analysis.'+entry['name'], *args,
            '--output-dir', str(isolated/entry['name']),
            expected=int(blocked and entry['name'] == 'disease_modeling'))
    if blocked:
        run('--output-dir', str(master), shell=True, expected=1)
    else:
        # Default Python execution must select the same layered profile as the shell.
        run('run.py', '--output-dir', str(master))
    manifest = json.loads((master/'.audit/run_manifest.json').read_text())
    assert manifest['status'] == ('failed' if blocked else 'complete')
    assert len(manifest['run_id']) == 32
    assert manifest['pipeline_kind'] == 'layered'
    assert manifest['code_sha256']['run_all_layers.sh'] == digest(isolated/'run_all_layers.sh')
    assert all(w['status'] == 'complete' for w in manifest['workflows'])
    if blocked:
        assert all(w['quality_status'] != 'errors_found' for w in manifest['workflows'][:3])
        disease_state = manifest['workflows'][3]
        assert disease_state['quality_status'] == 'errors_found'
        scopes = {c['cohort']: c['disease_status'] for c in disease_state['provenance']['cohorts']}
        assert scopes['retrospective'] == 'complete' and scopes['circall'] == 'blocked'
        assert (master/'04_disease_modeling/circall/disease_modeling.xlsx').exists()
        assert not (master/'04_disease_modeling/circall/figures').exists()
    directories = {'data_integrity':'01_data_integrity', 'sample_statistics':'02_sample_statistics',
                   'advanced_analysis':'03_advanced_analysis', 'disease_modeling':'04_disease_modeling'}
    for entry in entries:
        standalone = isolated/entry['name']
        directory = directories[entry['name']]
        # Compare report contents and PNGs, not ZIP timestamps in Excel containers.
        for p in (standalone/'.audit/workflows'/directory).rglob('*.json'):
            if p.name == 'run_manifest.json':
                continue
            relative = p.relative_to(standalone)
            assert json.loads(p.read_text()) == json.loads((master/relative).read_text())
        for p in standalone.rglob('*.png'):
            if '.audit' not in p.relative_to(standalone).parts:
                assert digest(p) == digest(master/directory/p.relative_to(standalone))
        index = json.loads((standalone/'.audit/artifact_index.json').read_text())
        assert all(digest(standalone/a['path']) == a['sha256'] for a in index['artifacts'])
    index = json.loads((master/'.audit/artifact_index.json').read_text())
    assert all(digest(master/a['path']) == a['sha256'] for a in index['artifacts'])


def test_helper_compatibility_exports_and_duplicate_key_rejection():
    import pytest
    from analysis.configuration import unique_object
    from analysis.pipeline import _unique_object
    from analysis import source_state
    from analysis.data_integrity import runner
    assert _unique_object is unique_object
    with pytest.raises(ValueError, match='duplicate keys'):
        json.loads('{"cohort": "all", "cohort": "circall"}', object_pairs_hook=unique_object)
    for name in ('sources', 'capture_sources', 'verify_source_states'):
        assert getattr(runner, name) is getattr(source_state, name)
