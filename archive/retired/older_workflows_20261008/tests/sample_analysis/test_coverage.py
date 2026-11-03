"""CIRCALL receipt status and future timepoints must remain distinct."""
import unittest
import pandas as pd
from analysis.sample_analysis.analyses import availability
from tests.fixtures.sample_analysis import fixture


class CoverageTests(unittest.TestCase):
    def test_future_timepoints_are_not_missing_samples(self):
        data=fixture().loc[lambda f:f.cohort.eq('circall')].iloc[:3].copy()
        data['timepoint']='tp1'
        data['sample_state']=['present','explicit_missing','blank']
        row=availability(data).iloc[0]
        self.assertEqual(row.inventory_records,3)
        self.assertEqual(row.not_received_records,1)
        self.assertEqual(row.timepoint_not_yet_reached_records,1)
        self.assertEqual(row.assessed_records,2)
        self.assertEqual(row.missing_rate,.5)
        data['sample_state']='blank'
        row=availability(data).iloc[0]
        self.assertEqual(row.assessed_records,0)
        self.assertTrue(pd.isna(row.missing_rate))
        data['cohort']='retrospective'
        row=availability(data).iloc[0]
        self.assertTrue(pd.isna(row.timepoint_not_yet_reached_records))


if __name__=='__main__':unittest.main()
