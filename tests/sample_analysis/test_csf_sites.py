import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from analysis.sample_analysis import analyses
from analysis.sample_analysis import reporting


class CSFSiteTests(unittest.TestCase):
    def test_site_means_missingness_and_scope(self):
        frame = pd.DataFrame({
            'cohort': ['circall'] * 6 + ['retrospective'],
            'compartment': ['CSF'] * 5 + ['plasma','CSF'],
            'qc_hold': [False,False,False,False,True,False,False],
            'hospital': ['RDB','RDB','TRS','unknown','TRS','RDB','RDB'],
            'timepoint': ['diag','tp1','tp1','diag','diag','diag','diag'],
            'volume_ml': [2, np.nan, 4, 3, 999, 888, 777],
            'patient_key': ['a','b','c','d','e','f','g'],
        })
        result = analyses.csf_volumes_by_site(frame).set_index('hospital')
        self.assertEqual(result.loc['RDB','mean_volume_ml'],2)
        self.assertEqual(result.loc['RDB','unavailable_records'],1)
        self.assertEqual(result.loc['TRS','mean_volume_ml'],4)
        self.assertEqual(result.loc['unknown','measured_records'],1)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'csf.png'
            reporting.csf_site_boxplot(frame,path)
            self.assertTrue(path.is_file())

    def test_empty_sites_can_be_reported(self):
        frame = pd.DataFrame(columns=['cohort','compartment','qc_hold','hospital','timepoint','volume_ml','patient_key'])
        result = analyses.csf_volumes_by_site(frame)
        self.assertTrue(result.empty)
