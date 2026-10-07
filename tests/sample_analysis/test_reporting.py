"""Plot contracts: canonical labels, shared axes, and pooled controls."""
import unittest
from unittest.mock import patch

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from analysis.sample_analysis import reporting
from analysis.sample_analysis.policies import PRIMARY
from tests.sample_analysis.test_shared_analyses import fixture


class ReportingTests(unittest.TestCase):
    def tearDown(self):
        plt.close('all')

    def test_timepoint_filter_is_explicit_and_preserves_input(self):
        source = pd.DataFrame({'timepoint': ['Control','diag','d1','d4','d8','d15','tp1','tp2','tp0,5','tp3',None]})
        before = source.copy(deep=True)
        data = reporting.plot_data(source, diagnosis_as_d1=True)
        self.assertEqual(data.plot_timepoint.tolist(), ['Control','D1','D1','D4','D8','D15','TP1 (D29)','TP2 (D71)'])
        self.assertNotIn('diag', reporting.plot_data(source).timepoint.tolist())
        pd.testing.assert_frame_equal(before, source)

    def test_boxes_share_axes_and_controls_are_not_duplicated(self):
        frame = fixture()
        extra = frame.iloc[[0]].copy();extra['timepoint'] = 'tp3'
        frame = pd.concat([frame, extra], ignore_index=True)
        with patch.object(reporting, 'save') as save:
            reporting.timepoint_plot(frame, ['retrospective','circall'], PRIMARY, 'unused.png', diagnosis_as_d1=True)
        fig = save.call_args.args[0]
        self.assertEqual(len(fig.axes), 1)
        ax = fig.axes[0]
        self.assertEqual([label.get_text().split('\n')[0] for label in ax.get_xticklabels()], ['Control','D1','TP1 (D29)'])
        self.assertEqual(len(ax.patches), 5)  # one control box, two per patient timepoint
        self.assertEqual([t.get_text() for t in ax.get_legend().get_texts()], ['Retrospective','Circall'])
        centers = [p.get_path().vertices[:,0].min()+np.ptp(p.get_path().vertices[:,0])/2 for p in ax.patches]
        self.assertLess(centers[1], 1)
        self.assertGreater(centers[2], 1)

    def test_other_multi_cohort_plots_use_one_axis(self):
        frame = fixture()
        from analysis.sample_analysis.analyses import availability
        cases = [
            (reporting.volume_plot, (frame, ['retrospective','circall'], 'volume_ml', 'unused.png')),
            (reporting.inventory_plot, (availability(frame), ['retrospective','circall'], 'unused.png')),
            (reporting.correlation_plot, (frame, ['retrospective','circall'], 'volume_ml', PRIMARY, 'unused.png')),
        ]
        for function,args in cases:
            with self.subTest(plot=function.__name__), patch.object(reporting, 'save') as save:
                function(*args, diagnosis_as_d1=True)
                self.assertEqual(len(save.call_args.args[0].axes), 1)

    def test_blood_pellet_boxes_show_timepoints_without_plasma(self):
        frame = fixture()
        pellet = frame.loc[frame.cohort.eq('circall')].copy()
        pellet['compartment'] = 'blood pellet'
        data = pd.concat([frame, pellet], ignore_index=True)
        with patch.object(reporting, 'save') as save:
            reporting.blood_pellet_plot(data, ['circall'], 'dna_total_ng', 'unused.png')
        ax = save.call_args.args[0].axes[0]
        self.assertEqual([t.get_text() for t in ax.get_xticklabels()], ['D1\nn=6', 'TP1 (D29)\nn=6'])
        self.assertEqual(ax.get_yscale(), 'linear')
        self.assertEqual(len(ax.patches), 2)

    def test_default_longitudinal_plot_includes_diagnosis(self):
        from analysis.cli import arguments
        args = arguments(['--circall', 'explicit.xlsx'])
        self.assertTrue(args.plot_diagnosis_as_d1)
        self.assertFalse(arguments(['--circall', 'explicit.xlsx', '--no-plot-diagnosis-as-d1']).plot_diagnosis_as_d1)
        with patch.object(reporting, 'save') as save:
            reporting.timepoint_plot(fixture(), ['retrospective','circall'], PRIMARY, 'unused.png',
                                     longitudinal=True, diagnosis_as_d1=args.plot_diagnosis_as_d1)
        labels = [t.get_text().split('\n')[0] for t in save.call_args.args[0].axes[0].get_xticklabels()]
        self.assertIn('D1', labels)

    def test_pooled_boxes_keep_cohort_dot_colors_and_one_control_group(self):
        from matplotlib.colors import to_rgba
        frame = fixture()
        before = frame.copy(deep=True)
        with patch.object(reporting, 'save') as save:
            reporting.timepoint_plot(frame, ['retrospective','circall'], PRIMARY, 'unused.png',
                                     diagnosis_as_d1=True, combine_cohorts=True)
        ax = save.call_args.args[0].axes[0]
        self.assertEqual(len(ax.patches), 3)
        self.assertEqual([len(c.get_offsets()) for c in ax.collections], [6, 12, 12])
        colors = {tuple(color) for color in ax.collections[1].get_facecolors()}
        self.assertEqual(colors, {to_rgba(reporting.COLORS[c], alpha=.65) for c in ('retrospective','circall')})
        pd.testing.assert_frame_equal(frame, before)


if __name__ == '__main__':
    unittest.main()
