"""Synthetic XLSX checks for shared strings, cached formulas and output safety."""
from pathlib import Path
import re
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZipFile

from openpyxl import Workbook, load_workbook

from analysis.maintenance.workbook_cleanup import clean, digest


class WorkbookCleanupTests(unittest.TestCase):
    def test_shared_identifier_formula_cache_and_package_preserved(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            seed, source, output = [root/n for n in ['seed.xlsx','source.xlsx','cleaned.xlsx']]
            wb = Workbook()
            ws = wb.active
            ws.title = 'Inventaire'
            ws.append(['tube','sample_id','dna_total_ng','extraction_date'])
            ws.append([' TEST ',' TEST ','=3*4','uncertain'])
            wb.save(seed)
            with ZipFile(seed) as zin, ZipFile(source,'w') as zout:
                for item in zin.infolist():
                    data = zin.read(item.filename)
                    if item.filename == 'xl/worksheets/sheet1.xml':
                        for coordinate in ['A2','B2']:
                            old = f'<c r="{coordinate}" t="inlineStr"><is><t xml:space="preserve"> TEST </t></is></c>'.encode()
                            new = f'<c r="{coordinate}" t="s"><v>0</v></c>'.encode()
                            self.assertIn(old,data)
                            data = data.replace(old,new)
                        data, substitutions = re.subn(rb'<f>3\*4</f><v\s*(?:/>|></v>)',b'<f>3*4</f><v>12</v>',data)
                        self.assertEqual(substitutions,1)
                    elif item.filename == '[Content_Types].xml':
                        data = data.replace(b'</Types>',b'<Override PartName="/xl/sharedStrings.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sharedStrings+xml"/></Types>')
                    zout.writestr(item,data)
                zout.writestr('xl/sharedStrings.xml',b'<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" count="2" uniqueCount="1"><si><t xml:space="preserve"> TEST </t></si></sst>')
                zout.writestr('retained_extension.bin',b'preserve exactly')
            before = digest(source)
            report = clean(source,output,['Inventaire'])
            self.assertEqual(len(report['changed_cells']),1)
            self.assertEqual(report['review_counts'],{'date_text_requires_review':1})
            self.assertEqual(digest(source),before)
            result = load_workbook(output,data_only=True)
            self.assertEqual(result['Inventaire']['A2'].value,'TEST')
            self.assertEqual(result['Inventaire']['B2'].value,' TEST ')
            self.assertEqual(result['Inventaire']['C2'].value,12)
            self.assertEqual(result['Inventaire']['D2'].value,'uncertain')
            result.close()
            with ZipFile(source) as a, ZipFile(output) as b:
                for member in a.namelist():
                    if member != 'xl/worksheets/sheet1.xml':
                        self.assertEqual(a.read(member),b.read(member))
            saved = digest(output)
            with self.assertRaises(FileExistsError):
                clean(source,output,['Inventaire'])
            self.assertEqual(digest(output),saved)


if __name__ == '__main__':
    unittest.main()
