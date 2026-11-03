import json

import matplotlib.pyplot as plt
import pytest

from analysis.disease_modeling import mrd, counts, reporting
from analysis.disease_modeling.common import ClinicalError, load_definitions
from analysis.disease_modeling.runner import arguments, evaluate, combined_results
from analysis.data_integrity.checks import load_rules
from analysis.provenance import ROOT
from .fixtures import inventory, count_source, sources, cli

D = load_definitions(ROOT/'configs/definitions/disease_modeling.json')


@pytest.mark.parametrize('value,expected', [(.001, ('quantified', .001, None)), ('2,5e-5', ('quantified', 2.5e-5, None)),
    ('pos NQ <10-4', ('positive_nonquantifiable', None, 1e-4)), ('pos NQ <5.10-5', ('positive_nonquantifiable', None, 5e-5)),
    ('pos NQ', ('positive_nonquantifiable', None, None)), ('NEG', ('negative', None, None)), ('?', ('missing', None, None))])
def test_mrd_values_bounds_and_unknowns(value, expected):
    assert mrd.parse_annotation(value, 'retrospective', D) == expected


@pytest.mark.parametrize('value', [0, -1, 2, True, float('inf'), '<1e-4', 'pos NQ <0', 'pos NQ <bad', 'unknown significance'])
def test_invalid_retrospective_mrd(value):
    with pytest.raises(ClinicalError):
        mrd.parse_annotation(value, 'retrospective', D)


def test_mrd_identity_tissue_visit_receipt_and_priority(tmp_path):
    path = tmp_path/'source.xlsx'
    rows = [dict(patient_id='P1', specimen_type='bone marrow', timepoint='tp1', MRD_IgTCR=v, sample_id='na') for v in ['negative', 'pos NQ <10-4', .001, .002]]
    rows += [dict(patient_id='P1', specimen_type='bone marrow', timepoint='TP2', MRD_IgTCR='pos NQ <5.10-4'),
             dict(patient_id='P2', specimen_type='bone marrow', timepoint='tp1', MRD_IgTCR='?'),
             dict(patient_id='P3', specimen_type='plasma', timepoint='tp1', MRD_IgTCR='bad'),
             dict(patient_id='P3', specimen_type='bone marrow', timepoint='diag', MRD_IgTCR='bad')]
    inventory(path, 'retrospective', rows)
    data, coverage = mrd.prepare(path, 'retrospective', D, duplicate_policy='worst')
    assert len(data) == 3 and coverage['retained_patients'] == 2
    chosen = next(r for r in data if r['status'] == 'quantified')
    assert chosen['measured_fraction'] == .002 and chosen['resolved_disagreement']
    assert next(r for r in data if r['status'] == 'positive_nonquantifiable')['upper_bound_fraction'] == .0005
    assert coverage['source_unknown'] == 1
    with pytest.raises(ClinicalError, match='conflicting_mrd_metadata'):
        mrd.prepare(path, 'retrospective', D, duplicate_policy='error')


def test_circall_patient_metadata_independent_of_source_visit(tmp_path):
    path = tmp_path/'source.xlsx'
    rows = [dict(circall_id='001-9001-X-Z', timepoint='tp2', specimen_type='CSF', sample_id=None, MRD_TP1=.001, MRD_TP2='negative'),
            dict(circall_id='001-9001-X-Z', timepoint='diag', specimen_type='plasma', sample_id='?', MRD_TP1=.001),
            dict(circall_id='001-9002-X-Z', MRD_TP1='unknown significance'),
            dict(circall_id='001-9003-X-Z', MRD_TP1=None, MRD_TP2=None)]
    inventory(path, 'circall', rows)
    data, coverage = mrd.prepare(path, 'circall', D, duplicate_policy='worst')
    assert coverage['retained_patients'] == 2 and coverage['patients_without_any_clinical_result'] == 1
    assert len(data) == 6
    assert sum(r['status'] == 'normalized_baseline' for r in data) == 2
    assert all(r['measured_fraction'] is None for r in data if r['status'] != 'quantified')
    rows.append(dict(circall_id='001-9001-X-Z', MRD_TP1=.002))
    inventory(path, 'circall', rows)
    with pytest.raises(ClinicalError, match='conflicting_mrd_metadata'):
        mrd.prepare(path, 'circall', D, duplicate_policy='worst')


