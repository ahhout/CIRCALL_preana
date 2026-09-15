import json
from pathlib import Path
import tempfile
import unittest

from openpyxl import Workbook

from pre_analysis.preparation import (Cell, SourceRow, mapped_measurements, numeric,
                                      read_sheet, validate_measurements)
from pre_analysis.adapters import CORE, MNC, circall, retrospective


class PreparationTests(unittest.TestCase):
    def test_circall_numeric_semantics(self):
        for value, expected in [('1,25', 1.25), (' 1e-3 ', .001), (0, 0), ('0.76', .76)]:
            self.assertEqual(numeric(value), expected)
        for value in [None, '', 'SK', 'na', '-', '#DIV/0!', 'inf', 'nan', '<0.1', '1 ng/uL', True]:
            self.assertIsNone(numeric(value))

    def record(self, concentration, elution, total, volume, endpoint, formula=None):
        mapping = {k: k for k in ('dna_concentration_ng_per_uL', 'elution_volume_uL', 'dna_total_ng', 'volume_ml', 'dna_ng_per_mL_plasma')}
        values = [concentration, elution, total, volume, endpoint]
        row = SourceRow(2, {key: Cell(value, formula if key == 'dna_total_ng' else None) for key, value in zip(mapping, values)})
        return mapped_measurements(row, mapping)

    def test_formula_zero_propagates_missingness(self):
        values, reasons, issues = validate_measurements(*self.record(None, None, 0, 5, 0, '=A2*B2'), compartment='plasma')
        self.assertIsNone(values['dna_total_ng'])
        self.assertIsNone(values['dna_ng_per_mL_plasma'])
        self.assertEqual(values['volume_ml'], 5)
        self.assertEqual(reasons['dna_total_ng'], 'formula_zero_missing_inputs')
        self.assertFalse(issues)

    def test_measured_zero_survives(self):
        values, _, issues = validate_measurements(*self.record(0, 100, 0, 5, 0, '=A2*B2'), compartment='plasma')
        self.assertEqual(values['dna_ng_per_mL_plasma'], 0)
        self.assertFalse(issues)

    def test_missing_volume_preserves_other_measurements(self):
        values, _, issues = validate_measurements(*self.record(.1, 100, 10, 'SK', '#VALUE!'), compartment='plasma')
        self.assertEqual(values['dna_total_ng'], 10)
        self.assertEqual(values['dna_concentration_ng_per_uL'], .1)
        self.assertIsNone(values['dna_ng_per_mL_plasma'])
        self.assertFalse(issues)

    def test_genuine_conflicts_and_tolerance(self):
        _, _, issues = validate_measurements(*self.record(.09, 100, 37160, 5, 7432, '=A9*B9'), compartment='plasma')
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0]['calculated'], 9)
        _, _, issues = validate_measurements(*self.record(1.14, 50, 57, 7, 57/7), compartment='plasma')
        self.assertFalse(issues)
        _, _, issues = validate_measurements(*self.record(1.2, 50, 60, 5, 11.23), compartment='plasma')
        self.assertEqual(issues[0]['reason'], 'endpoint_vs_total_divided_volume')

    def test_primary_endpoint_does_not_apply_fraction(self):
        values, reasons, raw = self.record(2, 50, 100, 5, 20)
        values.update(cfDNA_fraction=.2, cfDNA_total_ng=20, cfDNA_ng_per_mL_plasma=4)
        values, _, _ = validate_measurements(values, reasons, raw, compartment='plasma')
        self.assertEqual(values['dna_ng_per_mL_plasma'], 20)
        self.assertEqual(values['cfDNA_ng_per_mL_plasma'], 4)

    def workbook(self, path, sheet, rows, columns):
        book = Workbook(); ws = book.active; ws.title = sheet; ws.append(columns)
        for row in rows:
            ws.append([row.get(k) for k in columns])
        book.save(path); book.close()

    def test_wide_plasma_and_mnc_do_not_share_volume(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'synthetic.xlsx'
            cols = list(CORE) + list(MNC.values()) + ['lastname','sample_id','treatment_phase','tissue','nucleic_acid','MRD_IgTCR']
            self.workbook(path, 'Inventaire', [dict(lastname='Synthetic Private Name', sample_id='tube-1', treatment_phase='diag', tissue='Sang', nucleic_acid='cfDNA', volume_ml=5, dna_concentration_ng_per_uL=2, elution_volume_uL=50, dna_total_ng=100, dna_ng_per_mL_plasma=20, MNC_vario_total_ng=900, MRD_IgTCR='na')], cols)
            records, issues, _ = retrospective(path)
            self.assertEqual(len(records), 2)
            plasma, pellet = records
            self.assertEqual(plasma['compartment'], 'plasma')
            self.assertEqual(pellet['compartment'], 'blood pellet')
            self.assertEqual(plasma['source_tube_key'], pellet['source_tube_key'])
            self.assertIsNone(pellet['volume_ml'])
            self.assertIsNone(pellet['dna_total_ng'])
            self.assertEqual(pellet['mnc_vario_total_ng'], 900)
            self.assertEqual(plasma['mrd_status'], 'neg')
            self.assertNotIn('Synthetic Private Name', json.dumps(records))
            self.assertFalse(issues)

    def test_circall_keeps_known_patient_schedule_not_template(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp)/'synthetic.xlsx'
            cols = list(CORE) + ['circall_id','sample_id','timepoint','compartment']
            self.workbook(path, 'cohorte_lal', [dict(circall_id='001-X',sample_id='na',timepoint='D4',compartment='plasma'),dict(timepoint='D4',compartment='plasma',dna_total_ng=0)], cols)
            records, _, _ = circall(path)
            self.assertEqual(len(records), 1)
            self.assertEqual(records[0]['sample_state'], 'explicit_missing')
            self.assertEqual(records[0]['timepoint'], 'd4')

    def test_reader_rejects_duplicate_or_missing_headers(self):
        with tempfile.TemporaryDirectory() as temp:
            path=Path(temp)/'synthetic.xlsx'
            self.workbook(path,'Sheet',[],['volume_ml','volume_ml'])
            with self.assertRaisesRegex(ValueError, 'Duplicate'):
                read_sheet(path,'Sheet',{'volume_ml'})
            self.workbook(path,'Sheet',[],['volume_ml'])
            with self.assertRaisesRegex(ValueError, 'Missing columns'):
                read_sheet(path,'Sheet',{'dna_total_ng'})
            with self.assertRaisesRegex(ValueError, 'Missing required sheet'):
                read_sheet(path,'absent',set())


if __name__ == '__main__':
    unittest.main()
