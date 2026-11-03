"""MRD is patient-level; categorical display positions are not measurements."""
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import matplotlib.pyplot as plt
import pandas as pd
from openpyxl import Workbook

from analysis.sample_analysis import mrd
from analysis.cli import arguments


class MRDTests(unittest.TestCase):
    def workbook(self, rows):
        directory=tempfile.TemporaryDirectory();self.addCleanup(directory.cleanup)
        path=Path(directory.name)/'synthetic_mrd.xlsx'
        book=Workbook();sheet=book.active;sheet.title='cohorte_lal'
        sheet.append(['circall_id','MRD_TP1','MRD_TP2'])
        for row in rows:sheet.append(row)
        book.save(path);book.close()
        return path

    def test_repeated_fields_are_counted_once_and_categories_are_not_numeric(self):
        path=self.workbook([
            ['synthetic_a',1e-4,'negative'], ['synthetic_a',1e-4,'Negative'],
            ['synthetic_b','unknown significance',None], ['synthetic_c','na','n/a'],
        ])
        data=mrd.observations(path,unknown_level=1e-6,negative_level=1e-8)
        self.assertEqual(data.patient_key.nunique(),2)
        self.assertEqual(len(data),6)
        self.assertEqual(data.loc[data.status.eq('quantified'),'measured_log10_reduction'].item(),4)
        for status,level in [('negative',1e-8),('unknown_significance',1e-6)]:
            row=data.loc[data.status.eq(status)].iloc[0]
            self.assertTrue(pd.isna(row.measured_fraction))
            self.assertTrue(pd.isna(row.measured_log10_reduction))
            self.assertEqual(row.display_fraction,level)
        self.assertEqual(data.loc[data.status.eq('quantified'),'repeated_source_entries'].item(),2)
        summary=mrd.summary_table(data).set_index('timepoint')
        self.assertEqual(summary.loc['TP1 (D29)','patients_with_result'],2)
        self.assertEqual(summary.loc['TP2 (D71)','missing'],1)

    def test_conflicts_fail_instead_of_choosing_or_averaging(self):
        path=self.workbook([['synthetic_a',1e-4,None],['synthetic_a',1e-5,None]])
        with self.assertRaisesRegex(ValueError,'Conflicting patient-level'):
            mrd.observations(path,unknown_level=1e-6,negative_level=1e-8)

    def test_unconfirmed_or_invalid_values_fail(self):
        for value in (0,-1,2,float('inf'),True,'positive', '<1e-6'):
            with self.subTest(value=value),self.assertRaises(ValueError):mrd.parse_value(value,'B2')
        self.assertEqual(mrd.parse_value('na','B2'),('missing',None))
        self.assertEqual(mrd.parse_value('2,5e-5','B2'),('quantified',2.5e-5))

    def test_plot_has_three_visits_and_all_patient_endpoints(self):
        path=self.workbook([['synthetic_a',1e-4,'negative'],['synthetic_b','unknown significance',None]])
        frame=mrd.observations(path,unknown_level=1e-6,negative_level=1e-8)
        with patch.object(mrd.reporting,'save') as save:
            mrd.plot(frame,'unused.png',unknown_level=1e-6,negative_level=1e-8)
        fig=save.call_args.args[0];ax=fig.axes[0]
        self.assertEqual([t.get_text() for t in ax.get_xticklabels()],['D1\nn=2','TP1 (D29)\nn=2','TP2 (D71)\nn=1'])
        self.assertEqual(len(ax.collections),5)
        self.assertEqual(ax.get_yscale(),'log')
        plt.close(fig)

    def test_cli_records_user_display_conventions(self):
        args=arguments(['--cohort','circall','--analysis','mrd','--circall','explicit.xlsx'])
        self.assertEqual(args.mrd_unknown_level,1e-6)
        self.assertEqual(args.mrd_negative_level,1e-8)


if __name__=='__main__':unittest.main()
