"""Synthetic compatibility observations, never clinical data."""
import numpy as np
import pandas as pd
from analysis.sample_analysis.policies import PRIMARY

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


