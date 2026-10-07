"""Patient bootstrap dependence, box-summary equivalence and sparse-visit display."""
import unittest
from unittest.mock import patch

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from analysis.cli import arguments
from analysis.pipeline import option_argv
from analysis.sample_analysis import longitudinal_trends as trends, reporting
from analysis.sample_analysis.policies import PRIMARY, pooled_controls
from tests.sample_analysis.test_shared_analyses import fixture


class LongitudinalTrendTests(unittest.TestCase):
    def tearDown(self):
        plt.close('all')

    def summarize(self, frame, cohorts=('retrospective', 'circall')):
        return trends.summarize(frame, cohorts, diagnosis_as_d1=True,
                                resamples=300, seed=42, method='percentile')

    def test_whole_patient_draw_preserves_visit_dependence(self):
        matrix = np.array([[1., 10.], [3., 30.], [7., 70.]])
        draws = trends.bootstrap_medians(matrix, resamples=300, seed=42)
        np.testing.assert_allclose(draws[:, 1], 10*draws[:, 0])
        np.testing.assert_array_equal(draws, trends.bootstrap_medians(matrix, resamples=300, seed=42))

    def test_missing_visits_are_not_imputed(self):
        draws = trends.bootstrap_medians([[1., np.nan], [3., 30.]], resamples=300, seed=42)
        self.assertTrue(np.isnan(draws[:, 1]).any())
        np.testing.assert_array_equal(np.unique(draws[np.isfinite(draws[:, 1]), 1]), [30.])
        self.assertFalse(np.isnan(draws[:, 0]).any())

    def test_matches_box_patient_medians_not_log_medians(self):
        frame = fixture()
        frame.loc[0, PRIMARY] = 1.
        extra = frame.iloc[[0]].copy(); extra[PRIMARY] = 100.
        frame = pd.concat([frame, extra], ignore_index=True)
        before = frame.copy(deep=True)
        patients, summary = self.summarize(frame)
        value = patients['retrospective'].query("patient_key == 'retrospective:0' and plot_timepoint == 'D1'")[PRIMARY].iloc[0]
        self.assertEqual(value, 50.5)
        with patch.object(reporting, 'box_points') as boxes, patch.object(reporting, 'save'):
            reporting.timepoint_plot(frame, ['retrospective', 'circall'], PRIMARY, 'unused.png',
                                     longitudinal=True, diagnosis_as_d1=True)
        # Control, retrospective diagnosis, CIRCALL diagnosis, then TP1 groups.
        for call, (cohort, tp) in zip(boxes.call_args_list[1:],
                [('retrospective', 'D1'), ('circall', 'D1'), ('retrospective', 'TP1 (D29)'), ('circall', 'TP1 (D29)')]):
            row = summary.loc[summary.cohort.eq(cohort) & summary.plot_timepoint.eq(tp)].iloc[0]
            self.assertEqual(row.n_patients, len(call.args[1]))
            self.assertEqual(row['median'], np.median(call.args[1]))
        pd.testing.assert_frame_equal(frame, before)
        _, reordered = self.summarize(frame.sample(frac=1, random_state=12))
        pd.testing.assert_frame_equal(summary, reordered)
        _, single = self.summarize(frame, ['circall'])
        pd.testing.assert_frame_equal(summary.loc[summary.cohort.eq('circall')].reset_index(drop=True), single)

    def test_sparse_tp2_has_points_and_median_but_no_band(self):
        frame = fixture()
        extra = frame.loc[frame.cohort.eq('circall') & frame.timepoint.eq('tp1')].head(3).copy()
        extra['timepoint'] = 'tp2'
        frame = pd.concat([frame, extra], ignore_index=True)
        patients, summary = self.summarize(frame)
        row = summary.loc[summary.plot_timepoint.eq('TP2 (D71)')].iloc[0]
        self.assertEqual(row.n_patients, 3)
        self.assertTrue(np.isnan(row.ci95_low))
        self.assertTrue(np.isnan(row.ci95_high))
        self.assertIn('CIRCALL TP2', row.interval_omission)
        controls = pooled_controls(frame)[PRIMARY].to_numpy()
        with patch.object(reporting, 'save') as save:
            trends.plot(patients, controls, summary, ['retrospective', 'circall'], 'unused.png')
        ax = save.call_args.args[0].axes[0]
        self.assertEqual(ax.get_yscale(), 'log')
        self.assertEqual(len(ax.patches), 0)
        self.assertIn('n=3; no CI', [t.get_text() for t in ax.texts])
        self.assertEqual(sum(len(c.get_offsets()) for c in ax.collections if c.__class__.__name__ == 'PathCollection'), 33)
        bands = [c for c in ax.collections if 'PolyCollection' in c.__class__.__name__]
        self.assertTrue(bands)
        self.assertTrue(all(p.vertices[:, 0].max() < 3 for band in bands for p in band.get_paths()))

    def test_unavailable_and_single_patient_visits(self):
        frame = fixture().iloc[[0]].copy()
        _, summary = self.summarize(frame)
        self.assertEqual(len(summary), 1)
        self.assertEqual(summary.n_patients.iloc[0], 1)
        self.assertTrue(np.isnan(summary.ci95_low.iloc[0]))
        patients, empty = self.summarize(frame.iloc[:0])
        self.assertTrue(empty.empty)
        with patch.object(reporting, 'save'):
            trends.plot(patients, np.array([]), empty, ['retrospective', 'circall'], 'unused.png')

    def test_cli_and_profile_settings_are_exposed_and_validated(self):
        options = {'trend-bootstrap-resamples': 250, 'trend-bootstrap-seed': 17, 'trend-bootstrap-method': 'percentile'}
        args = arguments(['--circall', 'explicit.xlsx', *option_argv(options)])
        self.assertEqual((args.trend_bootstrap_resamples, args.trend_bootstrap_seed, args.trend_bootstrap_method), (250, 17, 'percentile'))
        for argv in [['--trend-bootstrap-resamples', '0'], ['--trend-bootstrap-seed', '-1'], ['--trend-bootstrap-method', 'unknown']]:
            with self.subTest(argv=argv), patch('sys.stderr'), self.assertRaises(SystemExit):
                arguments(['--circall', 'explicit.xlsx', *argv])


def test_canonical_pooled_writer_preserves_summary_and_settings(tmp_path):
    from analysis.sample_analysis import pooled_trend
    from analysis.outputs import SAMPLE_FIGURES
    frame = fixture()
    settings = dict(diagnosis_as_d1=True, resamples=100, seed=42, method='percentile')
    original = dict(settings)
    summary, recorded = pooled_trend.write(frame, tmp_path, settings)
    patients, _ = trends.summarize(frame, ['retrospective', 'circall'], **settings)
    combined = pd.concat(patients.values(), ignore_index=True)
    expected = combined.groupby('plot_timepoint')[PRIMARY].agg(['median', 'count'])
    for row in summary.itertuples():
        assert row.median == expected.loc[row.plot_timepoint, 'median']
        assert row.n_patients == expected.loc[row.plot_timepoint, 'count']
    assert settings == original
    assert recorded['seed'] == 42
    assert 'longitudinal/trendlines_pooled.png' in SAMPLE_FIGURES
    assert (tmp_path/'trendlines_pooled.png').is_file()
    assert 'patient_key' not in (tmp_path/'pooled_trendline_summary.csv').read_text()
    empty, _ = pooled_trend.write(frame.iloc[:0], tmp_path/'empty', settings)
    assert empty.empty
