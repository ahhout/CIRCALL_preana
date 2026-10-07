import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pandas as pd

from analysis.sample_analysis import pooled
from analysis.sample_analysis.stats_workbooks import build
from tests.sample_analysis.test_shared_analyses import fixture


class PooledTests(unittest.TestCase):
    def test_pooled_values_counts_scope_and_controls(self):
        frame = fixture()
        extra = frame.iloc[[0]].copy()
        extra['timepoint'] = 'tp0,5'
        extra['dna_total_ng'] = 999999
        frame = pd.concat([frame, extra], ignore_index=True)
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            with patch('analysis.sample_analysis.analyses.longitudinal_tables', return_value=({}, [])) as model:
                pooled.run(frame, output, ['yield', 'volumes', 'longitudinal'], ['diag', 'tp1'])
            patients, controls, cohort, times, _ = model.call_args.args
            self.assertEqual(len(patients), 24)
            self.assertEqual(patients.patient_key.nunique(), 12)
            self.assertEqual(len(controls), 6)
            self.assertEqual(cohort, 'combined')
            self.assertEqual(times, ['diag', 'tp1'])
            summary = pd.read_csv(output / 'yield.csv')
            overall = summary.loc[summary.timepoint.eq('Overall') & summary.measurement.eq('dna_total_ng')].iloc[0]
            self.assertEqual(overall.measured_records, 24)
            self.assertEqual(overall.measured_patients, 12)
            self.assertEqual(overall['mean'], 9.5)
            correlations = pd.read_csv(output / 'correlations.csv')
            self.assertFalse(correlations.variable_x.eq('elution_volume_uL').any())
            self.assertEqual(set(correlations.loc[correlations.timepoint.eq('Overall'), 'paired_sample_count']), {24})

    def test_combined_workbook_uses_pooled_results(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pd.DataFrame([{'cohort': 'combined', 'status': 'complete'}]).to_csv(root/'analysis_status.csv', index=False)
            (root/'pooled').mkdir()
            pooled_values = pd.DataFrame({'cohort': ['combined'], 'mean': [9.5]})
            pooled_values.to_csv(root/'pooled/yield.csv', index=False)
            paths = build(root)
            self.assertEqual(len(paths), 3)
            pd.testing.assert_frame_equal(pd.read_excel(paths[2], sheet_name='yield'), pooled_values)
            with self.assertRaises(FileExistsError):
                build(root)

    def test_unshared_timepoint_rejected(self):
        with self.assertRaises(ValueError):
            pooled.run(fixture(), Path('unused'), ['yield'], ['d4'])
