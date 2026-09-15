import unittest
import numpy as np
import pandas as pd
from pre_analysis import statistics
from pre_analysis.analyses import correlations, availability, cohort_comparison
from pre_analysis.policies import eligible, pooled_controls, PRIMARY
from workflows.retrospective import stats_reporting as legacy


def fixture():
    rng=np.random.default_rng(4);rows=[]
    for cohort in ('retrospective','circall'):
        for patient in range(6):
            for tp,value in [('diag',10),('tp1',4)]:
                rows.append(dict(record_id=f'{cohort}:{patient}:{tp}',cohort=cohort,is_control=False,control_source='',patient_key=f'{cohort}:{patient}',source_row=patient,
                    sample_id=f'{patient}:{tp}',sample_key=f'{cohort}:{patient}:{tp}',sample_state='present',compartment='plasma',timepoint=tp,hospital='RDB',
                    extraction_type='cfDNA',qc_hold=False,volume_ml=2+patient,elution_volume_uL=30+patient,
                    dna_total_ng=value+patient,dna_concentration_ng_per_uL=value/3+patient/2,dna_ng_per_mL_plasma=value+rng.random()))
    for source in ('existing_controls','pediatric_controls'):
        for i in range(3):
            rows.append({**rows[0], 'record_id':f'{source}:{i}','cohort':'control','is_control':True,'control_source':source,
                         'patient_key':f'Control_{source}:{i}','timepoint':'Control',PRIMARY:1+i/3})
    return pd.DataFrame(rows)


class SharedAnalysisTests(unittest.TestCase):
    def test_controls_pool_and_exclude_unmeasured(self):
        f=fixture();f.loc[f.index[-1],PRIMARY]=np.nan
        controls=pooled_controls(f)
        self.assertEqual(len(controls),5)
        self.assertEqual(controls.control_source.nunique(),2)
        self.assertEqual(controls.patient_key.nunique(),5)

    def test_hold_exclusion_is_distinct_from_missing_measurement(self):
        f=fixture();f.loc[0,'qc_hold']=True;f.loc[1,'volume_ml']=np.nan
        data,audit=eligible(f,'retrospective','yield')
        self.assertNotIn(f.loc[0,'record_id'],set(data.record_id))
        self.assertIn(f.loc[1,'record_id'],set(data.record_id))
        summary=availability(f)
        self.assertEqual(summary.inventory_records.sum(),24)

    def test_separate_cohorts_and_correlation_minimums(self):
        f=fixture()
        for cohort in ('retrospective','circall'):
            table,_=correlations(f,cohort)
            self.assertEqual(set(table.cohort),{cohort})
            self.assertEqual(table.query("timepoint == 'Overall'").paired_sample_count.unique().tolist(),[12])
            self.assertTrue(table.query("timepoint == 'tp1'").status.eq('complete').all())
            self.assertTrue(table.query("timepoint == 'tp2'").status.eq('unavailable').all())

    def test_descriptive_cohort_comparison(self):
        f=fixture()
        f.loc[f.cohort.eq('retrospective'),PRIMARY]=2.
        f.loc[f.cohort.eq('circall'),PRIMARY]=6.
        result=cohort_comparison(f)
        diag=result.loc[result.timepoint.eq('diag')].iloc[0]
        self.assertEqual(diag.mean_difference_ng_per_ml,4.)
        self.assertEqual(diag.mean_ratio_circall_to_retrospective,3.)
        self.assertEqual(diag.mean_percent_difference,200.)
        self.assertEqual(diag.retrospective_sample_count,6)
        self.assertEqual(diag.circall_sample_count,6)
        self.assertEqual(diag.matching_basis,'timepoint label only')

    def test_statistical_refactor_matches_legacy_on_identical_values(self):
        f=fixture();patients,_=eligible(f,'retrospective','longitudinal');controls=pooled_controls(f)
        old_patients=patients.rename(columns={'patient_key':'lastname',PRIMARY:'ng_per_ml'})
        old_controls=controls.rename(columns={PRIMARY:'ng/ml plasma'})
        for unit in ('sample','patient_median'):
            args=dict(bins=['Control','diag','tp1'],unit=unit,scale='log10',correction='bh')
            expected=legacy.compute_pairwise_bins(df_patients=old_patients,donors=old_controls,**args)
            actual=statistics.compute_pairwise_bins(df_patients=patients,donors=controls,**args)
            pd.testing.assert_frame_equal(actual,expected)
        expected=legacy.compute_mannwhitney_bins(df_patients=old_patients,donors=old_controls,bins=['Control','diag','tp1'],unit='patient_median',scale='log10',correction='bh')
        actual=statistics.compute_mannwhitney_bins(df_patients=patients,donors=controls,bins=['Control','diag','tp1'],unit='patient_median',scale='log10',correction='bh')
        pd.testing.assert_frame_equal(actual,expected)


if __name__=='__main__':unittest.main()
