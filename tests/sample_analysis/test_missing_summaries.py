import unittest
import pandas as pd

from analysis.sample_analysis.analyses import missing_samples_by_hospital, missing_samples_list


class MissingSummaryTests(unittest.TestCase):
    def test_missing_list_combines_blood_fractions_and_excludes_future_visits(self):
        records = [
            ('001-A','diag','plasma','explicit_missing'),
            ('001-A','diag','blood pellet','explicit_missing'),
            ('001-A','d4','plasma','present'),
            ('001-A','d4','blood pellet','explicit_missing'),
            ('001-A','d8','plasma','explicit_missing'),
            ('001-A','d8','blood pellet','present'),
            ('001-A','tp2','CSF','blank'),
            ('002-B','tp1','plasma','blank'),
            ('002-B','tp1','blood pellet','explicit_missing'),
            ('003-C','tp1,5','CSF','explicit_missing'),
            ('003-C','tp1,5','CSF','explicit_missing'),
            ('003-C','diag','bone marrow','explicit_missing'),
            ('','diag','CSF','explicit_missing'),
        ]
        data = pd.DataFrame(records, columns=['patient_id','timepoint','compartment','sample_state'])
        data['cohort']='circall'; data['is_control']=False; data['qc_hold']=True
        other = data.iloc[[0]].copy(); other['patient_id']='excluded'; other['cohort']='retrospective'
        control = other.copy(); control['cohort']='circall'; control['is_control']=True
        result = missing_samples_list(pd.concat([data, other, control], ignore_index=True))
        self.assertEqual(list(result.columns), ['circall_id','timepoint','compartment'])
        self.assertEqual(list(result.itertuples(index=False, name=None)), [
            ('001-A','diag','peripheral blood'),
            ('002-B','tp1','peripheral blood'),
            ('003-C','diag','bone marrow'),
            ('003-C','tp1,5','CSF'),
        ])
        empty = missing_samples_list(data.iloc[:0])
        self.assertTrue(empty.empty)
        self.assertEqual(list(empty.columns), list(result.columns))

    def test_denominators_and_noncanonical_visits(self):
        records = [
            ('RDB','a','diag','plasma','present'),
            ('RDB','a','diag','blood pellet','explicit_missing'),
            ('RDB','b','tp2','CSF','blank'),
            ('TRS','c','tp1','CSF','explicit_missing'),
            ('TRS','c','tp1,5','CSF','present'),
            ('unknown','d','diag','plasma','explicit_missing'),
        ]
        data = pd.DataFrame(records, columns=['hospital','patient_key','timepoint','compartment','sample_state'])
        data['cohort']='circall';data['is_control']=False;data['qc_hold']=True
        other = data.iloc[[0]].copy();other['cohort']='retrospective'
        data=pd.concat([data, other], ignore_index=True)
        tables=missing_samples_by_hospital(data)
        time=tables['missing_samples_by_hospital_timepoint'].set_index('hospital')
        comp=tables['missing_samples_by_hospital_compartment'].set_index('hospital')
        self.assertEqual(time.loc['RDB','affected_patients'],'1/2 (50.0%)')
        self.assertEqual(time.loc['RDB','all_assessed_samples'],'1/2 (50.0%)')
        self.assertEqual(time.loc['TRS','TP1'],'1/1 (100.0%)')
        self.assertEqual(time.loc['TRS','all_assessed_samples'],'1/2 (50.0%)')
        self.assertEqual(time.loc['Overall','all_assessed_samples'],'2/4 (50.0%)')
        self.assertEqual(comp.loc['Overall','CSF'],'1/2 (50.0%)')
        self.assertEqual(time.loc['RDB','TP2'],'0/0 (0.0%)')
        self.assertEqual(list(comp.index),['RDB','TRS','Overall'])

    def test_empty_inventory_keeps_legacy_layout(self):
        data=pd.DataFrame(columns=['cohort','is_control','patient_key','hospital','timepoint','compartment','sample_state'])
        tables=missing_samples_by_hospital(data)
        self.assertEqual(tables['missing_samples_by_hospital_compartment'].shape,(3,6))
        self.assertEqual(tables['missing_samples_by_hospital_timepoint'].shape,(3,9))
