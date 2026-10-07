from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from openpyxl import Workbook
from analysis.provenance import ROOT
from analysis.data_integrity.checks import load_rules
from analysis.retrospective_controls import inspect_with_controls,observations
from analysis.sample_statistics.core import load_definitions,aggregate
from analysis.sample_statistics.runner import arguments,run,validate_results
from tests.sample_statistics.test_statistics import fixture,ASOF
import json

class DonorTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.source=self.root/'patient.xlsx';fixture(self.source,'retrospective')
        self.donors=self.root/'donor.xlsx';b=Workbook();w=b.active;w.title='Feuil1';w.append(['Donor','Conc ng/mL  plasma  ','Conc ng'])
        w.append(['PRIVATE_DONOR_A',2.5,None]);w.append(['PRIVATE_DONOR_B',0,None]);b.save(self.donors);b.close()
        self.rules=load_rules(ROOT/'configs/definitions/data_integrity.json');self.d=load_definitions(ROOT/'configs/definitions/sample_statistics.json')

    def test_donor_schema_and_control_only_summary(self):
        r=inspect_with_controls(self.source,'retrospective',True,self.rules,self.donors)
        self.assertEqual(r['summary']['errors'],0)
        self.assertEqual([s['sheet'] for s in r['sheets']],['Inventaire','Feuil1'])
        self.assertNotIn('PRIVATE_DONOR',json.dumps(r))
        rows,issues=observations(self.donors,self.d);self.assertFalse(issues)
        summary=aggregate(rows,self.d)
        metric=next(m for m in summary['measurements'] if m['field']=='dna_ng_per_ml_plasma' and m['view']=='specimen')
        self.assertEqual(metric['n'],2);self.assertEqual(metric['mean'],1.25)
        self.assertTrue(all(r['classified_percentage'] is None for r in summary['receipt']))
        self.assertTrue(all(r['control'] for r in rows))

    def test_missing_controls_gate_and_exclusion(self):
        self.donors.unlink()
        self.assertGreater(inspect_with_controls(self.source,'retrospective',True,self.rules,self.donors)['summary']['errors'],0)
        self.assertEqual(inspect_with_controls(self.source,'retrospective',False,self.rules,self.donors)['summary']['errors'],0)

    def test_execution_publishes_controls_and_excludes_patient_totals(self):
        out=self.root/'native'
        a=arguments(['--inventory',str(self.source),'--donors',str(self.donors),'--cohort','retrospective','--assessment-time',ASOF,'--output-dir',str(out)])
        self.assertEqual(run(a),0)
        record=json.loads((out/'run_manifest.json').read_text());validate_results(out,record)
        self.assertIn('retrospective_controls',record['inputs'])
        r=json.loads((out/'retrospective/statistics.json').read_text())
        self.assertEqual(r['tables']['summary'][0]['patients'],1)
        self.assertEqual(r['controls']['summary'][0]['patients'],2)
        self.assertTrue(list((out/'retrospective/figures/controls').rglob('*.png')))
        from openpyxl import load_workbook
        b=load_workbook(out/'retrospective/statistics.xlsx');self.assertIn('Controls',b.sheetnames);b.close()

if __name__=='__main__':unittest.main()