@pytest.mark.parametrize('label,sensitivity', [('Positive NQ <5.10-5', 5e-5),
    ('Positive NQ <10-4', 1e-4), ('Positive NQ <10-5', 1e-5),
    ('pos NQ <2,5e-5', 2.5e-5), ('  POSITIVE  NQ < 10^-4 ', 1e-4), ('pos NQ', None)])
def test_circall_positive_nq_preserves_sensitivity_without_measurement(tmp_path, label, sensitivity):
    path = tmp_path/'source.xlsx'
    inventory(path, 'circall', [dict(circall_id='001-9001-X-Z', MRD_TP1=label)]*2)
    data, coverage = mrd.prepare(path, 'circall', D, duplicate_policy='worst')
    nq = next(r for r in data if r['status'] == 'positive_nonquantifiable')
    assert coverage['retained_patients'] == 1
    assert nq['reported_sensitivity_fraction'] == sensitivity
    assert nq['upper_bound_fraction'] is None and nq['measured_fraction'] is None
    assert nq['measured_log10_reduction'] is None
    row = next(r for r in mrd.summary(data, D['pooled_visits']) if r['visit'] == 'TP1')
    assert row['positive_nonquantifiable'] == 1 and row['positive_nq_with_bound'] == 0
    assert row['positive_nq_with_sensitivity'] == int(sensitivity is not None)
    assert row['reported_sensitivity_counts'] == ([] if sensitivity is None else [dict(fraction=sensitivity, patients=1)])


@pytest.mark.parametrize('value', ['Positive NQ <0', 'Positive NQ <2', 'Positive NQ <nan',
    'Positive NQ <bad', 'Positive NQ <', 'unsupported annotation'])
def test_circall_invalid_annotations_still_block(value):
    with pytest.raises(ClinicalError):
        mrd.parse_annotation(value, 'circall', D)


def test_circall_conflicting_nq_sensitivities_still_block(tmp_path):
    path = tmp_path/'source.xlsx'
    inventory(path, 'circall', [dict(circall_id='001-9001-X-Z', MRD_TP1=v)
                               for v in ['Positive NQ <10-4', 'Positive NQ <10-5']])
    with pytest.raises(ClinicalError, match='conflicting_mrd_metadata'):
        mrd.prepare(path, 'circall', D, duplicate_policy='worst')


def test_circall_nq_sensitivity_is_not_a_trajectory_measurement(tmp_path):
    paths = sources(tmp_path)
    inventory(paths['circall'], 'circall', [dict(circall_id='001-9001-X-Z',
              MRD_TP1='Positive NQ <5.10-5', MRD_TP2=.001)])
    a = arguments(cli(paths))
    evaluated = {c: evaluate(c, a, D, load_rules(a.rules)) for c in ('retrospective', 'circall')}
    result, prepared, _ = evaluated['circall']
    assert result['status'] == 'complete'
    fig = reporting.mrd_figure(prepared['mrd'], 'circall', a, D)
    assert sorted(float(c.get_offsets()[0, 1]) for c in fig.axes[0].collections) == [.001, 1.]
    assert not fig.axes[0].lines
    assert 'Positive NQ: counted, not positioned' in [t.get_text() for t in fig.axes[0].get_legend().get_texts()]
    plt.close(fig)
    pooled, prepared = combined_results(evaluated, a, D)['pooled']
    assert pooled['status'] == 'complete'
    nq = next(r for r in prepared['mrd'] if r['status'] == 'positive_nonquantifiable')
    assert nq['reported_sensitivity_fraction'] == 5e-5 and nq['measured_fraction'] is None
    fig = reporting.mrd_figure(prepared['mrd'], 'pooled', a, D)
    values = [float(c.get_offsets()[0, 1]) for c in fig.axes[0].collections]
    assert a.mrd_positive_nq_level in values and 5e-5 not in values
    plt.close(fig)


