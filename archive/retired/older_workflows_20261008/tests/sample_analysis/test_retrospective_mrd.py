"""Retrospective MRD keeps visit identity, censoring, and conflict safeguards."""
import json
from pathlib import Path
from unittest.mock import patch

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest
from openpyxl import Workbook

from analysis.cli import arguments
from analysis.sample_analysis import retrospective_mrd as mrd
from analysis.sample_analysis.runner import selection


def workbook(tmp_path, rows):
    path=tmp_path/'synthetic.xlsx'
    book=Workbook();sheet=book.active;sheet.title='Inventaire'
    sheet.append(['lastname','treatment_phase','MRD_IgTCR','tissue'])
    for row in rows:sheet.append([*row,'Moelle'] if len(row)==3 else row)
    book.save(path);book.close()
    return path


def test_numeric_fraction_and_nonquantifiable_bound_are_distinct():
    assert mrd.parse_annotation(.001,'C2') == ('quantified',.001,None)
    for token, bound in [('pos NQ <10-4',1e-4),('POS NQ <5.10-5',5e-5),('pos nq < 0,0001',1e-4)]:
        status,value,limit=mrd.parse_annotation(token,'C2')
        assert status=='positive_nonquantifiable' and value is None
        assert limit==pytest.approx(bound)
    assert mrd.parse_annotation('pos NQ','C2') == ('positive_nonquantifiable',None,None)
    for invalid in ('pos NQ <nonsense','pos NQ <0','pos NQ <2','pos NQ >10-4',0,True,'unknown significance'):
        with pytest.raises(ValueError):mrd.parse_annotation(invalid,'C2')


def test_visits_separate_repeats_collapse_and_other_phases_excluded(tmp_path):
    source=workbook(tmp_path,[['Synthetic A','tp1',.001],['Synthetic A','TP1',.001],
        ['Synthetic A','tp2','pos NQ <10-4'],['Synthetic A','diag','ignored annotation'],
        ['Synthetic B','tp1','na'],['Synthetic B','tp2','negative']])
    data=mrd.observations(source)
    assert len(data)==4
    quantified=data.loc[data.status.eq('quantified')].iloc[0]
    assert quantified.measured_log10_reduction==3
    assert quantified.repeated_source_entries==2
    nq=data.loc[data.status.eq('positive_nonquantifiable')].iloc[0]
    assert pd.isna(nq.measured_fraction) and pd.isna(nq.measured_log10_reduction)
    assert nq.reported_upper_bound_fraction==pytest.approx(1e-4)
    summary=mrd.summary_table(data).set_index('timepoint')
    assert summary.loc['TP1','patients_with_result']==1
    assert summary.loc['TP2','patients_with_result']==2
    assert summary.loc['TP1','missing']==1
    assert 'Synthetic' not in data.patient_key.str.cat()


def test_explicit_error_policy_stops_before_creating_output(tmp_path):
    source=workbook(tmp_path,[['Synthetic A','tp1',.001],['Synthetic A','TP1','negative']])
    output=tmp_path/'results'
    with pytest.raises(mrd.MRDConflictError) as error:
        mrd.run(source,output,negative_level=1e-8,duplicate_policy="error")
    assert not output.exists()
    assert 'Synthetic' not in str(error.value)
    conflict=error.value.conflicts[0]
    assert conflict['timepoint']=='TP1'
    assert set(json.loads(conflict['source_cells']))=={'C2','C3'}
    assert set(json.loads(conflict['treatment_phase_cells']))=={'B2','B3'}
    assert 'patient_key' not in conflict


def test_outputs_are_aggregate_and_figure_uses_recorded_visits(tmp_path):
    source=workbook(tmp_path,[['Synthetic A','tp1',.001],['Synthetic A','tp2',.0001],
        ['Synthetic B','tp1','pos NQ <5.10-4'],['Synthetic B','tp2','negative']])
    out=tmp_path/'result';mrd.run(source,out,negative_level=1e-8)
    assert {p.name for p in out.iterdir()}=={'retrospective_mrd_summary.csv','retrospective_plot_settings.json','retrospective_mrd_trajectories.png'}
    assert 'patient_key' not in pd.read_csv(out/'retrospective_mrd_summary.csv')
    data=mrd.observations(source)
    with patch.object(mrd.reporting,'save') as save:mrd.plot(data,out/'unused.png',negative_level=1e-8)
    fig=save.call_args.args[0];ax=fig.axes[0]
    assert [v.get_text() for v in ax.get_xticklabels()]==['TP1\nn=2 results','TP2\nn=2 results']
    assert len(ax.lines)==1  # Quantified pair only; no false trajectory to a bound.
    plt.close(fig)


def test_retrospective_mrd_is_selectable_and_uses_inventory():
    args=arguments(['--analysis','mrd','--cohort','retrospective','--circall','synthetic_circall.xlsx'])
    cohorts,tasks,inputs=selection(args)
    assert cohorts==['retrospective'] and tasks==['mrd']
    assert inputs['inventory']==args.inventory


def test_tissue_filter_precedes_mrd_parsing_and_conflict_detection(tmp_path):
    source=workbook(tmp_path,[['Synthetic A','tp1',.001,' Moelle '],
        ['Synthetic A','tp1','negative','Sang'],
        ['Synthetic A','tp2','pos NQ <10-4','MOELLE'],
        ['Synthetic B','tp1','invalid annotation','LCR'],
        ['Synthetic C','diag','invalid annotation','Moelle']])
    data=mrd.observations(source)
    assert data.timepoint.tolist()==['TP1','TP2']
    assert data.status.tolist()==['quantified','positive_nonquantifiable']
    blood=mrd.observations(source,tissue='Sang')
    assert blood.status.tolist()==['negative']


def test_worst_outcome_priority_resolves_within_each_visit(tmp_path):
    source=workbook(tmp_path,[['Synthetic A','tp1','negative'],
        ['Synthetic A','tp1','pos NQ <10-4'],['Synthetic A','tp1',1e-6],['Synthetic A','tp1',.001],
        ['Synthetic A','tp2','negative'],['Synthetic A','tp2','pos NQ <10-5'],['Synthetic A','tp2','pos NQ <5.10-4'],
        ['Synthetic B','tp1','negative'],['Synthetic B','tp1','na'],['Synthetic C','tp1','na']])
    data=mrd.observations(source)
    quantified=data.loc[data.status.eq('quantified')].iloc[0]
    assert quantified.measured_fraction==.001
    assert quantified.distinct_source_annotations==4
    assert quantified.resolved_disagreement
    nq=data.loc[data.status.eq('positive_nonquantifiable')].iloc[0]
    assert nq.timepoint=='TP2' and pd.isna(nq.measured_fraction)
    assert nq.reported_upper_bound_fraction==pytest.approx(5e-4)
    assert data.status.value_counts().to_dict()=={'quantified':1,'positive_nonquantifiable':1,'negative':1,'missing':1}
    assert mrd.summary_table(data).resolved_disagreements.sum()==2


def test_numeric_category_priority_is_not_replaced_by_bound_magnitude(tmp_path):
    source=workbook(tmp_path,[['Synthetic A','tp1',1e-6],['Synthetic A','tp1','pos NQ <10-3']])
    row=mrd.observations(source).iloc[0]
    assert row.status=='quantified' and row.measured_fraction==1e-6
