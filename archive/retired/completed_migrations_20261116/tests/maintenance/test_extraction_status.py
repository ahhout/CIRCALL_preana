"""Synthetic preservation and status-consolidation checks."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from openpyxl import Workbook, load_workbook

from archive.retired.completed_migrations_20261116.analysis.extraction_status import normalize
from analysis.provenance import ROOT,digest


class ExtractionStatusTests(unittest.TestCase):
    def test_explicit_status_only_clear_text_preserve_numbers_ids_formulas(self):
        with TemporaryDirectory() as temp:
            source=Path(temp)/'source.xlsx';dest=Path(temp)/'result.xlsx'
            wb=Workbook();ws=wb.active;ws.title='Inventaire'
            ws.append(['extraction_date','extraction_method','elution_volume_ul','dna_id','dna_total_ng'])
            ws.append(['PAS EXTRAIT','planned method',50,'SYNTHETIC-ID','=IF(FALSE,1,"")'])
            ws.append(['pas extrait','other method','?','SYNTHETIC-ID-2',None])
            ws.append(['?','known method',20,'SYNTHETIC-ID-3',40])
            wb.save(source);wb.close();before=digest(source)
            rules=json.loads((ROOT/'configs/definitions/data_integrity.json').read_text())
            result=normalize(source,dest,['Inventaire'],rules['extraction_dependent_fields'])
            output=load_workbook(dest);s=output['Inventaire']
            self.assertEqual(s['F1'].value,'extraction_status')
            self.assertEqual(s['F2'].value,'not_extracted');self.assertEqual(s['F3'].value,'not_extracted')
            self.assertIsNone(s['F4'].value)
            self.assertIsNone(s['A2'].value)
            self.assertEqual(s['B2'].value,'planned method')
            self.assertEqual(s['B3'].value,'other method')
            self.assertEqual(s['C2'].value,50);self.assertIsNone(s['C3'].value)
            self.assertEqual(s['D2'].value,'SYNTHETIC-ID')
            self.assertEqual(s['E2'].value,'=IF(FALSE,1,"")')
            self.assertEqual(s['A4'].value,'?');self.assertEqual(s['B4'].value,'known method')
            self.assertEqual(len(result['conflicts']),1)
            self.assertNotIn('SYNTHETIC-ID',json.dumps(result))
            self.assertEqual(digest(source),before)
            output.close()
            with self.assertRaises(FileExistsError):normalize(source,dest,['Inventaire'],rules['extraction_dependent_fields'])


if __name__=='__main__':unittest.main()
