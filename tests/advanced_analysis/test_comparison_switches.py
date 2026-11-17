from tests.fixtures.pipeline import full_entries
"""Per-comparison switches control inference and publication without reselection."""
from copy import deepcopy
import json

import pandas as pd
import pytest

from analysis.advanced_analysis.step_01_prepare import load_definitions, prepare
from analysis.advanced_analysis.step_03_report import figures, report_tables, workbook, validate_workbook
from analysis.advanced_analysis.schema import comparisons
from analysis.advanced_analysis.step_02_analyze import analyze
from analysis.pipeline import main as integrated
from tests.fixtures.advanced_analysis import sources
from tests.fixtures.advanced_analysis import D, fixture
from tests.fixtures.advanced_analysis import sample, settings


def disable_all():
    d = deepcopy(D)
    for outcomes in d['comparisons'].values():
        for switches in outcomes.values():
            for variable in switches:
                switches[variable] = False
    return d


def test_custom_definitions_may_change_only_boolean_switches(tmp_path):
    d = deepcopy(D)
    d['comparisons']['circall']['dna_total_ng']['sampling_time'] = False
    path = tmp_path/'definitions.json'
    path.write_text(json.dumps(d))
    assert load_definitions(path) == d
    d['rules']['sampling_time_cutoff_hour'] = 10
    path.write_text(json.dumps(d))
    with pytest.raises(ValueError, match='scientific settings'):
        load_definitions(path)


@pytest.mark.parametrize('bad', ['false', 0, 1, 0.0, None, [], {}])
def test_nonboolean_switches_are_rejected(tmp_path, bad):
    d = deepcopy(D)
    d['comparisons']['circall']['dna_total_ng']['sampling_time'] = bad
    path = tmp_path/'definitions.json'
    path.write_text(json.dumps(d))
    with pytest.raises(ValueError, match='JSON true/false'):
        load_definitions(path)


@pytest.mark.parametrize('change', ['unknown', 'unrequested', 'missing'])
def test_custom_files_cannot_change_comparison_keys(tmp_path, change):
    d = deepcopy(D)
    switches = d['comparisons']['circall']['dna_total_ng']
    if change == 'missing':
        del switches['sampling_time']
    else:
        switches['unknown' if change == 'unknown' else 'elution_volume_ul'] = True
    path = tmp_path/'definitions.json'
    path.write_text(json.dumps(d))
    with pytest.raises(ValueError):
        load_definitions(path)


def test_switch_is_specific_to_cohort_and_outcome_and_removes_pooled_pair(tmp_path):
    path = tmp_path/'source.xlsx'
    fixture(path, 'circall', [sample(i) for i in range(1, 9)])
    before, before_counts, before_evidence, before_issues = prepare(path, 'circall', D)
    d = deepcopy(D)
    pair = ('dna_total_ng', 'peripheral_blast_percent')
    d['comparisons']['circall'][pair[0]][pair[1]] = False
    after, counts, evidence, issues = prepare(path, 'circall', d)
    pd.testing.assert_frame_equal(before, after)
    assert (counts, evidence, issues) == (before_counts, before_evidence, before_issues)
    assert pair not in comparisons(d, 'circall') and pair not in comparisons(d, 'pooled')
    assert pair in comparisons(d, 'retrospective')
    assert ('cfdna_total_ng', pair[1]) in comparisons(d, 'circall')
    result, models, residuals = analyze(after, 'circall', settings(), d)
    assert result['summary']['requested_comparisons'] == 30
    assert result['summary']['disabled_comparisons'] == 1
    for rows in result['tables'].values():
        assert all((r['outcome'], r['predictor']) != pair for r in rows)
    assert '/'.join(pair) not in models
    assert all((r['outcome'], r['predictor']) != pair for r in residuals)
    toggle = next(r for r in report_tables(result, d)['Definitions'] if r['field'] == ' vs '.join(pair))
    assert toggle['enabled'] is False


def test_all_false_produces_valid_empty_reports_and_no_figures(tmp_path):
    d = disable_all()
    path = tmp_path/'source.xlsx'
    fixture(path, 'circall', [sample(i) for i in range(1, 9)])
    frame, counts, _, issues = prepare(path, 'circall', d)
    assert not issues
    result, models, residuals = analyze(frame, 'circall', settings(), d, counts=counts)
    assert result['summary']['requested_comparisons'] == 0
    assert result['summary']['disabled_comparisons'] == 31
    assert result['summary']['configured_tests'] == 0
    assert all(not rows for rows in result['tables'].values()) and not models and not residuals
    output = tmp_path/'figures'
    figures(output, frame, result, models, settings(), d)
    assert not output.exists()
    workbook(tmp_path/'report.xlsx', result, d)
    validate_workbook(tmp_path/'report.xlsx', result, d)


def test_integrated_run_records_switches_and_publishes_only_enabled_comparison(tmp_path):
    d = disable_all()
    d['comparisons']['circall']['cfdna_ng_per_ml_plasma']['peripheral_blast_percent'] = True
    definitions = tmp_path/'definitions.json'
    definitions.write_text(json.dumps(d))
    retro, circ, donors = sources(tmp_path)
    config = tmp_path/'profile.json'
    config.write_text(json.dumps({'schema_version':1, 'workflows':full_entries(tmp_path,[{'name':'advanced_analysis', 'options':{
        'inventory':str(retro), 'circall':str(circ), 'donors':str(donors),
        'definitions':str(definitions), 'retrospective-wbc-unit':'x10^9/L',
        'predictors':['peripheral_blast_percent']}}])}))
    output = tmp_path/'run'
    assert integrated(['--config', str(config), '--validate-only', '--output-dir', str(output)]) == 0
    assert not output.exists()
    assert integrated(['--config', str(config), '--output-dir', str(output)]) == 0
    native = output/'.audit/workflows/03_advanced_analysis'
    manifest = json.loads((native/'run_manifest.json').read_text())
    assert manifest['resolved_settings']['association_definition']['comparisons'] == d['comparisons']
    for scope, enabled in [('circall',1), ('retrospective',0), ('pooled',0)]:
        result = json.loads((native/scope/'associations.json').read_text())
        assert len(result['tables']['Coverage']) == enabled
        assert len(result['tables']['Associations']) == enabled
        assert (output/'03_advanced_analysis'/scope/'associations.xlsx').is_file()
    assert len(list((output/'03_advanced_analysis/circall/figures').rglob('*.png'))) == 1
    assert not (output/'03_advanced_analysis/retrospective/figures').exists() and not (output/'03_advanced_analysis/pooled/figures').exists()
