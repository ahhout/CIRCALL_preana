import unittest
from unittest.mock import patch

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from analysis.sample_analysis import statistical_plots as plots
from analysis.sample_analysis.policies import PRIMARY


class StatisticalPlotTests(unittest.TestCase):
    def tearDown(self):
        plt.close('all')

    def data(self):
        patients=pd.DataFrame({'patient_key':['a','a','b','a'],
            'timepoint':['diag','diag','diag','tp1'],PRIMARY:[1.,100.,10.,5.]})
        controls=pd.DataFrame({PRIMARY:[2.,4.]})
        return patients,controls

    def test_patient_median_display_uses_log_medians(self):
        patients,controls=self.data()
        before=patients.copy(deep=True)
        sample=plots.log_values(patients,controls,['Control','diag'],'sample')
        median=plots.log_values(patients,controls,['Control','diag'],'patient_median')
        np.testing.assert_allclose(sample['diag'],[0,2,1])
        np.testing.assert_allclose(median['diag'],[1,1])
        np.testing.assert_allclose(median['Control'],np.log10([2,4]))
        pd.testing.assert_frame_equal(patients,before)

    def test_welch_uses_adjusted_p_and_validates_counts(self):
        patients,controls=self.data()
        table=pd.DataFrame([dict(bin_a='Control',bin_b='diag',n_a=2,n_b=3,
                                 unit='sample',p_value=.001,p_adj_bh=.125)])
        with patch.object(plots,'save') as save:
            plots.welch_plot(table,patients,controls,'unused.png','Example',diagnosis_as_d1=True)
        fig=save.call_args.args[0]
        self.assertIn('0.125',[t.get_text() for t in fig.axes[1].texts])
        self.assertEqual([t.get_text() for t in fig.axes[0].get_yticklabels()],['Controls  (n=2)','D1 (diagnosis)  (n=3)'])
        table.loc[0,'n_b']=2
        with self.assertRaisesRegex(ValueError,'counts differ'):
            plots.welch_plot(table,patients,controls,'unused.png','Example',diagnosis_as_d1=True)

    def test_mixed_ratio_direction_intervals_and_zero_precision_label(self):
        table=pd.DataFrame([dict(timepoint_a='diag',timepoint_b='tp1',fold_change=.5,
                                 ci95_low_fc=.25,ci95_high_fc=.75,p_adj=0.)])
        before=table.copy(deep=True)
        with patch.object(plots,'save') as save:
            plots.comparison_plot(table,'unused.png','Example',mixed=True,diagnosis_as_d1=False,
                                  counts={'diag':20,'tp1':12})
        fig=save.call_args.args[0];ax=fig.axes[0]
        self.assertEqual(ax.get_yticklabels()[0].get_text(),'TP1 / Diagnosis')
        self.assertEqual(ax.get_xscale(),'log')
        self.assertIn('0.50 (0.25–0.75)',[t.get_text() for t in ax.texts])
        self.assertIn('0 [precision limit]',[t.get_text() for t in ax.texts])
        self.assertIn('12 / 20',[t.get_text() for t in ax.texts])
        pd.testing.assert_frame_equal(table,before)

    def test_rank_plot_preserves_cliffs_delta_direction(self):
        table=pd.DataFrame([dict(bin_a='diag',bin_b='tp1',cliffs_delta=.7,p_adj_bh=.2,n_a=20,n_b=12)])
        with patch.object(plots,'save') as save:
            plots.comparison_plot(table,'unused.png','Example',mixed=False,diagnosis_as_d1=False)
        ax=save.call_args.args[0].axes[0]
        self.assertEqual(ax.get_yticklabels()[0].get_text(),'Diagnosis vs TP1')
        self.assertIn('+0.70',[t.get_text() for t in ax.texts])
        self.assertIn('A tends higher',ax.get_xlabel())
