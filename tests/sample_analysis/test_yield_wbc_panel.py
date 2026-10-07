"""Composite rendering preserves the source observations and aligns the visit axes."""
from unittest.mock import patch

import numpy as np
import pandas as pd

from analysis.outputs import SAMPLE_FIGURES
from analysis.sample_analysis import pooled_trend, reporting, yield_wbc_panel
from tests.sample_analysis.test_shared_analyses import fixture


def test_composite_preserves_wbc_days_and_values(tmp_path):
    frame = fixture()
    settings = dict(diagnosis_as_d1=True, resamples=100, seed=42, method='percentile')
    summary, _ = pooled_trend.write(frame, tmp_path/'pooled', settings)
    counts = pd.DataFrame(dict(measurement=['wbc']*4, patient_key=['synthetic']*4,
        day=[1, 4, 29, 79], display_day=[1, 4, 29, 79],
        count_x10_9_per_L=[100., 0., 2., 5.], selected_for_plot=[True]*4))
    before = counts.copy(deep=True)
    with patch.object(reporting.plt, 'close') as close:
        result = yield_wbc_panel.write(frame, summary, counts, settings,
            {'diagnostic_baseline_day_max': 1}, tmp_path/'panels')
    fig = close.call_args.args[0]
    try:
        top, bottom = fig.axes
        assert top.get_yscale() == bottom.get_yscale() == 'log'
        np.testing.assert_allclose(bottom.lines[0].get_xdata(), [1, 2, 5, 6+8/42])
        np.testing.assert_array_equal(top.get_xticks(), bottom.get_xticks())
        assert top.get_xlim() == bottom.get_xlim()
        fig.canvas.draw()
        for tick in top.get_xticks():
            assert top.transData.transform((tick, 1))[0] == bottom.transData.transform((tick, 1))[0]
        np.testing.assert_allclose(bottom.lines[0].get_ydata(), [100., np.nan, 2., 5.], equal_nan=True)
        assert [t.get_text() for t in bottom.get_xticklabels()] == ['Control', 'D1', 'D4', 'D8', 'D15', 'TP1 (D29)', 'TP2 (D71)']
        assert bottom.get_title() == ''
        assert result['wbc_points_retained'] == 4
        pd.testing.assert_frame_equal(counts, before)
        for ext in ['png', 'pdf']:
            name = f'yield_wbc_panels.{ext}'
            assert (tmp_path/'panels'/name).is_file()
            assert f'longitudinal/{name}' in SAMPLE_FIGURES
    finally:
        reporting.plt.close(fig)


def test_aligned_days_preserves_intermediate_and_late_measurements():
    np.testing.assert_allclose(yield_wbc_panel.aligned_days([1, 4, 8, 15, 29, 71], offset=0), np.arange(6))
    np.testing.assert_allclose(yield_wbc_panel.aligned_days([2.5, 6, 11.5, 22, 50, 79], offset=1), [1.5, 2.5, 3.5, 4.5, 5.5, 6+8/42])
