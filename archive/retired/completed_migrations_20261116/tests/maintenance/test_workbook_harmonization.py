"""Synthetic checks for authorized header/specimen mappings and preservation."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from openpyxl import Workbook, load_workbook

from archive.retired.completed_migrations_20261116.analysis.workbook_harmonization import ROOT, DEFAULT_CONFIG, harmonize, replacements


class HarmonizationTests(unittest.TestCase):
    def setUp(self):
        self.config=json.loads(DEFAULT_CONFIG.read_text())

    def test_contextual_specimen_mapping_and_identifiers(self):
        with TemporaryDirectory() as tmp:
            source,output=[Path(tmp)/n for n in ['source.xlsx','result.xlsx']]
            wb=Workbook(); ws=wb.active; ws.title='Inventaire'
            ws.append(['tissue','nucleic_acid','sample_id','volume_ml','cfDNA_total_ng','treatment_phase'])
            ws.append(['Sang','celDNA','Sang',2.5,'=D2*2','tp1'])
            ws.append(['Sang','cfDNA','synthetic-02',1.5,3,'diag'])
            ws.append(['Plasma','cfDNA','synthetic-03',None,None,'diag'])
            wb.save(source)
            result=harmonize(source,output,'retrospective',self.config)
            self.assertEqual(result['specimen_label_changes'],2)
            self.assertEqual(len(result['review_cells']),1)
            copied=load_workbook(output,data_only=False)['Inventaire']
            self.assertEqual([c.value for c in copied[1]],['specimen_type','nucleic_acid','sample_id','extraction_input_volume_ml','cfdna_total_ng','timepoint'])
            self.assertEqual(copied['A2'].value,'blood pellet')
            self.assertEqual(copied['A3'].value,'Sang')
            self.assertEqual(copied['A4'].value,'plasma')
            self.assertEqual(copied['C2'].value,'Sang')
            self.assertEqual(copied['D2'].value,2.5)
            self.assertEqual(copied['E2'].value,'=D2*2')
            self.assertEqual(copied['F2'].value,'tp1')

    def test_header_collision_rejected(self):
        with TemporaryDirectory() as tmp:
            source=Path(tmp)/'source.xlsx'
            wb=Workbook(); wb.active.title='Inventaire'
            wb.active.append(['tissue','compartment']); wb.save(source)
            with self.assertRaisesRegex(ValueError,'collide'):
                replacements(source,'retrospective',self.config)

    def test_formula_using_changed_label_requires_review(self):
        with TemporaryDirectory() as tmp:
            source=Path(tmp)/'source.xlsx'
            wb=Workbook(); wb.active.title='Inventaire'
            wb.active.append(['tissue','nucleic_acid','calculation'])
            wb.active.append(['Sang','celDNA','=IF(A2="Sang",1,0)']); wb.save(source)
            with self.assertRaisesRegex(ValueError,'specimen label'):
                replacements(source,'retrospective',self.config)


if __name__=='__main__':
    unittest.main()
