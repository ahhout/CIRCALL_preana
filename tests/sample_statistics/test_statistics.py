from tests.fixtures.execution import layer_main
"""Synthetic acceptance coverage; no clinical fixtures or source identifiers."""

from tests.fixtures.sample_statistics import fixture, D, ASOF
from contextlib import redirect_stdout, redirect_stderr
from datetime import date, datetime, timedelta, timezone
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from collections import Counter
import unittest
from unittest.mock import patch
from zipfile import ZipFile

from openpyxl import Workbook, load_workbook

from analysis.provenance import ROOT, digest
from analysis.sample_io import SourceCell
from analysis.sample_statistics import core, runner





class RulesTests(unittest.TestCase):
    def classify(self, sample=None, visit='tp1', planned=date(2026,10,1), asof='2026-10-05T00:00:00+02:00',cohort='circall'):
        return core.receipt(sample,visit,planned,cohort,core.assessment(asof),D)

    def test_receipt_boundary_and_fallback(self):
        for sample in ('na',):
            for asof,expected in [('2026-09-30T23:59:59+02:00','not_yet_due'),('2026-10-01T00:00:00+02:00','pending'),('2026-10-04T00:00:00+02:00','pending'),('2026-10-04T00:00:01+02:00','overdue')]:
                with self.subTest(sample=sample,asof=asof):
                    result=self.classify(sample,asof=asof)
                    self.assertEqual(result['receipt'],'marked_missing')
                    self.assertEqual(result['receipt_timing'],expected)
                    self.assertEqual(result['overdue'],expected=='overdue')
        early=self.classify('SYNTHETIC',asof='2026-09-30T12:00:00+02:00')
        self.assertEqual(early['receipt'],'received');self.assertEqual(early['receipt_timing'],'received_early')
        self.assertFalse(early['due_received'])
        for visit,plan in [('tp2',date(2026,1,1)),('tp1',None),('tp1','01/10/2026')]:
            missing=self.classify('na',visit,plan)
            self.assertEqual(missing['receipt'],'marked_missing')
            self.assertFalse(missing['overdue']);self.assertFalse(missing['overdue_assessed'])
            self.assertEqual(self.classify(None,visit,plan)['receipt'],'unassessed')
            self.assertEqual(self.classify('?',visit,plan)['receipt'],'unassessed')
            self.assertEqual(self.classify('SYNTHETIC',visit,plan)['receipt'],'received')
        self.assertEqual(self.classify('na',cohort='retrospective')['receipt'],'marked_missing')
        for sample in (None, '', '?', 'sk'):
            self.assertEqual(self.classify(sample)['receipt'], 'unassessed')

    def test_only_explicit_overdue_missingness_enters_denominator(self):
        rows=[]
        for sample, planned in [(None,date(2026,10,1)),('?',date(2026,10,1)),('na',None),
                                ('na',date(2026,10,1)),('SYNTHETIC',date(2026,10,1)),('EARLY-SYNTHETIC',date(2026,10,10)),('UNTIMED-SYNTHETIC',None)]:
            rows.append(dict(subject_key='SYNTHETIC',patient_id='SYNTHETIC',center='RDB',visit='tp1',
                             specimen='plasma',control=False,extraction_status='no',measurements={},sheet='synthetic',row=2,
                             **self.classify(sample,planned=planned)))
        tables=core.aggregate(rows,{**D,'metrics':{}})
        overall=[r for r in tables['receipt'] if r['view']=='overall']
        self.assertTrue(all(r['classified_denominator']==2 for r in overall if r['basis']=='deadline'))
        self.assertEqual(len(tables['missed']),3)
        self.assertEqual(Counter(r['status'] for r in tables['missed']),{'late':2,'marked_missing':1})
        self.assertTrue(all(r['classified_percentage'] is None for r in overall if r['status']=='unassessed' or r['basis']=='manual_or_id'))
        received=next(r for r in overall if r['status']=='received')
        self.assertEqual(received['samples'],2);self.assertEqual(received['classified_samples'],1)
        self.assertEqual(received['classified_percentage'],.5)
        self.assertEqual(sum(r['overdue_samples'] for r in overall),3)
        self.assertEqual(next(r for r in overall if r['status']=='unassessed')['overdue_samples'],2)

    def test_late_is_unmarked_absence_after_the_same_deadline(self):
        for sample in (None, '', '?', 'sk'):
            for asof, timing in [('2026-09-30T23:59:59+02:00','not_yet_due'),
                                 ('2026-10-01T00:00:00+02:00','pending'),
                                 ('2026-10-04T00:00:00+02:00','pending'),
                                 ('2026-10-04T00:00:01+02:00','late')]:
                with self.subTest(sample=sample,asof=asof):
                    result=self.classify(sample,asof=asof)
                    self.assertEqual(result['receipt'],'unassessed')
                    self.assertEqual(result['receipt_timing'],timing)
                    self.assertEqual(result['overdue'],timing=='late')
                    self.assertEqual(result['overdue_status'],'late' if timing=='late' else None)
        self.assertEqual(self.classify('na')['overdue_status'],'marked_missing')
        for kwargs in [dict(sample='SYNTHETIC'),dict(sample=None,visit='tp2'),
                       dict(sample=None,planned=None),dict(sample='?',planned='01/10/2026'),
                       dict(sample=None,cohort='retrospective')]:
            self.assertFalse(self.classify(**kwargs)['overdue'])
        self.assertFalse(core.receipt(None,'tp1',date(2026,10,1),'circall',
                                     core.assessment('2026-10-05T00:00:00+02:00'),D,control=True)['overdue'])

    def test_dst_elapsed_not_wall_time(self):
        for start,at,after in [(date(2026,3,28),'2026-03-31T01:00:00+02:00','2026-03-31T01:00:01+02:00'),(date(2026,10,24),'2026-10-26T23:00:00+01:00','2026-10-26T23:00:01+01:00')]:
            self.assertFalse(self.classify('na',planned=start,asof=at)['overdue'])
            self.assertTrue(self.classify('na',planned=start,asof=after)['overdue'])
        with self.assertRaises(ValueError):core.assessment('2026-10-05T12:00:00')

    def test_measurements(self):
        for value,state,expected in [(0,'available',0),('0,5','available',.5),('?','unknown',None),('na','missing_marker',None),('2 aliquots','qualified_or_invalid',None),('50%','qualified_or_invalid',None),(None,'blank',None)]:
            c=SourceCell('A2',2,1,value,value,'n','n','General',None)
            self.assertEqual(core.measurement(c,'unclassified',D),{'value':expected,'state':state})
        c=SourceCell('A2',2,1,'na','na','s','s','General',None)
        self.assertEqual(core.measurement(c,'no',D)['state'],'not_applicable')
        self.assertEqual(core.measurement(c,'yes',D)['state'],'missing_marker')
        for kind,state in [('str','intentional_empty'),('n','cache_unavailable')]:
            c=SourceCell('A2',2,1,'=IF(1,"",0)',None,'f',kind,'General','=IF(1,"",0)')
            self.assertEqual(core.measurement(c,'unclassified',D)['state'],state)
        self.assertEqual(core.describe([0,2])['mean'],1)
        self.assertEqual(core.describe([0])['sd'],None)


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.retro=self.root/'retro.xlsx';self.circall=self.root/'circall.xlsx'
        fixture(self.retro,'retrospective');fixture(self.circall)

    def args(self,output,cohort='all',controls=True):
        return runner.arguments(['--inventory',str(self.retro),'--circall',str(self.circall),'--cohort',cohort,'--assessment-time',ASOF,'--output-dir',str(output)]+([] if controls else ['--no-include-controls']))

    def test_available_volume_independent_of_extraction(self):
        book=load_workbook(self.retro);ws=book['Inventaire'];headers=[c.value for c in ws[1]]
        ws.cell(2,headers.index('extraction_status')+1,'not_extracted')
        ws.cell(2,headers.index('dna_id')+1).value=None
        ws.cell(2,headers.index('extraction_input_volume_ml')+1).value=None
        ws.cell(2,headers.index('elution_volume_ul')+1).value=None
        book.save(self.retro);book.close()
        rows,issues,skipped=core.prepare(self.retro,'retrospective',False,core.assessment(ASOF),D)
        self.assertEqual(rows[0]['measurements']['extraction_input_volume_ml']['state'],'blank')
        self.assertEqual(rows[0]['measurements']['elution_volume_ul']['state'],'not_applicable')

    def test_counts_receipt_and_pooling(self):
        rows,issues,skipped=core.prepare(self.circall,'circall',True,core.assessment(ASOF),D)
        self.assertEqual(issues,[]);self.assertEqual(skipped,2)
        t=core.aggregate([r for r in rows if not r['control']],D)
        self.assertEqual(t['summary'][0],dict(view='overall',samples=2,patients=1,received_samples=1,received_patients=1))
        self.assertEqual({r['view'] for r in t['summary']},{'overall','specimen_visit'})
        self.assertFalse(any('center' in r for key in ('summary','receipt','measurements','availability') for r in t[key]))
        self.assertTrue(any('center' in r for r in t['audit_detail']['summary']))
        receipts=[r for r in t['receipt'] if r['view']=='overall']
        self.assertEqual([r['classified_percentage'] for r in receipts],[.5,.5])
        self.assertEqual(len(t['missed']),1)
        # A repeated row is another sample, not another patient.
        duplicate=core.aggregate([rows[0],rows[0]],D)
        self.assertEqual(duplicate['summary'][0]['samples'],2)
        self.assertEqual(duplicate['summary'][0]['patients'],1)
        pooled=core.aggregate(rows,D,pooled=True)
        self.assertFalse(pooled['receipt'])
        self.assertNotIn('cfdna_fraction',{m['field'] for m in pooled['measurements']})
        self.assertNotIn('elution_volume_ul',{m['field'] for m in pooled['measurements']})
        self.assertTrue(all(m['total'] is None for m in t['measurements'] if 'concentration' in m['field']))

    def test_good_run_reports_figures_privacy_and_hashes(self):
        destination=self.root/'native';a=self.args(destination)
        before=[digest(self.retro),digest(self.circall)]
        self.assertEqual(runner.run(a),0)
        record=json.loads((destination/'run_manifest.json').read_text())
        self.assertEqual(record['quality_status'],'no_issues_detected')
        runner.validate_results(destination,record)
        self.assertTrue(list(destination.rglob('*.png')));self.assertTrue(list(destination.rglob('*.pdf')))
        self.assertEqual(before,[digest(self.retro),digest(self.circall)])
        for path in destination.rglob('statistics.xlsx'):
            with ZipFile(path) as z:
                payload=b''.join(z.read(n) for n in z.namelist() if n.endswith('.xml'))
            self.assertNotIn(b'SYNTHETIC-SAMPLE',payload)
        with self.assertRaises(FileExistsError):runner.run(a)

    def test_independent_gate_and_controls(self):
        fixture(self.retro,'retrospective',bad=True)
        destination=self.root/'blocked'
        with patch('analysis.sample_statistics.runner.figures',return_value=[]):self.assertEqual(runner.run(self.args(destination)),0)
        record=json.loads((destination/'run_manifest.json').read_text());runner.validate_results(destination,record)
        self.assertEqual({c['cohort']:c['statistics_status'] for c in record['cohorts']},{'retrospective':'blocked','circall':'complete','pooled':'blocked'})
        self.assertEqual(record['quality_status'],'errors_found')
        self.assertFalse(json.loads((destination/'retrospective/statistics.json').read_text())['tables'])
        wb=load_workbook(self.circall);wb['cohorte_control'].cell(2,1,'=1/0');wb.save(self.circall);wb.close()
        # A missing selected control sheet blocks CIRCALL; exclusion permits the patient sheet.
        wb=load_workbook(self.circall);del wb['cohorte_control'];wb.save(self.circall);wb.close()
        for include,expected in [(True,'errors_found'),(False,'no_issues_detected')]:
            out=self.root/str(include)
            with patch('analysis.sample_statistics.runner.figures',return_value=[]):runner.run(self.args(out,'circall',include))
            self.assertEqual(json.loads((out/'run_manifest.json').read_text())['quality_status'],expected)

    def test_reference_controls_reach_all_scopes_without_entering_patient_rows(self):
        donors=self.root/'donors.xlsx'
        book=Workbook();sheet=book.active;sheet.title='Feuil1'
        sheet.append(['Donor','Conc ng/mL  plasma  ','Conc ng'])
        sheet.append(['SYNTHETIC-DONOR',2.5,None]);book.save(donors);book.close()
        for include in (True,False):
            destination=self.root/f'reference-{include}'
            args=self.args(destination,controls=include);args.donors=donors
            with patch('analysis.sample_statistics.runner.figures',return_value=[]) as plots:
                runner.run(args)
            patient_calls=[call for call in plots.call_args_list if not call.kwargs.get('controls')]
            self.assertEqual(len(patient_calls),3)
            for call in patient_calls:
                self.assertTrue(all(not r['control'] for r in call.args[1]))
                refs=call.kwargs['reference_controls']
                self.assertEqual(bool(refs),include)
                self.assertTrue(all(r['control'] for r in refs))
                self.assertEqual({r['cohort'] for r in refs},{'circall','retrospective'} if include else set())

    def test_missing_source_and_standalone_nonzero(self):
        self.retro.unlink()
        out=self.root/'standalone'
        with patch('analysis.sample_statistics.runner.figures',return_value=[]),redirect_stdout(StringIO()),redirect_stderr(StringIO()):
            result=layer_main('sample_statistics', ['--inventory',str(self.retro),'--circall',str(self.circall),'--assessment-time',ASOF,'--output-dir',str(out)])
        self.assertEqual(result,1)
        self.assertTrue((out/'circall/statistics.xlsx').is_file())
        with redirect_stdout(StringIO()),redirect_stderr(StringIO()):self.assertEqual(layer_main('sample_statistics', ['--circall',str(self.circall),'--cohort','circall','--output-dir',str(out)]),1)

    def test_failed_figures_are_not_published(self):
        from analysis.outputs import deliverables
        native=self.root/'native'
        (native/'circall').mkdir(parents=True)
        (native/'circall/statistics.xlsx').touch()
        (native/'circall/partial.png').touch()
        record={'cohorts':[{'cohort':'circall','report_status':'complete','statistics_status':'execution_failed'}],
                'artifacts':[{'path':'circall/statistics.xlsx'},{'path':'circall/partial.png'}]}
        self.assertEqual(deliverables('sample_statistics',native,record),{'circall/statistics.xlsx':'circall/statistics.xlsx'})

    def test_identity_gate(self):
        fixture(self.retro,'retrospective',names=True)
        rows,issues,skipped=core.prepare(self.retro,'retrospective',False,core.assessment(ASOF),D)
        self.assertTrue(any(i['reason']=='identity_migration_pending' for i in issues))




if __name__=='__main__':unittest.main()
