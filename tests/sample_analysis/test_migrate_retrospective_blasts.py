"""Synthetic workbook migration checks, including exact caches and safe failures."""
from datetime import datetime
from io import BytesIO
from pathlib import Path
import tempfile
import unittest
from xml.etree import ElementTree as ET
from zipfile import ZipFile, ZIP_DEFLATED

from openpyxl import Workbook, load_workbook

from analysis.sample_analysis.migrate_retrospective_blasts import migrate, remap_formula, NS


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.source = Path(self.tmp.name)/'synthetic.xlsx'
        self.output = Path(self.tmp.name)/'new.xlsx'

    def workbook(self, *, cached=True, extra=False):
        book = Workbook()
        book.remove(book.active)
        for name in ('cleandata', 'test'):
            sheet = book.create_sheet(name)
            sheet.append(['lastname', 'firstname', 'subtype', 'induction', 'consolidation',
                          'D1 date', 'sample_date', 'day', 'percent_blast', 'num_blast', 'num_log', None])
            sheet.append(['synthetic_subject', 'synthetic_given', 'synthetic_group', None, 'synthetic_treatment',
                          datetime(2020,1,1), datetime(2020,1,3), '=(G2-F2)+1', 0, 0, '=LOG(J2+1)', 'synthetic_note'])
            if extra:
                sheet.cell(1,13,'unexpected_field')
        buffer=BytesIO()
        book.save(buffer)
        book.close()
        with ZipFile(buffer) as src, ZipFile(self.source,'w',ZIP_DEFLATED) as dst:
            for item in src.infolist():
                data=src.read(item.filename)
                if cached and item.filename.startswith('xl/worksheets/sheet'):
                    tree=ET.fromstring(data)
                    for c in tree.findall('.//s:c',NS):
                        if c.attrib['r'] in ('H2','K2'):
                            c.find('s:v',NS).text='3' if c.attrib['r']=='H2' else '0'
                    data=ET.tostring(tree)
                dst.writestr(item,data)

    def test_preserves_values_formulas_notes_and_original(self):
        self.workbook()
        original=self.source.read_bytes()
        report=migrate(self.source,self.output)
        self.assertEqual(self.source.read_bytes(),original)
        self.assertEqual(report['status'],'passed')
        with ZipFile(self.output) as z:
            self.assertIsNone(z.testzip())
        for data_only in (False,True):
            book=load_workbook(self.output,data_only=data_only)
            try:
                self.assertEqual(book.sheetnames,['blast','source_test','README'])
                for name in ('blast','source_test'):
                    s=book[name]
                    self.assertEqual(s['D2'].value,3 if data_only else '=(C2-B2)+1')
                    self.assertEqual(s['K2'].value,0 if data_only else '=LOG(E2+1)')
                    self.assertEqual(s['E2'].value,0)
                    self.assertEqual(s['L2'].value,'synthetic_note')
                    self.assertEqual(s['A2'].value,'synthetic_subject')
                    self.assertEqual(s['B2'].value,datetime(2020,1,1))
                    self.assertEqual(s['E1'].value,'blast_count_x10*9/L')
            finally:
                book.close()

    def test_uncached_formulas_do_not_create_output(self):
        self.workbook(cached=False)
        with self.assertRaisesRegex(ValueError,'uncached formula'):
            migrate(self.source,self.output)
        self.assertFalse(self.output.exists())

    def test_unexpected_metadata_is_not_silently_dropped(self):
        self.workbook(extra=True)
        with self.assertRaisesRegex(ValueError,'Unexpected source headers'):
            migrate(self.source,self.output)
        self.assertFalse(self.output.exists())

    def test_existing_output_is_not_overwritten(self):
        self.output.write_bytes(b'preserve')
        with self.assertRaisesRegex(ValueError,'Destination exists'):
            migrate(self.source,self.output)
        self.assertEqual(self.output.read_bytes(),b'preserve')

    def test_formula_mapping_preserves_absolute_references_and_rejects_external(self):
        self.assertEqual(remap_formula('=$G$2-F2+1',{'G':'C','F':'B'}),'=$C$2-B2+1')
        with self.assertRaisesRegex(ValueError,'Unsupported formula'):
            remap_formula("='other'!A2",{'A':'A'})


if __name__ == '__main__':
    unittest.main()
