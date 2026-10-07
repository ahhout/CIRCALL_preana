"""Synthetic tests for gap filling without changing existing source data."""
from datetime import datetime
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from zipfile import ZipFile

from openpyxl import Workbook,load_workbook
from analysis.patient_ids import plan,run
from analysis.provenance import digest


class PatientIdTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.source=self.root/'synthetic.xlsx'

    def make(self,rows,header='patient_id'):
        b=Workbook();w=b.active;w.title='Inventaire'
        w.append([header,'lastname','firstname','dob','sample_id','measurement'])
        for row in rows:w.append(row)
        b.save(self.source);b.close()

    def test_fill_continue_reuse_and_preserve(self):
        dob=datetime(1990,1,1)
        self.make([['unk-005-X-Y','Xexample','Yexample',dob,'S1','=2*3'],
                   [None,'Xexample','Yexample',dob,'S2',0],
                   ['na','Apple','Bear',dob,'S3',12],
                   [None,'Apple','Bear',dob,'S4',13],
                   [None,'Apple','Bear',datetime(1991,1,1),'S5',14]],header='inclusion_id')
        before=digest(self.source);out=self.root/'out';result=run(self.source,out,True)
        self.assertEqual(result['filled_cells'],4);self.assertEqual(result['new_patient_ids'],2)
        self.assertEqual(digest(out/'original.xlsx'),before)
        b=load_workbook(self.source);w=b.active
        self.assertEqual(w['A1'].value,'patient_id')
        self.assertEqual([w.cell(r,1).value for r in range(2,7)],['unk-005-X-Y','unk-005-X-Y','unk-006-A-B','unk-006-A-B','unk-007-A-B'])
        self.assertEqual(w['F2'].value,'=2*3');self.assertEqual(w['F3'].value,0);b.close()
        self.assertEqual(plan(self.source)[2]['filled_cells'],0)
        self.assertNotIn('Apple',(out/'patient_id_report.json').read_text())

    def test_conflicting_existing_ids_are_preserved(self):
        dob=datetime(1990,1,1)
        self.make([['A','Alpha','Beta',dob],['B','Alpha','Beta',dob],[None,'Alpha','Beta',dob]])
        _,edits,report=plan(self.source)
        self.assertEqual(edits,{})
        self.assertEqual(report['unfilled_cells'],1)

    def test_incomplete_identity_is_not_invented(self):
        self.make([[None,'Alpha','Beta',None]])
        self.assertEqual(plan(self.source)[2]['unfilled_cells'],1)

    def test_open_workbook_and_existing_destination_refused(self):
        self.make([[None,'Alpha','Beta',datetime(1990,1,1)]])
        lock=self.source.with_name('~$'+self.source.name);lock.touch()
        with self.assertRaises(ValueError):run(self.source,self.root/'out')
        lock.unlink();(self.root/'out').mkdir()
        with self.assertRaises(ValueError):run(self.source,self.root/'out')

    def test_exact_name_spelling_is_not_normalized(self):
        self.make([[None,'Alpha','Beta',datetime(1990,1,1)],[None,'ALPHA','Beta',datetime(1990,1,1)]])
        self.assertEqual(plan(self.source)[2]['new_patient_ids'],2)


if __name__=='__main__':unittest.main()
