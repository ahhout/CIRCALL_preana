from tests.fixtures.pipeline import full_entries
from tests.fixtures.execution import layer_main
import json
import os
from pathlib import Path
import shutil
import subprocess
from zipfile import ZipFile

import pytest

from analysis.disease_modeling import runner
from analysis.pipeline import main as master
from analysis.provenance import ROOT, digest
from .fixtures import sources, cli, inventory, count_source


def profile(root, paths, **changes):
    options = {k.replace('_', '-'):str(v) for k, v in paths.items()}
    options.update({'blood-count-unit':'x10^9/L', 'retrospective-blast-unit':'x10^9/L', **changes})
    path = root/'profile.json'
    path.write_text(json.dumps({'schema_version':1, 'workflows':full_entries(root,[dict(name='disease_modeling', options=options)])}))
    return path


def no_figures(monkeypatch):
    monkeypatch.setattr(runner.reporting, 'figures', lambda *a: None)
    monkeypatch.setattr(runner.reporting, 'count_figure', lambda *a, **kw: None)


def test_control_gate_preflight_status_and_independent_reports(tmp_path, monkeypatch):
    paths = sources(tmp_path, bad_control=True)
    no_figures(monkeypatch)
    out = tmp_path/'blocked'
    assert layer_main('disease_modeling', cli(paths, out)+['--validate-only']) == 1
    assert not out.exists()
    cfg = profile(tmp_path, paths)
    assert master(['--config', str(cfg), '--output-dir', str(out), '--validate-only']) == 1
    assert not out.exists()
    assert layer_main('disease_modeling', cli(paths, out)) == 1
    native = out/'.audit/workflows/04_disease_modeling'
    record = json.loads((native/'run_manifest.json').read_text())
    runner.validate_results(native, record)
    states = {c['cohort']:c['disease_status'] for c in record['cohorts']}
    assert states == dict(retrospective='complete', circall='blocked', pooled='blocked', comparisons='unavailable')
    assert all((out/c/'disease_modeling.xlsx').is_file() for c in states)
    assert layer_main('disease_modeling', cli(paths, tmp_path/'exclude')+['--no-include-controls']) == 0


def test_master_full_execution_publishes_reports_despite_gate_preflight(tmp_path):
    paths = sources(tmp_path, bad_control=True)
    cfg = profile(tmp_path, paths)
    out = tmp_path/'master'
    assert master(['--config', str(cfg), '--output-dir', str(out)]) == 1
    assert (out/'04_disease_modeling/retrospective/disease_modeling.xlsx').is_file()
    assert (out/'04_disease_modeling/circall/disease_modeling.xlsx').is_file()
    manifest = json.loads((out/'.audit/run_manifest.json').read_text())
    assert manifest['workflows'][3]['status'] == 'complete'
    assert manifest['workflows'][3]['quality_status'] == 'errors_found'


def test_missing_source_and_invalid_annotation_do_not_leak(tmp_path, monkeypatch):
    paths = sources(tmp_path)
    paths['retrospective_blasts'] = tmp_path/'missing_counts.xlsx'
    no_figures(monkeypatch)
    out = tmp_path/'missing'
    assert layer_main('disease_modeling', cli(paths, out)) == 1
    native = out/'.audit/workflows/04_disease_modeling'
    r = json.loads((native/'retrospective/disease_modeling.json').read_text())
    assert r['status'] == 'blocked' and r['blocking'][0]['reason'] == 'file_unavailable'
    inventory(paths['circall'], 'circall', [dict(circall_id='001-9001-X-Z', MRD_TP1='PRIVATE_BAD_CLINICAL_NOTE')])
    paths['retrospective_blasts'] = tmp_path/'retrospective_blasts.xlsx'
    fail = tmp_path/'annotation'
    assert layer_main('disease_modeling', cli(paths, fail)) == 1
    r = json.loads((fail/'.audit/workflows/04_disease_modeling/circall/disease_modeling.json').read_text())
    assert r['blocking'][0]['reason'] == 'invalid_mrd_annotation'
    assert not any('PRIVATE_BAD_CLINICAL_NOTE' in p.read_text() for p in fail.rglob('*.json'))


