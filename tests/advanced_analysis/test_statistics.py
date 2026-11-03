from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from analysis.advanced_analysis.statistics import analyze_outcome as analyze, pairs
from analysis.advanced_analysis.reporting import figure, workbook, validate_workbook, COLORS
from analysis import association_methods as engine
from tests.fixtures.associations import toy_cohort
from tests.fixtures.advanced_analysis import D


def args(**changes):
    settings = dict(predictors=['peripheral_blast_percent'], spearman_sensitivity=True, retrospective_wbc_unit='x10^9/L')
    settings.update(changes)
    return SimpleNamespace(**settings)


def frame():
    f = toy_cohort().drop(columns=['blood_sample_ids', 'marrow_sample_ids'])
    f['cohort'] = 'retrospective'
    f['subject_hash'] = [str(i).zfill(64) for i in range(len(f))]
    f['outcome_sample_n'] = f['eligible_sample_n'] = 1
    for p in engine.PREDICTORS:
        f[p.variable+'_sample_n'] = 1
    f.cfdna_ng_per_ml *= np.exp(np.random.default_rng(12).normal(0, .2, len(f)))
    return f


def test_engine_equivalence_complete_pairs_unadjusted_and_spearman():
    f = frame()
    f.loc[:2, 'age_diag'] = np.nan
    f['gb_per_l'] = np.nan
    selected = ['peripheral_blast_percent', 'age_diag', 'gb_per_l', 'sex']
    result, _, _ = analyze(f, 'retrospective', args(predictors=selected), D)
    fitted = {}
    for p in engine.select_predictors(selected):
        data = pairs(f, p)
        model, table = engine.fit_regression(data, p)
        actual = next(r for r in result['tables']['Associations'] if r['predictor'] == p.variable)
        assert actual['n'] == len(data)
        if model is None:
            assert actual['status'] == 'skipped' and 'p_adj_bh' not in actual
            fitted[p.variable] = 1.
        elif p.kind == 'continuous':
            expected = table.loc[table.term.eq(p.variable)].iloc[0]
            for key in ['coefficient', 'ci95_low', 'ci95_high', 'p_value']:
                assert actual[key] == pytest.approx(expected[key], rel=1e-12)
            fitted[p.variable] = actual['p_value']
            assert actual['fold_change'] == pytest.approx(10**(actual['predictor_increment']*expected.coefficient))
        else:
            assert actual['term'] == 'overall predictor' and actual['coefficient'] is None
            assert actual['p_value'] == pytest.approx(table.f_p_value.iat[0])
            fitted[p.variable] = actual['p_value']
    for row in result['tables']['Associations']:
        assert 'p_adj_bh' not in row
    primary = next(r for r in result['tables']['Associations'] if r['predictor'] == 'peripheral_blast_percent')
    p = engine.select_predictors()[0]
    for key, value in engine.spearman_sensitivity(pairs(f, p), p).items():
        assert primary[key] == value
    disabled, _, _ = analyze(f, 'retrospective', args(predictors=selected, spearman_sensitivity=False), D)
    assert [r['p_value'] for r in disabled['tables']['Associations']] == [r['p_value'] for r in result['tables']['Associations']]


@pytest.mark.parametrize('kind', ['empty', 'small', 'constant', 'singular'])
def test_estimability_reasons_and_points(kind):
    f = frame()
    if kind == 'empty':
        f = f.iloc[:0]
    elif kind == 'small':
        f = f.iloc[:2]
    elif kind == 'constant':
        f['peripheral_blast_percent'] = 10
    else:
        f['genetic_subtype'] = [str(i) for i in range(len(f))]
    a = args(predictors=['genetic_subtype'] if kind == 'singular' else ['peripheral_blast_percent'])
    result, models, _ = analyze(f, 'retrospective', a, D)
    test = result['tables']['Associations'][0]
    assert test['status'] == 'skipped' and test['reason']
    p = engine.select_predictors(a.predictors)[0]
    cov = next(c for c in result['tables']['Coverage'] if c['predictor'] == p.variable)
    fig = figure(f, p, models[p.variable], cov, test, 'retrospective', a, D)
    if kind == 'empty':
        assert fig is None
    else:
        assert fig.axes[0].get_yscale() == 'log'
        assert not fig.texts and fig.axes[0].get_title() == ''
        import matplotlib.pyplot as plt
        plt.close(fig)


def test_nonfinite_uncertainty_preserved(monkeypatch):
    f = frame()
    original = engine.smf.ols
    def bad(*a, **kw):
        model = original(*a, **kw).fit()
        model.get_robustcov_results = lambda **kw: SimpleNamespace(bse=np.array([np.inf]), pvalues=np.array([.1]))
        return SimpleNamespace(fit=lambda: model)
    monkeypatch.setattr(engine.smf, 'ols', bad)
    result, _, _ = analyze(f, 'retrospective', args(), D)
    assert 'Nonfinite' in result['tables']['Associations'][0]['reason']


