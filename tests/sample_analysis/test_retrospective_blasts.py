"""Synthetic cohort ingestion, eligibility, identity separation and privacy checks."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from openpyxl import Workbook

from analysis.cli import arguments
from analysis.sample_analysis import blood_counts, retrospective_blasts
from analysis.sample_analysis.runner import selection


class RetrospectiveBlastTests(unittest.TestCase):
    def workbook(self, rows):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        path = Path(tmp.name) / 'synthetic.xlsx'
        book = Workbook()
        sheet = book.active
        sheet.title = 'blast'
        sheet.append(['lastname', 'day', 'blast_count_x10*9/L'])
        for row in rows:
            sheet.append(row)
        book.save(path)
        book.close()
        return path

    def test_raw_counts_zeros_missing_and_non_day1_subjects_survive(self):
        path = self.workbook([['synthetic_a', -2, '4,5'], ['synthetic_a', 3, 0],
                              ['synthetic_b', 20, 9], ['synthetic_c', None, None]])
        frame = retrospective_blasts.observations(path, unit='x10^9/L')
        prepared = blood_counts.assign_baseline(frame, baseline_day_max=1)
        summary = blood_counts.summary_table(prepared, measurements=('blast',)).iloc[0]
        self.assertEqual(summary.measurements, 3)
        self.assertEqual(summary.plotted_measurements, 3)
        self.assertEqual(summary.patients_with_measurements, 2)
        self.assertEqual(summary.zero_counts, 1)
        self.assertEqual(summary.missing_counts, 1)
        self.assertEqual(prepared.loc[prepared.status.eq('measured'), 'count_x10_9_per_L'].tolist(), [4.5, 0, 9])
        self.assertEqual(prepared.loc[prepared.status.eq('measured'), 'display_day'].tolist(), [1, 3, 20])

    def test_surname_matching_preserves_case_and_trims_whitespace(self):
        path = self.workbook([['synthetic_a', 1, 2], [' synthetic_a ', 2, 3], ['Synthetic_a', 1, 4]])
        frame = retrospective_blasts.observations(path, unit='x10^9/L')
        self.assertEqual(frame.patient_key.nunique(), 2)
        self.assertFalse(frame.patient_key.str.contains('synthetic', case=False).any())
        self.assertTrue(frame.patient_key.str.startswith('retrospective_blast:').all())

    def test_invalid_input_fails_without_printing_identifier_or_value(self):
        for rows in ([['synthetic_secret', 1, -3]], [['synthetic_secret', 1.5, 3]],
                     [['synthetic_secret', 1, 3], ['synthetic_secret', 1, 4]], [[None, 1, 3]],
                     [['synthetic_secret', None, 3]], [['synthetic_secret', 1, '=1+1']]):
            with self.subTest(rows=rows), self.assertRaises(ValueError) as caught:
                retrospective_blasts.observations(self.workbook(rows), unit='x10^9/L')
            self.assertNotIn('synthetic_secret', str(caught.exception))
        with self.assertRaisesRegex(ValueError, 'explicitly confirmed'):
            retrospective_blasts.observations('unused.xlsx', unit=None)

    def test_retrospective_only_cli_includes_retrospective_mrd_without_circall_counts(self):
        args = arguments(['--analysis', 'kinetics', '--cohort', 'retrospective', '--circall', 'synthetic.xlsx',
                          '--retrospective-blasts', 'synthetic_blasts.xlsx', '--retrospective-blast-unit', 'x10^9/L'])
        cohorts, tasks, inputs = selection(args)
        self.assertEqual(cohorts, ['retrospective'])
        self.assertEqual(tasks, ['kinetics', 'mrd'])
        self.assertNotIn('blood_counts', inputs)
        self.assertIn('retrospective_blasts', inputs)

    def test_row_export_is_not_added_for_retrospective_source(self):
        path = self.workbook([['synthetic_secret', -1, 2], ['synthetic_secret', 4, 0]])
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / 'fresh'
            with patch.object(blood_counts.reporting, 'save', side_effect=lambda fig, path: blood_counts.plt.close(fig)):
                summary = blood_counts.run(None, output, baseline_day_max=1,
                    retrospective_path=path, retrospective_unit='x10^9/L')
            self.assertEqual(summary.cohort.tolist(), ['retrospective'])
            self.assertFalse(list(output.glob('*observations*')))
            for artifact in output.iterdir():
                text = artifact.read_text()
                self.assertNotIn('synthetic_secret', text)
                self.assertNotIn('retrospective_blast:', text)
            with self.assertRaisesRegex(ValueError, 'already exists'):
                blood_counts.run(None, output, baseline_day_max=1,
                    retrospective_path=path, retrospective_unit='x10^9/L')


if __name__ == '__main__':
    unittest.main()
