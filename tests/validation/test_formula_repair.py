from tempfile import TemporaryDirectory
from zipfile import ZipFile
from io import BytesIO
import re
from pathlib import Path
import unittest
from openpyxl import load_workbook
from analysis.repair_inventory_formulas import run
from analysis.provenance import digest
from analysis.sample_io import read_sheet
from tests.sample_statistics.test_statistics import fixture

class FormulaRepairTests(unittest.TestCase):
    def test_preserve_measurements_and_invalidate_only_changed_caches(self):
        with TemporaryDirectory() as t:
            root=Path(t);source=root/'synthetic.xlsx';fixture(source)
            b=load_workbook(source);w=b['cohorte_lal'];h=[c.value for c in w[1]]
            target=h.index('dna_total_ng')+1;w.cell(3,target,'=2*3');b.save(source);b.close()
            payload=source.read_bytes()
            with ZipFile(BytesIO(payload)) as a,ZipFile(source,'w') as z:
                for info in a.infolist():
                    data=a.read(info.filename)
                    if info.filename=='xl/worksheets/sheet1.xml':
                        from openpyxl.utils import get_column_letter
                        coord=(get_column_letter(target)+'3').encode()
                        pattern=rb'<c\b[^>]*r="'+coord+rb'"[^>]*>.*?</c>'
                        def bad(m):
                            raw=m[0].replace(b'>',b' t="e">',1)
                            return re.sub(rb'<v(?:/>|>.*?</v>)',b'<v>#DIV/0!</v>',raw)
                        data=re.sub(pattern,bad,data,flags=re.S)
                    z.writestr(info,data)
            before=digest(source);report=run(source,root/'repair',True)
            self.assertEqual(len(report['changes']['cohorte_lal']),1)
            self.assertEqual(digest(root/'repair/original.xlsx'),before)
            with ZipFile(source) as z:
                self.assertNotIn('xl/calcChain.xml',z.namelist())
                self.assertIn(b'fullCalcOnLoad="1"',z.read('xl/workbook.xml'))
                self.assertIn(b'forceFullCalc="1"',z.read('xl/workbook.xml'))
            s=read_sheet(source,'cohorte_lal');self.assertEqual(s.rows[0][target-1].value,100)
            self.assertIsNone(s.rows[1][target-1].value)
            self.assertIn('ISNUMBER',s.rows[1][target-1].formula)
            self.assertEqual(report['changes']['cohorte_control'],{})
            with self.assertRaises(ValueError):run(source,root/'repair')

if __name__=='__main__':unittest.main()