def test_pooling_units_colors_and_no_inference():
    retro = frame()
    circ = frame()
    circ['cohort'] = 'circall'
    circ['sex'] = circ['age_diag'] = np.nan
    both = pd.concat([retro, circ], ignore_index=True)
    a = args(retrospective_wbc_unit='unknown')
    result, models, residuals = analyze(both, 'pooled', a, D, cohorts=dict(retrospective=retro, circall=circ))
    assert not result['tables']['Associations'] and not models and not residuals
    coverage = {r['predictor']:r for r in result['tables']['Coverage']}
    assert 'not explicitly confirmed' in coverage['gb_per_l']['reason']
    assert coverage['sex']['status'] == 'unavailable'
    p = engine.select_predictors()[0]
    fig = figure(both, p, None, coverage[p.variable], None, 'pooled', a, D)
    assert len(fig.axes[0].collections) == 2
    assert all(c in COLORS for c in ('retrospective', 'circall'))
    from matplotlib.colors import to_rgba
    from analysis.plot_style import COHORT_COLORS
    for collection, cohort in zip(fig.axes[0].collections, ['circall', 'retrospective'], strict=True):
        assert np.allclose(collection.get_facecolors()[0][:3], to_rgba(COHORT_COLORS[cohort])[:3])
    assert fig.axes[0].get_ylabel() == 'cfDNA concentration (ng/mL plasma)'
    assert fig.axes[0].get_title() == '' and not fig.texts
    assert [t.get_text() for t in fig.axes[0].texts] == [f'n={len(both)}']
    assert all('(n=' not in t.get_text() for t in fig.axes[0].get_legend().get_texts())
    import matplotlib.pyplot as plt
    plt.close(fig)


def test_zero_counts_predictor_population_and_workbook(tmp_path):
    f = frame()
    f.loc[0, 'cfdna_ng_per_ml'] = 0
    f.loc[1:3, 'age_diag'] = np.nan
    result, _, _ = analyze(f, 'retrospective', args(predictors=['age_diag', 'peripheral_blast_percent']), D)
    counts = {r['predictor']:r for r in result['tables']['Coverage']}
    assert counts['age_diag']['analysis_patients'] == 8
    assert counts['peripheral_blast_percent']['analysis_patients'] == 11
    assert counts['peripheral_blast_percent']['nonpositive_pairs'] == 1
    desc = next(r for r in result['tables']['Descriptions'] if r['predictor'] == 'peripheral_blast_percent')
    assert desc['minimum_cfdna_ng_per_ml'] == 0
    path = tmp_path/'report.xlsx'
    workbook(path, result, D)
    validate_workbook(path, result, D)


def test_backtransformed_fitted_curve_and_historical_box_scale():
    f = frame()
    result, models, _ = analyze(f, 'retrospective', args(), D)
    p = engine.select_predictors()[0]
    cov = next(r for r in result['tables']['Coverage'] if r['predictor'] == p.variable)
    association = result['tables']['Associations'][0]
    fig = figure(f, p, models[p.variable], cov, association, 'retrospective', args(), D)
    line = fig.axes[0].lines[0]
    grid = pd.DataFrame({p.variable:line.get_xdata()})
    expected = models[p.variable].get_robustcov_results(cov_type='HC3').get_prediction(grid).summary_frame()
    assert np.allclose(line.get_ydata(), 10**expected['mean'])
    assert all('plasma_DNA' not in t.get_text() and 'not_recorded' not in t.get_text() for t in fig.texts)
    import matplotlib.pyplot as plt
    plt.close(fig)


@pytest.mark.parametrize('scope', ['retrospective', 'circall', 'pooled'])
@pytest.mark.parametrize('variable', ['gb_per_l', 'tumor_fraction_percent', 'dna_concentration_ng_per_ul'])
def test_log_log_display_preserves_zero_in_analysis(scope, variable):
    f = frame()
    if variable == 'dna_concentration_ng_per_ul':
        f[variable] = np.linspace(1, 100, len(f))
        f[variable+'_sample_n'] = 1
    f.loc[0, variable] = 0
    if scope == 'circall':
        f['cohort'] = 'circall'
    cohorts = None
    if scope == 'pooled':
        circ = f.copy()
        circ['cohort'] = 'circall'
        cohorts = dict(retrospective=f, circall=circ)
        f = pd.concat([f, circ], ignore_index=True)
    a = args(predictors=[variable])
    from analysis.advanced_analysis.schema import predictors
    p = next(p for p in predictors(D) if p.variable == variable)
    result, models, _ = analyze(f, scope, a, D, cohorts=cohorts, selected_predictors=(p,))
    cov = next(r for r in result['tables']['Coverage'] if r['predictor'] == variable)
    association = result['tables']['Associations'][0] if scope != 'pooled' else None
    assert cov['analysis_patients'] == len(f)
    fig = figure(f, p, models.get(variable), cov, association, scope, a, D)
    ax = fig.axes[0]
    assert ax.get_xscale() == ax.get_yscale() == 'log'
    assert sum(len(c.get_offsets()) for c in ax.collections if hasattr(c, 'get_offsets') and c.__class__.__name__ == 'PathCollection') == int(f[variable].gt(0).sum())
    assert not fig.texts and ax.get_title() == ''
    grid = ax.lines[0].get_xdata()
    assert np.all(grid > 0) and np.allclose(np.diff(np.log10(grid)), np.diff(np.log10(grid))[0])
    if scope != 'pooled':
        expected = models[variable].predict(pd.DataFrame({variable: grid}))
        assert np.allclose(ax.lines[0].get_ydata(), 10**expected)
        assert association['n'] == len(f)
    import matplotlib.pyplot as plt
    plt.close(fig)


def test_historical_box_scale():
    f = frame().iloc[:2].copy()
    f['sex'] = 'F'
    f['cfdna_ng_per_ml'] = [1., 100.]
    p = next(p for p in engine.PREDICTORS if p.variable == 'sex')
    result, _, _ = analyze(f, 'retrospective', args(), D)
    cov = next(r for r in result['tables']['Coverage'] if r['predictor'] == 'sex')
    fig = figure(f, p, None, cov, None, 'retrospective', args(), D)
    median_lines = [line for line in fig.axes[0].lines if np.allclose(line.get_ydata(), 10.)]
    assert median_lines  # median(log10([1,100])) back-transforms to 10, not 50.5
    import matplotlib.pyplot as plt
    plt.close(fig)
