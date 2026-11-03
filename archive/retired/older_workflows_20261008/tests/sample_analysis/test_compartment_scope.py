"""Regression checks for the requested compartment and cohort exclusions."""
import unittest
import pandas as pd
from analysis.sample_analysis import analyses
from analysis.sample_analysis import reporting
from tests.fixtures.sample_analysis import fixture


class CompartmentScopeTests(unittest.TestCase):
    def test_blood_volume_and_retrospective_elution_are_absent(self):
        data=fixture()
        data['blood_volume_ml']=100
        summary=analyses.measurement_summary(data,['volume_ml','blood_volume_ml','elution_volume_uL'])
        self.assertNotIn('blood_volume_ml',set(summary.measurement))
        self.assertFalse((summary.cohort.eq('retrospective') & summary.measurement.eq('elution_volume_uL')).any())
        ret,_=analyses.correlations(data,'retrospective')
        circ,_=analyses.correlations(data,'circall')
        self.assertNotIn('elution_volume_uL',set(ret.variable_x))
        self.assertIn('elution_volume_uL',set(circ.variable_x))

    def test_circall_pellet_selected_by_compartment_without_retrospective_id(self):
        data=fixture().loc[lambda f:f.cohort.eq('circall')].copy()
        data['compartment']='blood pellet'
        other=data.iloc[[0]].copy();other['compartment']='bone marrow';other['dna_total_ng']=1e9
        summary=analyses.blood_pellet_summary(pd.concat([data,other]),['circall'])
        total=summary.loc[summary.timepoint.eq('Overall') & summary.measurement.eq('dna_total_ng')].iloc[0]
        self.assertEqual(total.measured_records,len(data))
        self.assertEqual(total.total,data.dna_total_ng.sum())
        self.assertEqual(set(summary.compartment),{'blood pellet'})
        self.assertEqual(set(summary.measurement),{'dna_total_ng','dna_concentration_ng_per_uL'})

    def test_cross_compartment_plots_are_rejected(self):
        data=fixture();data.loc[0,'compartment']='CSF'
        with self.assertRaisesRegex(ValueError,'one compartment'):
            reporting.volume_plot(data,['retrospective','circall'],'volume_ml','unused.png')
        with self.assertRaisesRegex(ValueError,'one compartment'):
            reporting.inventory_plot(analyses.availability(data),['retrospective','circall'],'unused.png')


if __name__=='__main__':unittest.main()
