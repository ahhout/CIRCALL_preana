"""Diagnosis timing stays distinct from MRD/follow-up; pooling needs both cohorts."""
from pathlib import Path
from unittest.mock import patch
import json

from openpyxl import Workbook
import numpy as np
import pandas as pd
import pytest

from analysis.cfdna_associations import diagnosis
from analysis.cfdna_associations import analyze_blast_cfdna as engine
from tests.fixtures.associations import toy_cohort, row
from analysis import artifacts, outputs


def source(tmp_path, rows):
    p=tmp_path/'circall.xlsx';book=Workbook();sheet=book.active;sheet.title='cohorte_lal'
    sheet.append(['circall_id','timepoint','compartment','sample_id','cfDNA_ng_per_mL_plasma',
                  'genetic_subtype','diag_blood_blast_pct','diag_bm_blast_pct','diag_blood_wbc_x10*9/L'])
    for record in rows:sheet.append(record)
    book.save(p);book.close();return p


def test_circall_requires_diag_and_preserves_percent_units_and_missing_fields(tmp_path):
    p=source(tmp_path,[['synthetic','diag','plasma','S1',100,'A',.2,.7,15],
        ['synthetic','diag','plasma','S2',300,'A',.2,.7,15],
        ['synthetic','tp1','plasma','S3',900,'B',.8,.9,100],
        ['another','diag','plasma','na',200,'A',.1,.8,9]])
    data,counts=diagnosis.prepare_circall(p)
    assert len(data)==1 and data.cfdna_ng_per_ml.iat[0]==200
    assert data.peripheral_blast_percent.iat[0]==20 and data.tumor_fraction_percent.iat[0]==70
    assert data.gb_per_l.iat[0]==15
    assert data.sex.isna().all() and data.age_diag.isna().all()
    assert not {'circall_id','patient_key','lastname'} & set(data)
    assert counts['diagnosis_rows']==3


def test_circall_diagnostic_metadata_conflicts_fail_without_identifiers(tmp_path):
    p=source(tmp_path,[['synthetic-secret','diag','plasma','S1',100,'A',.2,.7,15],
        ['synthetic-secret','diag','plasma','S2',100,'A',.3,.7,15]])
    with pytest.raises(ValueError,match='Conflicting CIRCALL diagnosis metadata') as error:
        diagnosis.prepare_circall(p)
    assert 'synthetic-secret' not in str(error.value)


def test_retrospective_wbc_and_marrow_are_not_borrowed_from_tp1():
    data=pd.DataFrame([row('Synthetic','Sang','cfDNA',.2,100,gb_per_l=np.nan),
                       row('Synthetic','Moelle','MNC celDNA',.8,phase='TP1',gb_per_l=50)])
    frame,_=engine.prepare_cohort(data,engine.CohortConfig())
    assert frame.gb_per_l.isna().all()
    assert frame.tumor_fraction_percent.isna().all()


def test_two_cohorts_skip_missing_variables_and_pool_only_comparable_fields(tmp_path):
    p=source(tmp_path,[[f'C{i}','diag','plasma',f'S{i}',10**(1+i*.12),'A' if i%2 else 'B',.1+i*.05,.5+i*.03,10+i]
                       for i in range(6)])
    retro=toy_cohort();retro['cfdna_ng_per_ml']*=np.exp(np.random.default_rng(4).normal(0,.1,len(retro)))
    out=tmp_path/'cfdna_associations'
    scopes,coverage,_=diagnosis.write(out,retro,{},p,predictors=['peripheral_blast_percent'])
    available=pd.DataFrame(coverage)
    assert len(available)==24
    assert available.query("cohort == 'circall' and predictor == 'sex'").status.iat[0]=='skipped'
    assert available.query("cohort == 'pooled' and predictor == 'gb_per_l'").status.iat[0]=='skipped'
    assert available.query("cohort == 'pooled' and predictor == 'peripheral_blast_percent'").status.iat[0]=='available'
    assert not (out/'circall/cfDNA_age_diag').exists()
    assert not (out/'pooled/cfDNA_vs_peripheral_blood_wbc_count').exists()
    assert not list((out/'pooled').rglob('results.csv'))
    assert set(pd.read_csv(out/'pooled/cfDNA_vs_peripheral_blood_blast_percent/analysis_data.csv').cohort)=={'retrospective','circall'}
    assert len(list(out.rglob('results.csv')))==2
    artifacts.associations(out,[],scopes=scopes)
    selected=outputs.deliverables('cfdna_associations',tmp_path,{'details':{'scopes':scopes}})
    assert selected['cfdna_associations/diagnosis_availability.csv']=='diagnosis_availability.csv'
    assert 'pooled/cfDNA_vs_peripheral_blood_blast_percent/log10_cfDNA_ng_per_mL_vs_peripheral_blood_blast_percent.png' in selected.values()
    assert 'circall/cfDNA_vs_peripheral_blood_blast_percent/results.csv' in selected.values()


def test_absent_diagnostic_cfdna_stays_unavailable_without_followup_fallback(tmp_path):
    p=source(tmp_path,[['synthetic','tp1','plasma','S1',100,'A',.2,.7,15],
                       ['synthetic','diag','plasma','S2',None,'A',.2,.7,15]])
    frame,counts=diagnosis.prepare_circall(p)
    assert frame.empty and counts['analysis_patients']==0
    assert diagnosis.coverage({'circall':frame}).status.eq('skipped').all()


def test_confirmed_wbc_pools_without_deriving_blasts_or_inventing_marrow(tmp_path):
    path = source(tmp_path, [[f'C{i}', 'diag', 'plasma', f'S{i}', 10**(1+i*.12), 'A',
                              .1+i*.05, .5+i*.03, 10+i] for i in range(6)])
    retro = toy_cohort()
    retro['tumor_fraction_percent'] = np.nan
    original = retro.copy(deep=True)
    output = tmp_path/'confirmed'
    scopes, coverage, _ = diagnosis.write(output, retro, {}, path,
        predictors=['peripheral_blast_percent'], retrospective_wbc_unit='x10^9/L')
    available = pd.DataFrame(coverage)
    wbc = available.query("cohort == 'pooled' and predictor == 'gb_per_l'").iloc[0]
    assert wbc.status == 'available' and wbc.n == 18 and wbc.unit == 'x10^9/L'
    assert (output/'pooled/cfDNA_vs_peripheral_blood_wbc_count/log10_cfDNA_ng_per_mL_vs_peripheral_blood_wbc_count.png').is_file()
    assert (output/'circall/cfDNA_vs_bone_marrow_blast_percent/log10_cfDNA_ng_per_mL_vs_bone_marrow_blast_percent.png').is_file()
    assert not (output/'pooled/cfDNA_vs_bone_marrow_blast_percent').exists()
    assert available.query("predictor == 'peripheral_blast_count'").status.eq('skipped').all()
    assert not list(output.rglob('*peripheral_blast_count*'))
    assert not list((output/'pooled').rglob('results.csv'))
    pd.testing.assert_frame_equal(retro, original)
    settings = json.loads((output/'diagnosis_settings.json').read_text())
    assert settings['retrospective_wbc_unit'] == 'x10^9/L'
    artifacts.associations(output, [], scopes=scopes)
