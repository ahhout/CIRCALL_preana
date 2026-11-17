"""Synthetic acceptance for shared extraction rules and source preservation."""
import json
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZipFile

from openpyxl import Workbook, load_workbook

from analysis.data_integrity.step_01_inspect import inspect_cohort, load_rules
from analysis.provenance import ROOT, digest
from analysis.maintenance.sample_annotations import main, migrate, plan
from analysis.utils.sample_definitions import extraction_state
from analysis.utils.sample_io import read_sheet
from tests.fixtures.data_integrity import fixture


CONFIG = json.loads((ROOT/'configs/maintenance/sample_annotations.json').read_text())


class AnnotationTests(unittest.TestCase):
    def test_adoption_retains_verified_originals_for_every_selected_workbook(self):
        with TemporaryDirectory() as temp:
            root=Path(temp); args=[]; originals={}
            for cohort,sheets in CONFIG['selected_sheets'].items():
                path=root/(cohort+'.xlsx');book=Workbook();book.remove(book.active)
                for name in sheets:
                    sheet=book.create_sheet(name)
                    sheet.append(['sample_id','dna_id','specimen_type','extraction_status','value'])
                    sheet.append(['SYNTHETIC','SYNTHETIC-DNA','plasma',None,'?'])
                book.save(path);book.close();originals[cohort]=digest(path)
                args.extend(['--'+cohort,str(path)])
            output=root/'migration'
            with redirect_stdout(StringIO()):
                self.assertEqual(main([*args,'--output-dir',str(output),'--adopt']),0)
            report=json.loads((output/'annotation_report.json').read_text())
            self.assertEqual(len(report['adopted']),3)
            self.assertIsNotNone(report['started_utc']);self.assertIsNotNone(report['finished_utc'])
            for cohort,before in originals.items():
                self.assertEqual(digest(output/cohort/'original.xlsx'),before)
                self.assertNotEqual(digest(root/(cohort+'.xlsx')),before)
                self.assertEqual(digest(root/(cohort+'.xlsx')),digest(output/cohort/(cohort+'.xlsx')))
            with redirect_stdout(StringIO()), self.assertRaises(SystemExit):
                main([*args,'--output-dir',str(output),'--adopt'])

    def test_migration_preserves_actual_ids_blanks_numbers_formulas_and_extensions(self):
        with TemporaryDirectory() as temp:
            source, output = Path(temp)/'source.xlsx', Path(temp)/'output.xlsx'
            book = Workbook(); sheet = book.active; sheet.title = 'Inventaire'
            sheet.append(['sample_id', 'dna_id', 'specimen_type', 'extraction_status', 'value', 'lastname', 'dob', 'formula'])
            sheet.append(['REAL-SYNTHETIC-ID', 'DNA-SYNTHETIC-ID', 'plasma', None, '?', '?', '-', '=IF(1,"?",0)'])
            sheet.append([' N/A ', None, 'CSF', 'pending', 'sk', 'PRIVATE-SYNTHETIC-NAME', None, 0])
            sheet.append([None, 'na', 'plasma', 'extracted', '-', None, None, 1.25])
            book.save(source); book.close()
            # Package metadata must survive the edit without a library resave.
            with ZipFile(source, 'a') as archive:
                archive.writestr('customXml/annotation-test.xml', '<approved-test/>')
            before = digest(source)
            report = migrate(source, output, ['Inventaire'], CONFIG)
            self.assertEqual(digest(source), before)
            actual = load_workbook(output); sheet = actual['Inventaire']
            self.assertEqual(sheet['A2'].value, 'REAL-SYNTHETIC-ID')
            self.assertEqual(sheet['B2'].value, 'DNA-SYNTHETIC-ID')
            self.assertEqual(sheet['D2'].value, 'yes')
            self.assertEqual(sheet['E2'].value, 'na')
            self.assertEqual(sheet['F2'].value, '?'); self.assertEqual(sheet['G2'].value, '-')
            self.assertEqual(sheet['H2'].value, '=IF(1,"?",0)')
            self.assertEqual(sheet['A3'].value, 'na'); self.assertIsNone(sheet['B3'].value)
            self.assertEqual(sheet['D3'].value, 'no'); self.assertEqual(sheet['E3'].value, 'na')
            self.assertIsNone(sheet['A4'].value); self.assertEqual(sheet['D4'].value, 'no')
            self.assertEqual(sheet['H3'].value, 0); self.assertEqual(sheet['H4'].value, 1.25)
            actual.close()
            self.assertFalse(any(value in json.dumps(report) for value in ('REAL-SYNTHETIC-ID','DNA-SYNTHETIC-ID','PRIVATE-SYNTHETIC-NAME')))
            self.assertFalse(any(plan(output,['Inventaire'],CONFIG).values()))
            with ZipFile(source) as old, ZipFile(output) as new:
                self.assertEqual(old.read('customXml/annotation-test.xml'), new.read('customXml/annotation-test.xml'))

    def test_legacy_status_is_ignored_and_dna_id_controls_extraction(self):
        with TemporaryDirectory() as temp:
            source = Path(temp)/'source.xlsx'
            fixture(source, [{'dna_id':None,'extraction_status':'yes'},
                             {'dna_id':'SYNTHETIC-ID','extraction_status':'no'},
                             {'dna_id':'SYNTHETIC-ID-2','extraction_status':'=1/0'},
                             {'dna_id':None,'extraction_status':'unrecognized status'}])
            rules = load_rules(ROOT/'configs/definitions/data_integrity.json')
            result = inspect_cohort(source,'retrospective',False,rules)
            self.assertFalse(any(i['field']=='extraction_status' for i in result['findings']))
            self.assertTrue(any(i['rule']=='extraction_state_conflict' and i['field']=='dna_concentration_ng_per_ul' for i in result['findings']))
            cells = read_sheet(source,'Inventaire')
            pos = next(i for i,c in enumerate(cells.headers) if c.value=='dna_id')
            self.assertEqual(extraction_state(cells.rows[0][pos],rules['missing_tokens'],rules['unknown_tokens']),'no')
            self.assertEqual(extraction_state(cells.rows[1][pos],rules['missing_tokens'],rules['unknown_tokens']),'yes')
            self.assertEqual(extraction_state(None,rules['missing_tokens']),'unavailable')
            book=load_workbook(source); ws=book['Inventaire']
            status_col=next(c.column for c in ws[1] if c.value=='extraction_status')
            ws.delete_cols(status_col); book.save(source); book.close()
            without_status=inspect_cohort(source,'retrospective',False,rules)
            self.assertEqual(result['findings'],without_status['findings'])
            self.assertEqual(result['summary'],without_status['summary'])

    def test_volume_validation_only_applies_to_plasma_and_csf(self):
        with TemporaryDirectory() as temp:
            source = Path(temp)/'source.xlsx'
            fixture(source,[{'specimen_type':'blood pellet','extraction_input_volume_ml':-1},
                            {'specimen_type':'CSF','extraction_input_volume_ml':-1}])
            result=inspect_cohort(source,'retrospective',False,load_rules(ROOT/'configs/definitions/data_integrity.json'))
            invalid=[i for i in result['findings'] if i['field']=='extraction_input_volume_ml' and i['rule']=='number_invalid']
            self.assertEqual(len(invalid),1)
            self.assertTrue(invalid[0]['cell'].endswith('3'))

    def test_formula_identity_is_not_guessed_or_rewritten(self):
        with TemporaryDirectory() as temp:
            source=Path(temp)/'source.xlsx'; book=Workbook(); sheet=book.active;sheet.title='Inventaire'
            sheet.append(['sample_id','dna_id','extraction_status']);sheet.append(['SYNTHETIC','=1',None])
            book.save(source);book.close();before=digest(source)
            with self.assertRaises(ValueError):plan(source,['Inventaire'],CONFIG)
            self.assertEqual(digest(source),before)


if __name__ == '__main__':
    unittest.main()
