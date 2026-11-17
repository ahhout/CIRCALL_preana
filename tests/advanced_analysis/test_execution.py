from tests.fixtures.pipeline import full_entries
from tests.fixtures.execution import layer_main

from tests.fixtures.advanced_analysis import sources
import json
from pathlib import Path
from zipfile import ZipFile

from openpyxl import Workbook
import pytest

from analysis.steps import step_03_advanced_analysis as runner
from analysis.pipeline import main as integrated, load_config, workflow_args
from analysis.outputs import deliverables, publication_directory
from analysis.provenance import digest
from tests.fixtures.advanced_analysis import fixture, row




def cli(paths, output):
    retro, circ, donor = paths
    return ['--inventory', str(retro), '--circall', str(circ), '--donors', str(donor),
            '--retrospective-wbc-unit', 'x10^9/L', '--output-dir', str(output)]


def test_controls_gate_independent_completion_and_publication(tmp_path, monkeypatch):
    paths = sources(tmp_path, bad_controls=True)
    monkeypatch.setattr(runner, 'figures', lambda *a: None)
    output = tmp_path/'blocked'
    assert layer_main('advanced_analysis', cli(paths, output)) == 1
    native = output/'.audit/workflows/03_advanced_analysis'
    rec = json.loads((native/'run_manifest.json').read_text())
    runner.validate_results(native, rec)
    assert (output/'retrospective/associations.xlsx').is_file()
    assert (output/'circall/associations.xlsx').is_file()
    assert (output/'pooled/associations.xlsx').is_file()
    scopes = {r['cohort']:r['association_status'] for r in rec['cohorts']}
    assert scopes == dict(retrospective='complete', circall='blocked', pooled='blocked')
    assert not (native/'circall/observations.json').exists()
    clean = tmp_path/'exclude_controls'
    assert layer_main('advanced_analysis', cli(paths, clean)+['--no-include-controls']) == 0
    assert 'retrospective_controls' not in json.loads((clean/'.audit/workflows/03_advanced_analysis/run_manifest.json').read_text())['inputs']


def test_unavailable_donor_blocks_only_selected_retrospective(tmp_path, monkeypatch):
    paths = sources(tmp_path)
    nonexistent = tmp_path/'unavailable_donors.xlsx'
    monkeypatch.setattr(runner, 'figures', lambda *a: None)
    output = tmp_path/'unavailable'
    assert layer_main('advanced_analysis', cli((paths[0], paths[1], nonexistent), output)) == 1
    rec = json.loads((output/'.audit/workflows/03_advanced_analysis/run_manifest.json').read_text())
    scopes = {r['cohort']:r['association_status'] for r in rec['cohorts']}
    assert scopes['retrospective'] == 'blocked' and scopes['circall'] == 'complete'
    assert rec['source_states']['retrospective_controls']['availability'] == 'unavailable'


def test_execution_failure_safe_report_and_peer_completion(tmp_path, monkeypatch):
    paths = sources(tmp_path)
    monkeypatch.setattr(runner, 'figures', lambda *a: None)
    original = runner.prepare
    def fail(path, cohort, d, **kwargs):
        if cohort == 'retrospective':
            raise RuntimeError('PRIVATE_IDENTIFIER_SENTINEL')
        return original(path, cohort, d, **kwargs)
    monkeypatch.setattr(runner, 'prepare', fail)
    output = tmp_path/'failed'
    assert layer_main('advanced_analysis', cli(paths, output)) == 1
    native = output/'.audit/workflows/03_advanced_analysis'
    r = json.loads((native/'retrospective/associations.json').read_text())
    assert r['status'] == 'execution_failed' and r['blocking'] == [{'reason':'RuntimeError'}]
    assert (output/'circall/associations.xlsx').is_file()
    assert not any('PRIVATE_IDENTIFIER_SENTINEL' in p.read_text() for p in output.rglob('*.json'))


def test_empty_unestimable_is_analytical_limitation(tmp_path, monkeypatch):
    paths = sources(tmp_path)
    fixture(paths[0], rows=[row(timepoint='tp1')])
    monkeypatch.setattr(runner, 'figures', lambda *a: None)
    output = tmp_path/'empty'
    assert layer_main('advanced_analysis', cli(paths, output)) == 0
    result = json.loads((output/'.audit/workflows/03_advanced_analysis/retrospective/associations.json').read_text())
    assert result['status'] == 'complete' and result['tables']['Associations'][0]['status'] == 'skipped'