@pytest.mark.parametrize('drop,duplicate', [(['MRD_IgTCR'], None), ([], 'patient_id')])
def test_header_validation(tmp_path, drop, duplicate):
    path = tmp_path/'source.xlsx'
    inventory(path, 'retrospective', drop=drop, duplicate=duplicate)
    with pytest.raises(ClinicalError):
        mrd.prepare(path, 'retrospective', D, duplicate_policy='worst')


def test_unknown_cache_and_intentional_population(tmp_path):
    path = tmp_path/'source.xlsx'
    inventory(path, 'retrospective', [dict(patient_id='P1', timepoint='tp1', specimen_type='bone marrow', MRD_IgTCR='=1e-4')])
    data, coverage = mrd.prepare(path, 'retrospective', D, duplicate_policy='worst')
    assert data[0]['status'] == 'missing' and coverage['source_cache_unavailable'] == 1


def test_count_baseline_full_range_zeros_and_no_normalization(tmp_path):
    path = tmp_path/'counts.xlsx'
    count_source(path, 'retrospective')
    data, _ = counts.prepare(path, 'retrospective', D, baseline_day_max=1, baseline_selection='latest', overlay_max_day=8)
    table = counts.summary(data, ['blast'], overlay_max_day=8)[0]
    assert table['measurements'] == 6 and table['zero_counts'] == 1
    assert table['plotted_full_range_measurements'] == 5 and table['plotted_early_measurements'] == 3
    assert table['first_recorded_day'] == -2 and table['last_recorded_day'] == 29
    assert [r['value'] for r in data] == [9., 8., 0., 1., .5, .1]
    assert not data[0]['selected_for_plot'] and data[1]['display_day'] == 1
    all_data, _ = counts.prepare(path, 'retrospective', D, baseline_day_max=1, baseline_selection='all', overlay_max_day=8)
    assert all(r['selected_for_plot'] for r in all_data)


@pytest.mark.parametrize('options', [{'duplicate':True}, {'invalid':True}])
def test_invalid_count_rows(tmp_path, options):
    path = tmp_path/'counts.xlsx'
    count_source(path, 'circall', **options)
    with pytest.raises(ClinicalError):
        counts.prepare(path, 'circall', D, baseline_day_max=1, baseline_selection='latest', overlay_max_day=8)


def test_count_missing_cache_and_invalid_day(tmp_path):
    path = tmp_path/'counts.xlsx'
    count_source(path, 'retrospective', [('PRIVATE_SYNTHETIC', 1, '=1+1')])
    data, states = counts.prepare(path, 'retrospective', D, baseline_day_max=1, baseline_selection='latest', overlay_max_day=8)
    assert data[0]['value'] is None and states['blast_cache_unavailable'] == 1
    count_source(path, 'retrospective', [('PRIVATE_SYNTHETIC', 1.5, 1)])
    with pytest.raises(ClinicalError, match='invalid_measured_day'):
        counts.prepare(path, 'retrospective', D, baseline_day_max=1, baseline_selection='latest', overlay_max_day=8)


def test_pool_denominators_figure_positions_and_zeros(tmp_path):
    paths = sources(tmp_path)
    a = arguments(cli(paths))
    rules = load_rules(a.rules)
    evaluated = {c: evaluate(c, a, D, rules) for c in ('retrospective','circall')}
    pooled, prepared = combined_results(evaluated, a, D)['pooled']
    assert all(r['patients'] == 2 for r in pooled['tables']['MRD'])
    assert all(sum(r[s] for s in mrd.STATUSES) == r['patients'] for r in pooled['tables']['MRD'])
    assert not pooled['tables']['Counts'] and pooled['tables']['Models'][0]['status'] == 'disabled'
    fig = reporting.mrd_figure(prepared['mrd'], 'pooled', a, D)
    assert fig.axes[0].get_yscale() == 'log'
    assert not fig.texts and fig.axes[0].get_title() == ''
    assert all('(n=' not in t.get_text() for t in fig.axes[0].get_legend().get_texts())
    plt.close(fig)
    data = evaluated['retrospective'][1]['counts']
    fig = reporting.count_figure(data, 'blast', a, D)
    assert fig.axes[0].get_yscale() == 'log' and fig.axes[0].get_title() == ''
    assert max(fig.axes[0].lines[0].get_xdata()) == 29
    assert not fig.texts
    plt.close(fig)


