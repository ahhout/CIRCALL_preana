from tempfile import TemporaryDirectory
from zipfile import ZipFile
from io import BytesIO
import re
import json
from pathlib import Path
import unittest
from openpyxl import load_workbook
from openpyxl.utils import get_column_letter
from analysis.repair_inventory_formulas import run,plan
from analysis.provenance import digest
from analysis.sample_io import read_sheet
from tests.sample_statistics.test_statistics import fixture

class FormulaRepairTests(unittest.TestCase):
    def test_audited_repair_clears_only_invalid_assay_formulas_and_preserves_good_formulas(self):
        with TemporaryDirectory() as t:
            root=Path(t);source=root/'synthetic.xlsx';fixture(source)
            b=load_workbook(source);sheet=b['cohorte_lal'];headers=[c.value for c in sheet[1]]
            def ref(field):return get_column_letter(headers.index(field)+1)+'2'
            volume=ref('extraction_input_volume_ml');mass=ref('dna_total_ng');specimen=ref('specimen_type')
            normalized=ref('dna_ng_per_ml_plasma');fraction=ref('cfdna_fraction');concentration=ref('cfdna_concentration_ng_per_ul')
            sheet[normalized]=f'=IF(AND(ISNUMBER({mass}),ISNUMBER({ref("elution_volume_ul")})),{mass}*{ref("elution_volume_ul")},"")'
            sheet[fraction]=f'=IF(AND({specimen}="plasma",ISNUMBER({normalized}),ISNUMBER({volume}),{volume}>0),{normalized}/{volume},"")'
            size=ref('cfdna_avg_size_bp')
            sheet[size]=f'=IF(AND({specimen}="plasma",ISNUMBER({concentration}),ISNUMBER({fraction})),{concentration}*{fraction},"")'
            healthy=ref('cfdna_total_ng');sheet[healthy]=f'=IF(AND(ISNUMBER({fraction}),ISNUMBER({mass})),{fraction}*{mass},"")'
            plan_cell=ref('sampling_plan');sheet[plan_cell]='=A2+70'
            b.save(source);b.close()
            original=read_sheet(source,'cohorte_lal');original_cells={c.coordinate:c for row in original.rows for c in row}
            audit=root/'audit.json';evidence={'workflow':'circall_equation_audit','inputs':{'inventory':{'sha256':digest(source)}},
                'equation_defects':[{'sheet':'cohorte_lal','cell':c} for c in (normalized,fraction,size)],
                'date_guard_findings':[{'sheet':'cohorte_lal','cell':plan_cell}]}
            audit.write_text(json.dumps(evidence))
            result=run(source,root/'repair',True,sheets=['cohorte_lal'],audit=audit,clear_invalid_assay_formulas=True)
            self.assertEqual(len(result['changes']['cohorte_lal']),4)
            after=read_sheet(source,'cohorte_lal');cells={c.coordinate:c for row in after.rows for c in row}
            self.assertIsNone(cells[fraction].formula);self.assertIsNone(cells[size].formula)
            self.assertIsNone(cells[fraction].value);self.assertIsNone(cells[size].value)
            self.assertEqual(cells[healthy],original_cells[healthy])
            self.assertEqual(cells[ref('dna_total_ng')],original_cells[ref('dna_total_ng')])
            self.assertIn(f'{mass}/{volume}',cells[normalized].formula)
            self.assertEqual(cells[plan_cell].formula,'=IF(ISNUMBER(A2),A2+70,"")')
            with self.assertRaises(ValueError):plan(source,['cohorte_lal'],audit=audit,clear_invalid_assay_formulas=True)
            with self.assertRaises(ValueError):plan(source,['cohorte_lal'],clear_invalid_assay_formulas=True)

    def test_explicit_controls_template_guards_dates_and_preserves_other_sheets(self):
        with TemporaryDirectory() as t:
            root=Path(t);source=root/'synthetic.xlsx';fixture(source)
            b=load_workbook(source);control=b['cohorte_control']
            template=b.copy_worksheet(control);template.title='template'
            headers=[c.value for c in template[1]]
            start=len(headers)+1;template.cell(1,start,'tt_d1_date')
            sampled=start+1;template.cell(1,sampled,'sampling_date')
            day=start+2;template.cell(1,day,'day')
            for sheet in (control,template):
                def ref(field):return get_column_letter(headers.index(field)+1)+'2'
                sheet[ref('dna_total_ng')]='='+ref('elution_volume_ul')+'*'+ref('dna_concentration_ng_per_ul')
                sheet[ref('dna_ng_per_ml_plasma')]='='+ref('dna_total_ng')+'/'+ref('extraction_input_volume_ml')
                sheet[ref('cfdna_concentration_ng_per_ul')]='='+ref('cfdna_fraction')+'*'+ref('dna_concentration_ng_per_ul')
                sheet[ref('cfdna_total_ng')]='='+ref('cfdna_fraction')+'*'+ref('dna_total_ng')
                sheet[ref('cfdna_ng_per_ml_plasma')]='='+ref('cfdna_fraction')+'*'+ref('dna_ng_per_ml_plasma')
            a=get_column_letter(start)+'2';e=get_column_letter(sampled)+'2'
            template.cell(2,headers.index('sampling_plan')+1,'='+a+'+70')
            template.cell(2,day,'='+e+'-'+a+'+1')
            # Preserve a numeric endpoint even when it does not match inputs.
            control[ref('cfdna_total_ng')]=123
            b.save(source);b.close()
            original=read_sheet(source,'cohorte_lal');before=digest(source)
            report=run(source,root/'repair',True,sheets=['cohorte_control','template'])
            self.assertEqual(digest(root/'repair/original.xlsx'),before)
            self.assertEqual(read_sheet(source,'cohorte_lal').rows,original.rows)
            self.assertEqual(len(report['changes']['cohorte_control']),4)
            self.assertEqual(len(report['changes']['template']),7)
            b=load_workbook(source);control=b['cohorte_control'];template=b['template']
            self.assertEqual(control[ref('cfdna_total_ng')].value,123)
            self.assertIn('>0',control[ref('dna_ng_per_ml_plasma')].value)
            self.assertIn('="plasma"',control[ref('cfdna_ng_per_ml_plasma')].value)
            self.assertEqual(template.cell(2,headers.index('sampling_plan')+1).value,f'=IF(ISNUMBER({a}),{a}+70,"")')
            self.assertEqual(template.cell(2,day).value,f'=IF(AND(ISNUMBER({e}),ISNUMBER({a})),{e}-{a}+1,"")')
            b.close()
            self.assertFalse(any(plan(source,['cohorte_control','template']).values()))
            self.assertEqual(report['status'],'complete')
            self.assertIsNotNone(report['started_utc']);self.assertIsNotNone(report['finished_utc'])

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