def test_standalone_master_equivalence_privacy_artifacts_and_fresh_destination(tmp_path):
    paths = sources(tmp_path)
    retro, circ, donor = paths
    hashes = [digest(p) for p in paths]
    options = {'inventory':str(retro), 'circall':str(circ), 'donors':str(donor), 'cohort':'all',
               'retrospective-wbc-unit':'x10^9/L', 'include-controls':True, 'sample-selection-seed':37}
    profile = tmp_path/'profile.json'
    profile.write_text(json.dumps({'schema_version':1, 'workflows':full_entries(tmp_path,[dict(name='advanced_analysis', options=options)])}))
    standalone, master = tmp_path/'standalone', tmp_path/'master'
    assert integrated(['--config', str(profile), '--validate-only', '--output-dir', str(master)]) == 0
    assert not master.exists()
    assert layer_main('advanced_analysis', cli(paths, standalone)+['--sample-selection-seed', '37']) == 0
    assert integrated(['--config', str(profile), '--output-dir', str(master)]) == 0
    assert [digest(p) for p in paths] == hashes
    from analysis.validation.validate_advanced_analysis import compare
    validation = compare(standalone, master)
    assert validation['status'] == 'passed' and validation['identical_workbooks'] == 3
    for scope in ('retrospective', 'circall', 'pooled'):
        for name in ('associations.json', 'observations.json', 'source_observations.json', 'model_diagnostics.json'):
            relative = Path('.audit/workflows/03_advanced_analysis')/scope/name
            assert json.loads((standalone/relative).read_text()) == json.loads((master/relative).read_text())
    for output in (standalone, master):
        record = json.loads((output/'.audit/workflows/03_advanced_analysis/run_manifest.json').read_text())
        assert record['resolved_settings']['sample_selection_seed'] == 37
        assert record['resolved_settings']['association_definition']['rules']['sample_selection_seed'] == 37
        result = json.loads((output/'.audit/workflows/03_advanced_analysis/retrospective/associations.json').read_text())
        assert result['summary']['unselected_numeric_outcome_samples'] == 1
        primary = next(r for r in result['tables']['Associations']
                       if r['outcome'] == 'cfdna_ng_per_ml_plasma' and r['predictor'] == 'peripheral_blast_percent')
        assert primary['contributing_outcome_samples'] == 5
        index = json.loads((output/'.audit/artifact_index.json').read_text())
        assert all(digest(output/a['path']) == a['sha256'] for a in index['artifacts'])
        assert all(digest(output/a['path']) == digest(output/a['source']) == a['sha256'] for a in index['publications'])
        assert all(a['path'].endswith(('.xlsx','.png','.pdf')) for a in index['publications'])
        assert publication_directory(output, 'advanced_analysis') == (output if output == standalone else output/'03_advanced_analysis')
        for path in output.rglob('*'):
            if path.suffix in ('.json','.csv','.log'):
                assert 'PRIVATE_' not in path.read_text()
            if path.suffix == '.xlsx':
                with ZipFile(path) as z:
                    assert all(b'PRIVATE_' not in z.read(n) for n in z.namelist() if n.endswith('.xml'))
        for a in index['publications']:
            if a['workflow'] == 'advanced_analysis' and a['path'].endswith('.png'):
                assert digest(output/a['path']) == digest((master/'03_advanced_analysis'/a['path']) if output == standalone else (standalone/Path(a['path']).relative_to('03_advanced_analysis')))
    assert layer_main('advanced_analysis', cli(paths, standalone)) == 1
    assert integrated(['--config', str(profile), '--output-dir', str(master)]) == 1
    mixed = tmp_path/'mixed'
    (mixed/'.audit').mkdir(parents=True)
    (mixed/'.audit/run_manifest.json').write_text(json.dumps({'workflows':[{'name':'advanced_analysis'}, {'name':'data_integrity'}]}))
    assert publication_directory(mixed, 'advanced_analysis') == mixed/'03_advanced_analysis'


def test_profile_registration_and_definitions_provenance():
    from analysis.provenance import ROOT
    entry = load_config(ROOT/'configs/pipeline_layers.json')['workflows'][2]
    args = workflow_args(entry)
    assert args.cohort == 'all' and args.include_controls and args.pool_cohorts and args.spearman_sensitivity
    assert args.predictors == ['requested'] and args.retrospective_wbc_unit == 'x10^9/L'
    assert args.sample_selection_seed == 123