def test_population_keys_are_separate_across_modalities(tmp_path):
    paths = sources(tmp_path)
    a = arguments(cli(paths))
    _, prepared, _ = evaluate('circall', a, D, load_rules(a.rules))
    assert {r['subject_hash'] for r in prepared['mrd']}.isdisjoint({r['subject_hash'] for r in prepared['counts']})


def test_full_count_range_includes_late_zero_and_mrd_range_has_no_artificial_baseline(tmp_path):
    paths = sources(tmp_path)
    a = arguments(cli(paths))
    count_source(paths['retrospective_blasts'], 'retrospective', [('PRIVATE_SYNTHETIC', 1, 10), ('PRIVATE_SYNTHETIC', 29, 0)])
    _, prepared, _ = evaluate('retrospective', a, D, load_rules(a.rules))
    fig = reporting.count_figure(prepared['counts'], 'blast', a, D)
    assert fig.axes[0].get_xlim()[1] >= 29
    plt.close(fig)
    fig = reporting.mrd_figure(prepared['mrd'], 'retrospective', a, D)
    assert fig.axes[0].get_ylim()[1] == pytest.approx(.003)
    plt.close(fig)


def test_identical_prepared_observations_match_archived_synthetic_reference(tmp_path):
    reference = json.loads((ROOT/'tests/fixtures/synthetic_disease_methods_reference.json').read_text())
    paths = sources(tmp_path)
    a = arguments(cli(paths))
    evaluated = {c: evaluate(c, a, D, load_rules(a.rules)) for c in ('retrospective','circall')}
    for cohort, (_, prepared, _) in evaluated.items():
        actual = sorted([(r['visit'], r['status'], r['measured_fraction'], r['upper_bound_fraction']) for r in prepared['mrd']])
        assert [list(r) for r in actual] == reference['mrd_observations'][cohort]
        actual = counts.summary(prepared['counts'], D['counts'][cohort]['sheets'], overlay_max_day=8)
        for row, old in zip(actual, reference['counts_summary'][cohort], strict=True):
            for new_name, old_name in [('source_rows','source_rows'), ('patients_in_source','patients_in_sheet'),
                                       ('patients_with_measurements','patients_with_measurements'), ('measurements','measurements'),
                                       ('missing_counts','missing_counts'), ('zero_counts','zero_counts'),
                                       ('plotted_full_range_measurements','plotted_measurements'),
                                       ('earlier_diagnostic_measurements_not_plotted','earlier_diagnostic_measurements_not_plotted'),
                                       ('first_recorded_day','first_day'), ('last_recorded_day','last_day')]:
                assert row[new_name] == old[old_name]
    pooled, _ = combined_results(evaluated, a, D)['pooled']
    old_rows = [r for r in reference['pooled_summary'] if r['cohort'] == 'pooled']
    for row in pooled['tables']['MRD']:
        for status in mrd.STATUSES:
            old = next(r for r in old_rows if r['timepoint'] == row['visit'] and r['status'] == status)
            assert row[status] == old['patients'] and row['patients'] == old['denominator']


def test_workbook_tiny_display_levels_do_not_format_as_zero(tmp_path):
    from openpyxl import load_workbook
    paths = sources(tmp_path)
    a = arguments(cli(paths))
    result, _, _ = evaluate('retrospective', a, D, load_rules(a.rules))
    path = tmp_path/'report.xlsx'
    reporting.workbook(path, result, D, vars(a))
    b = load_workbook(path)
    try:
        values = [c for row in b['Definitions'] for c in row if c.value == 1e-8]
        assert values and all('E+' in c.number_format for c in values)
    finally:
        b.close()
