"""Undefined influence diagnostics are reported without changing model fits."""
import warnings

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
import pytest

from analysis import association_methods as methods


@pytest.mark.parametrize('cohort', [None, 'circall', 'retrospective'])
def test_singleton_category_preserves_fit_and_reports_undefined_diagnostics(tmp_path, monkeypatch, cohort):
    data = pd.DataFrame({'group':['A']*4+['B']*3+['C'], 'y':[1,3,2,5,2,5,4,7]})
    model = smf.ols('y ~ C(group)', data).fit()
    coefficients = model.params.copy()
    pvalues = model.pvalues.copy()
    labels = []
    def inspect(figure, path):
        labels.extend(t.get_text() for ax in figure.axes for t in ax.texts)
        if cohort:
            from matplotlib.colors import to_rgba
            from analysis.utils.plot_style import COHORT_COLORS, COHORT_MARKERS
            axis = figure.axes[0]
            assert not axis.spines['top'].get_visible()
            if path.name == 'qq_plot.png':
                assert axis.lines[0].get_color() == COHORT_COLORS[cohort]
                assert axis.lines[0].get_marker() == COHORT_MARKERS[cohort]
            else:
                assert np.allclose(axis.collections[0].get_facecolors()[0][:3], to_rgba(COHORT_COLORS[cohort])[:3])
        plt.close(figure)
    monkeypatch.setattr(methods, '_save_figure', inspect)
    from analysis.utils import plot_style
    monkeypatch.setattr(plot_style, 'save_figure', inspect)
    with warnings.catch_warnings():
        warnings.simplefilter('error', RuntimeWarning)
        leverage, standardized, cooks = methods.influence_diagnostics(model)
        diagnostics = methods.model_diagnostics(model).iloc[0]
        methods.plot_assumptions(model, tmp_path, cohort=cohort)
    assert abs(leverage[-1]-1) < 1e-12
    assert np.isnan(standardized[-1]) and np.isnan(cooks[-1])
    assert np.isfinite(standardized[:-1]).all() and np.isfinite(cooks[:-1]).all()
    assert diagnostics.undefined_studentized_residuals == diagnostics.undefined_cooks_distances == 1
    assert any('Undefined studentized residuals: 1' in label for label in labels)
    pd.testing.assert_series_equal(coefficients, model.params)
    pd.testing.assert_series_equal(pvalues, model.pvalues)
    assert model.nobs == 8


def test_zero_residual_variance_is_unavailable_without_runtime_warning():
    model = smf.ols('y ~ x', pd.DataFrame({'x':[1,2,3,4], 'y':[0,0,0,0]})).fit()
    with warnings.catch_warnings():
        warnings.simplefilter('error', RuntimeWarning)
        _, standardized, cooks = methods.influence_diagnostics(model)
        diagnostics = methods.model_diagnostics(model).iloc[0]
    assert np.isnan(standardized).all() and np.isnan(cooks).all()
    assert diagnostics.undefined_studentized_residuals == 4
    assert np.isnan(diagnostics.max_cooks_distance)