def test_empty_valid_sources_are_limitations_not_failure(tmp_path, monkeypatch):
    paths = sources(tmp_path)
    inventory(paths['inventory'], 'retrospective', [dict(patient_id='P1', timepoint='diag', specimen_type='bone marrow', MRD_IgTCR=None)])
    count_source(paths['retrospective_blasts'], 'retrospective', [])
    no_figures(monkeypatch)
    out = tmp_path/'empty'
    assert layer_main('disease_modeling', cli(paths, out)) == 0
    record = json.loads((out/'.audit/workflows/04_disease_modeling/run_manifest.json').read_text())
    assert any(r['status'] == 'unavailable' for r in record['analysis_status'])
    assert record['quality_status'] != 'errors_found'


def test_unexpected_failure_preserves_safe_aggregate_report(tmp_path, monkeypatch):
    paths = sources(tmp_path)
    original = runner.mrd.prepare
    def fail(path, cohort, *a, **kw):
        if cohort == 'retrospective':
            raise RuntimeError('PRIVATE_FAILURE_NOTE')
        return original(path, cohort, *a, **kw)
    monkeypatch.setattr(runner.mrd, 'prepare', fail)
    no_figures(monkeypatch)
    out = tmp_path/'failure'
    assert layer_main('disease_modeling', cli(paths, out)) == 1
    r = json.loads((out/'.audit/workflows/04_disease_modeling/retrospective/disease_modeling.json').read_text())
    assert r['status'] == 'execution_failed' and r['blocking'] == [{'reason':'RuntimeError'}]
    assert 'PRIVATE_FAILURE_NOTE' not in json.dumps(r)


def test_real_standalone_master_equivalence_privacy_and_fresh_destinations(tmp_path):
    paths = sources(tmp_path)
    inventory(paths['circall'], 'circall', [dict(circall_id='001-9001-X-Z',
              MRD_TP1='Positive NQ <5.10-5', MRD_TP2='negative')])
    hashes = {k:digest(p) for k, p in paths.items()}
    cfg = profile(tmp_path, paths)
    standalone, integrated = tmp_path/'standalone', tmp_path/'master'
    assert master(['--config', str(cfg), '--validate-only']) == 0
    assert layer_main('disease_modeling', cli(paths, standalone)) == 0
    assert master(['--config', str(cfg), '--output-dir', str(integrated)]) == 0
    assert hashes == {k:digest(p) for k, p in paths.items()}
    for scope in ('retrospective','circall','pooled','comparisons'):
        relative = Path('.audit/workflows/04_disease_modeling')/scope/'disease_modeling.json'
        assert json.loads((standalone/relative).read_text()) == json.loads((integrated/relative).read_text())
    for out in (standalone, integrated):
        index = json.loads((out/'.audit/artifact_index.json').read_text())
        assert all(digest(out/a['path']) == a['sha256'] for a in index['artifacts'])
        assert all(digest(out/a['path']) == digest(out/a['source']) == a['sha256'] for a in index['publications'])
        assert all(a['path'].endswith(('.xlsx','.png','.pdf')) for a in index['publications'])
        for path in (out/'.audit/workflows/04_disease_modeling').rglob('*'):
            if path.suffix in ('.json', '.csv', '.log'):
                content = path.read_text()
                assert 'PRIVATE_' not in content and '001-9001-X-Z' not in content
                assert 'subject_hash' not in content
            if path.suffix == '.xlsx':
                with ZipFile(path) as z:
                    assert all(b'PRIVATE_' not in z.read(n) and b'001-9001-X-Z' not in z.read(n) for n in z.namelist() if n.endswith('.xml'))
        for path in (out/'.audit/workflows/04_disease_modeling').rglob('*.png'):
            if '.cache' not in path.parts:
                other = (integrated if out == standalone else standalone)/path.relative_to(out)
                assert digest(path) == digest(other)
    assert layer_main('disease_modeling', cli(paths, standalone)) == 1
    assert master(['--config', str(cfg), '--output-dir', str(integrated)]) == 1




def test_cli_requires_explicit_units_and_valid_settings(tmp_path):
    paths = sources(tmp_path)
    with pytest.raises(SystemExit):
        runner.arguments(['--inventory',str(paths['inventory']), '--cohort','retrospective','--retrospective-blasts',str(paths['retrospective_blasts'])])
    with pytest.raises(SystemExit):
        runner.arguments(cli(paths)+['--mrd-negative-level','0'])
