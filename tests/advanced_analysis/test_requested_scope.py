"""Requested endpoints, plasma-only pairing and time-of-day associations."""
from datetime import time
from types import SimpleNamespace

import numpy as np
import pytest

from analysis.advanced_analysis.step_01_prepare import prepare
from analysis.advanced_analysis.schema import comparisons, outcome_frame, predictors
from analysis.advanced_analysis.step_02_analyze import analyze, pairs
from analysis import association_methods as engine
from tests.fixtures.advanced_analysis import D, fixture, row, sample, settings






@pytest.mark.parametrize('cohort,total', [('retrospective', 30), ('circall', 31)])
def test_exact_requested_matrix_and_unadjusted_engine_results(tmp_path, cohort, total):
    path = tmp_path/'source.xlsx'
    fixture(path, cohort, [sample(i) for i in range(1, 9)])
    frame, counts, _, issues = prepare(path, cohort, D)
    assert not issues
    result, _, _ = analyze(frame, cohort, settings(), D, counts=counts)
    expected = set(comparisons(D, cohort))
    assert len(expected) == total
    for table in ('Coverage', 'Associations'):
        assert {(r['outcome'], r['predictor']) for r in result['tables'][table]} == expected
        assert len(result['tables'][table]) == total
    assert all('p_adj_bh' not in r for rows in result['tables'].values() for r in rows)
    if cohort == 'retrospective':
        assert not any(r['predictor'] == 'tumor_fraction_percent' for r in result['tables']['Coverage'])
    for outcome in D['outcomes']:
        variable = 'dna_concentration_ng_per_ul' if outcome == 'cfdna_fraction' else 'peripheral_blast_percent'
        p = next(p for p in predictors(D) if p.variable == variable)
        _, expected_fit = engine.fit_regression(pairs(outcome_frame(frame, outcome), p), p)
        actual = next(r for r in result['tables']['Associations'] if (r['outcome'], r['predictor']) == (outcome, variable))
        reference = expected_fit.loc[expected_fit.term.eq(variable)].iloc[0]
        assert actual['p_value'] == pytest.approx(reference.p_value)
        assert actual['coefficient'] == pytest.approx(reference.coefficient)


def test_no_retrospective_nonplasma_or_followup_borrowing(tmp_path):
    plasma = sample(1)
    for field in ('diag_blood_wbc_max_x10*9/L', 'Hb_g_per_dL', 'platelets_10e9_per_L', 'genetic_subtype'):
        plasma[field] = None
    path = tmp_path/'source.xlsx'
    fixture(path, rows=[plasma, dict(sample(1), specimen_type='blood pellet'),
                       dict(sample(1), specimen_type='bone marrow'), dict(sample(1), timepoint='tp1')])
    frame, _, evidence, issues = prepare(path, 'retrospective', D)
    assert not issues and len(evidence) == 1
    assert frame[['gb_per_l', 'Hb_g_per_dL', 'platelets_10e9_per_L', 'genetic_subtype', 'tumor_fraction_percent']].isna().all().all()


def test_one_selected_sample_for_all_outcomes_and_handling_values(tmp_path):
    first = sample(1)
    second = dict(sample(1), sample_id='SYNTHETIC_SECOND', dna_total_ng=None,
                  cfdna_ng_per_ml_plasma=100, sampling_time=time(13), corticoide_pre_tt='other')
    path = tmp_path/'source.xlsx'
    fixture(path, 'circall', [first, second])
    selected_both = set()
    for seed in range(12):
        frame, _, evidence, issues = prepare(path, 'circall', D, sample_selection_seed=seed)
        assert not issues  # Sample-specific values need not be concordant across visits.
        selected = next(r for r in evidence if r['selected_sample'])
        selected_both.add(selected['row'])
        for field in D['outcomes']:
            expected = selected['outcomes'][field]
            assert np.isnan(frame[field].iat[0]) if expected is None else frame[field].iat[0] == expected
        assert frame.sampling_time.iat[0] == selected['sampling_time']
    assert len(selected_both) == 2


def test_morning_afternoon_is_categorical_and_noon_boundary(tmp_path):
    path = tmp_path/'source.xlsx'
    fixture(path, 'circall', [sample(i) for i in range(1, 9)])
    frame, _, _, issues = prepare(path, 'circall', D)
    assert not issues and set(frame.sampling_time) == {'Morning', 'Afternoon'}
    result, _, _ = analyze(frame, 'circall', settings(), D)
    tests = [r for r in result['tables']['Associations'] if r['predictor'] == 'sampling_time']
    assert len(tests) == 5 and all(r['term'] == 'overall predictor' for r in tests)
    assert all(r['coefficient'] is None and 'C(sampling_time)' in r['formula'] for r in tests)


@pytest.mark.parametrize('changes,reason', [(dict(sampling_time='morning?'), 'invalid_sampling_time'),
                                         (dict(cfdna_fraction=1.2), 'invalid_outcome')])
def test_invalid_new_fields_do_not_silently_enter_models(tmp_path, changes, reason):
    path = tmp_path/'source.xlsx'
    fixture(path, 'circall', [dict(sample(1), **changes)])
    assert any(i['reason'] == reason for i in prepare(path, 'circall', D)[3])


def test_pooled_scope_is_only_requested_intersection(tmp_path):
    frames = {}
    for scope in ('retrospective', 'circall'):
        path = tmp_path/f'{scope}.xlsx'
        fixture(path, scope, [sample(i) for i in range(1, 9)])
        frames[scope] = prepare(path, scope, D)[0]
    import pandas as pd
    result, models, residuals = analyze(pd.concat(frames.values()), 'pooled', settings(), D, cohorts=frames)
    assert {(r['outcome'], r['predictor']) for r in result['tables']['Coverage']} == (
        set(comparisons(D, 'retrospective')) & set(comparisons(D, 'circall')))
    assert not result['tables']['Associations'] and not models and not residuals


def test_diagnostic_axes_identify_the_actual_outcome(tmp_path, monkeypatch):
    path = tmp_path/'source.xlsx'
    fixture(path, 'circall', [sample(i) for i in range(1, 9)])
    frame = prepare(path, 'circall', D)[0]
    p = next(p for p in predictors(D) if p.variable == 'peripheral_blast_percent')
    model, _ = engine.fit_regression(pairs(outcome_frame(frame, 'dna_total_ng'), p), p)
    labels = []
    def inspect(figure, path):
        labels.extend(ax.get_xlabel() for ax in figure.axes)
        import matplotlib.pyplot as plt
        plt.close(figure)
    monkeypatch.setattr(engine, '_save_figure', inspect)
    engine.plot_assumptions(model, tmp_path, outcome_label='Total extracted DNA')
    assert labels.count('Fitted log10(Total extracted DNA)') == 2
    assert not any('cfDNA' in label for label in labels)
