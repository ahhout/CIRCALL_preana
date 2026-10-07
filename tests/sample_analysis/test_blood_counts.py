"""Blood count ingestion preserves zeros and missingness without selecting repeats."""
from pathlib import Path
import tempfile
import unittest

from openpyxl import Workbook

from analysis.sample_analysis import blood_counts


class BloodCountTests(unittest.TestCase):
    def workbook(self, rows):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        path = Path(directory.name) / 'counts.xlsx'
        book = Workbook()
        book.remove(book.active)
        for sheet, field in blood_counts.FIELDS.items():
            ws = book.create_sheet(sheet)
            ws.append(['circall_id', 'day', field])
            for row in rows:
                ws.append(row)
        book.save(path)
        book.close()
        return path

    def test_numeric_strings_zeros_and_empty_formula_days(self):
        path = self.workbook([['synthetic_a', -1, '1,04'], ['synthetic_a', 4, 0],
                              ['synthetic_b', -46217, None]])
        data = blood_counts.observations(path)
        measured = data.loc[data.status.eq('measured')]
        self.assertEqual(measured.count_x10_9_per_L.tolist(), [1.04, 0, 1.04, 0])
        self.assertTrue(data.loc[data.status.eq('missing'), 'day'].isna().all())
        self.assertFalse(data.patient_key.str.contains('synthetic').any())
        summary = blood_counts.summary_table(data)
        self.assertEqual(summary.zero_counts.tolist(), [1, 1])
        self.assertEqual(summary.missing_counts.tolist(), [1, 1])

    def test_repeated_patient_day_fails(self):
        path = self.workbook([['synthetic_a', 1, 2], ['synthetic_a', 1, 3]])
        with self.assertRaisesRegex(ValueError, 'Repeated patient/day'):
            blood_counts.observations(path)

    def test_measurement_requires_day_and_identifier(self):
        for row, message in [(['synthetic_a', None, 2], 'invalid day'),
                             ([None, 1, 2], 'Missing patient identifier')]:
            with self.subTest(row=row), self.assertRaisesRegex(ValueError, message):
                blood_counts.observations(self.workbook([row]))

    def test_invalid_counts_fail_without_including_source_value(self):
        for value in (-1, True, float('inf'), 'nan', '<0.1', 'unrecognized'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                blood_counts.number(value, 'blast!E2')

    def test_existing_output_is_refused(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, 'already exists'):
                blood_counts.run('unused.xlsx', directory, baseline_day_max=1)

    def test_diagnostic_alignment_preserves_original_days_and_counts(self):
        path = self.workbook([['synthetic_a', -1, 1.04], ['synthetic_a', 1, 1.09],
                              ['synthetic_a', 4, 0]])
        frame = blood_counts.assign_baseline(blood_counts.observations(path), baseline_day_max=1)
        self.assertEqual(frame.day.tolist(), [-1, 1, 4] * 2)
        self.assertEqual(frame.display_day.tolist(), [1, 1, 4] * 2)
        self.assertEqual(frame.diagnostic_baseline.tolist(), [True, True, False] * 2)
        self.assertEqual(frame.selected_for_plot.tolist(), [False, True, True] * 2)
        self.assertEqual(frame.count_x10_9_per_L.tolist(), [1.04, 1.09, 0] * 2)

    def test_semilog_preserves_counts_breaks_lines_without_zero_strip(self):
        import numpy as np
        path = self.workbook([['synthetic_a', 1, 10], ['synthetic_a', 2, 0],
                              ['synthetic_a', 3, 1]])
        frame = blood_counts.assign_baseline(blood_counts.observations(path), baseline_day_max=1)
        original = frame.copy(deep=True)
        fig, ax = blood_counts.plt.subplots()
        self.addCleanup(blood_counts.plt.close, fig)
        blood_counts.draw(ax, frame, 'blast', baseline_day_max=1, y_scale='log')
        fig.canvas.draw()
        self.assertEqual(ax.get_yscale(), 'log')
        self.assertEqual(ax.get_xscale(), 'linear')
        self.assertTrue(np.isnan(ax.lines[0].get_ydata()[1]))
        self.assertEqual(len(ax.collections), 1)
        self.assertFalse(any('0 (separate)' in label.get_text() for label in ax.texts))
        self.assertTrue(frame.equals(original))

    def test_linear_option_and_all_zero_log_plot(self):
        frame = blood_counts.assign_baseline(
            blood_counts.observations(self.workbook([['synthetic_a', 1, 0]])), baseline_day_max=1)
        for scale in ('linear', 'log'):
            fig, ax = blood_counts.plt.subplots()
            self.addCleanup(blood_counts.plt.close, fig)
            blood_counts.draw(ax, frame, 'blast', baseline_day_max=1, y_scale=scale)
            fig.canvas.draw()
            self.assertEqual(ax.get_yscale(), scale)
            self.assertEqual(len(ax.collections), 1)


if __name__ == '__main__':
    unittest.main()
