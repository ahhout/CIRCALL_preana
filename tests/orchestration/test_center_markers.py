"""Presentation groups preserve values, scope boundaries and residual alignment."""
from types import SimpleNamespace
import json

import matplotlib.pyplot as plt
from matplotlib.markers import MarkerStyle
from matplotlib.colors import to_rgba
import numpy as np
import pandas as pd
import pytest
import statsmodels.formula.api as smf

from analysis.plot_style import COHORT_COLORS, scatter_points, center_from_id
from analysis.provenance import ROOT


def shape(collection, marker):
    expected = MarkerStyle(marker)
    np.testing.assert_allclose(collection.get_paths()[0].vertices,
                               expected.get_path().transformed(expected.get_transform()).vertices)


def test_center_mapping_uses_established_prefixes():
    assert center_from_id('001-9001-X-Z','circall') == 'RDB'
    assert center_from_id('002-9001-X-Z','circall') == 'TRS'
    assert center_from_id('999-9001-X-Z','circall') == 'unknown'


@pytest.mark.parametrize('cohort,solo,markers',[
    ('circall',True,['s','^']), ('circall',False,['o']),
    ('retrospective',True,['^'])])
def test_scope_keeps_coordinates_and_retrospective_shape(cohort,solo,markers):
    fig,ax=plt.subplots()
    scatter_points(ax,[1,2,3],[4,5,6],cohort,['TRS','RDB','TRS'],circall_only=solo)
    for collection,marker in zip(ax.collections,markers,strict=True):
        shape(collection,marker)
        np.testing.assert_allclose(collection.get_facecolors()[0],to_rgba(COHORT_COLORS[cohort]))
    assert sorted(tuple(p) for c in ax.collections for p in c.get_offsets()) == [(1,4),(2,5),(3,6)]
    plt.close(fig)


def test_diagnostic_qq_centers_follow_sorted_residuals(tmp_path,monkeypatch):
    from analysis import association_methods as methods
    from analysis import plot_style
    frame=pd.DataFrame(dict(x=[1,2,3,4,5,6],y=[2,6,3,8,4,10],
                            center=['TRS','RDB','RDB','TRS','TRS','RDB']))
    model=smf.ols('y ~ x',data=frame).fit()
    saved=[]
    def inspect(fig,path):
        ax=fig.axes[0]
        assert {t.get_text() for t in ax.get_legend().get_texts()} == {'CIRCALL · TRS','CIRCALL · RDB'}
        if path.name=='qq_plot.png':
            expected=ax.lines[0].get_xydata()
            ordered=frame.center.to_numpy()[np.argsort(model.resid)]
            for collection,center,marker in zip(ax.collections,['RDB','TRS'],['s','^'],strict=True):
                shape(collection,marker)
                np.testing.assert_allclose(collection.get_offsets(),expected[ordered==center])
        saved.append(path.name)
    monkeypatch.setattr(plot_style,'save_figure',inspect)
    methods.plot_assumptions(model,tmp_path,cohort='circall')
    assert len(saved)==3


def test_layer4_center_shapes_and_retrospective_circle_are_preserved():
    from analysis.disease_modeling.reporting import count_figure,mrd_figure
    d=json.loads((ROOT/'configs/definitions/disease_modeling.json').read_text())
    args=SimpleNamespace(jitter_seed=42,mrd_negative_level=1e-8,mrd_unknown_level=1e-6,
                         mrd_positive_nq_level=1e-6,overlay_max_day=8,kinetics_y_scale='linear',
                         baseline_day_max=1,baseline_selection='latest')
    records=[dict(cohort='circall',subject_hash=str(i),center=center,measurement='blast',
                  selected_for_plot=True,display_day=1,day=1,value=i+1)
             for i,center in enumerate(['TRS','RDB'])]
    fig=count_figure(records,'blast',args,d)
    for c,m in zip(fig.axes[0].collections,['^','s'],strict=True):shape(c,m)
    plt.close(fig)
    for r in records:r['cohort']='retrospective'
    fig=count_figure(records,'blast',args,d)
    for c in fig.axes[0].collections:
        shape(c,'o')
        np.testing.assert_allclose(c.get_facecolors()[0][:3],to_rgba(COHORT_COLORS['retrospective'])[:3])
    plt.close(fig)
    records=[dict(cohort='circall',subject_hash=str(i),center=center,visit='TP1',
                  status='quantified',measured_fraction=.001,upper_bound_fraction=None)
             for i,center in enumerate(['TRS','RDB'])]
    fig=mrd_figure(records,'circall',args,d)
    for c,m in zip(fig.axes[0].collections,['^','s'],strict=True):shape(c,m)
    plt.close(fig)


def test_circall_layer2_shared_retro_controls_do_not_hide_center_shapes():
    from analysis.sample_statistics.reporting import grant_figure
    d=json.loads((ROOT/'configs/definitions/sample_statistics.json').read_text())
    field='dna_ng_per_ml_plasma'
    rows=[dict(cohort=cohort,center=center,control=control,specimen='plasma',
               visit='control' if control else 'diag',subject_key=str(i),
               measurements={field:dict(value=value)})
          for i,(cohort,center,control,value) in enumerate([
              ('retrospective','RDB',True,2),('circall','TRS',False,10),
              ('circall','RDB',False,20)])]
    fig=grant_figure(rows,field,d['metrics'][field],['control','diag'],False,False,42,scope='circall')
    collections=[c for c in fig.axes[0].collections if len(c.get_offsets())]
    assert sorted(float(p[1]) for c in collections for p in c.get_offsets())==[2,10,20]
    for collection in collections:
        value=float(collection.get_offsets()[0,1])
        shape(collection,'s' if value==20 else '^')
    labels=[t.get_text() for t in fig.legends[0].get_texts()]
    assert set(labels)=={'Retrospective','CIRCALL · RDB','CIRCALL · TRS'}
    plt.close(fig)
