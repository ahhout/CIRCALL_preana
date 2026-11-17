"""Calendar collection-volume plots preserve samples, dates, zeros and provenance."""
from copy import deepcopy
from datetime import date, datetime, timezone
import json

import matplotlib.pyplot as plt
from matplotlib.dates import date2num
from openpyxl import load_workbook
import pytest

from analysis.provenance import ROOT
from analysis.utils.sample_io import SourceCell
from analysis.sample_statistics.step_01_prepare import load_definitions, prepare, assessment
from analysis.sample_statistics.calendar_volumes import (
    FIELD, collection_date, calendar_coverage, calendar_groups,
    calendar_points, calendar_figure, validate_calendar_dates)
from tests.fixtures.sample_statistics import fixture, ASOF

D=load_definitions(ROOT/'configs/definitions/sample_statistics.json')


def cell(value, **changes):
    arguments=dict(coordinate='A2',row=2,column=1,raw=value,value=value,data_type='d',
                   cached_type='d',number_format='yyyy-mm-dd',formula=None)
    arguments.update(changes)
    return SourceCell(**arguments)


@pytest.mark.parametrize('value,state,expected',[
    (datetime(2026,2,3,14,30),'recorded_date','2026-02-03'),
    (date(2026,2,3),'recorded_date','2026-02-03'),
    ('2026-02-03','not_a_recorded_date',None),
    (45000,'not_a_recorded_date',None),
    (True,'not_a_recorded_date',None),
    ('?','unknown',None),('na','missing',None),(None,'missing',None),
    (datetime(2026,2,3,tzinfo=timezone.utc),'timezone_unresolved',None),
])
def test_only_typed_collection_dates_are_usable(value,state,expected):
    assert collection_date(cell(value),D)==dict(value=expected,state=state)


def test_date_errors_and_formula_caches_remain_distinct():
    assert collection_date(None,D)['state']=='field_unavailable'
    assert collection_date(cell('#VALUE!',data_type='e'),D)['state']=='excel_error'
    assert collection_date(cell(None,formula='=A1',data_type='f',cached_type='n'),D)['state']=='cache_unavailable'
    assert collection_date(cell(None,formula='=A1',data_type='f',cached_type='str'),D)['state']=='intentional_empty'
    assert collection_date(cell(date(2026,2,3),formula='=A1',data_type='f'),D)==dict(value='2026-02-03',state='cached_date')


def row(subject='synthetic',specimen='plasma',value=2,day='2026-02-03',**changes):
    result=dict(cohort='circall',control=False,specimen=specimen,assay='cfdna',
                visit='diag',receipt='received',subject_key=subject,
                measurements={FIELD:dict(value=value,state='available')},
                collection_date=dict(value=day,state='recorded_date' if day else 'missing'))
    result.update(changes)
    return result


def test_coverage_preserves_repeats_zeros_and_all_visits_without_pooling():
    rows=[row(value=0,day='2026-03-01'),row(value=3,day='2026-01-01',visit='relapse'),
          row('missing',value=None),row('undated',day=None),
          row(value=4,receipt='received_early',specimen='CSF'),
          row(value=99,receipt='unassessed'),row(value=99,control=True),
          row(value=99,cohort='retrospective'),row(value=99,specimen='bone marrow')]
    before=deepcopy(rows)
    coverage={entry['specimen']:entry for entry in calendar_coverage(rows,D)}
    assert coverage['plasma']['received_samples']==4
    assert coverage['plasma']['numeric_volume_samples']==3
    assert coverage['plasma']['unavailable_volume_samples']==1
    assert coverage['plasma']['numeric_volume_without_date']==1
    assert coverage['plasma']['plotted_samples']==2
    assert coverage['plasma']['plotted_participants']==1
    assert coverage['CSF']['plotted_samples']==1
    assert set(calendar_groups(rows,D))=={('circall','plasma'),('circall','CSF')}
    assert rows==before


def test_exact_calendar_positions_linear_volume_and_no_trajectory():
    rows=[row(value=0,day='2026-03-01'),row(value=3,day='2026-01-01',visit='tp1'),
          row('missing',value=None),row('undated',day=None)]
    before=deepcopy(rows)
    fig=calendar_figure(rows,calendar_coverage(rows,D)[0])
    ax=fig.axes[0]
    points=list(ax.collections[0].get_offsets())
    assert [float(p[0]) for p in points]==list(date2num([date(2026,1,1),date(2026,3,1)]))
    assert [float(p[1]) for p in points]==[3,0]
    assert ax.get_yscale()=='linear'
    assert ax.get_xlabel()=='Calendar collection date'
    assert ax.get_ylabel()=='Available plasma volume (mL)'
    assert not ax.lines and not ax.get_title()
    assert rows==before
    plt.close(fig)


def test_no_usable_dates_has_explicit_placeholder():
    rows=[row(day=None)]
    fig=calendar_figure(rows,calendar_coverage(rows,D)[0])
    assert not fig.axes[0].collections
    assert any('No dated' in text.get_text() for text in fig.axes[0].texts)
    plt.close(fig)


def test_prepare_retains_actual_date_and_never_uses_sampling_plan(tmp_path):
    source=tmp_path/'synthetic.xlsx'
    fixture(source,controls=False)
    book=load_workbook(source)
    sheet=book['cohorte_lal']
    headers=[c.value for c in sheet[1]]
    column=headers.index('sampling_date')+1 if 'sampling_date' in headers else len(headers)+1
    sheet.cell(1,column,'sampling_date')
    sheet.cell(2,column,datetime(2026,2,3,14,30))
    sheet.cell(3,column).value=None
    book.save(source)
    book.close()
    rows,issues,_=prepare(source,'circall',False,assessment(ASOF),D)
    assert not issues
    assert rows[0]['collection_date']==dict(value='2026-02-03',state='recorded_date')
    assert rows[1]['collection_date']['value'] is None
    validate_calendar_dates(rows,D,source)
    rows[0]['collection_date']['value']='2026-02-04'
    with pytest.raises(ValueError,match='reconcile'):
        validate_calendar_dates(rows,D,source)


@pytest.mark.parametrize('pooled,controls',[(False,False),(True,False),(False,True)])
def test_only_requested_circall_patient_scope_exports_calendar_plots(tmp_path,pooled,controls):
    from analysis.sample_statistics.step_04_report import figures
    rows=[row(control=controls),row(specimen='CSF',control=controls)]
    selected={**D,'metrics':{FIELD:D['metrics'][FIELD]}}
    paths=figures(tmp_path,rows,selected,pooled=pooled,controls=controls,pdf_output=False)
    calendar=[path for path in paths if path.stem.endswith('_by_collection_date')]
    assert len(calendar)==(2 if not pooled and not controls else 0)
    assert not list(tmp_path.rglob('*.pdf'))
    assert all(path.is_file() for path in calendar)



def test_exclusions_stay_below_center_legend_after_repeated_exports(tmp_path):
    from analysis.utils.plot_style import save_figure
    rows=[row(value=2,center='TRS'),row(value=3,center='RDB'),row(day=None)]
    fig=calendar_figure(rows,calendar_coverage(rows,D)[0])
    legend=fig.legends[0]
    assert 'Excluded:' not in legend.get_title().get_text()
    footer=fig._legend_footers[legend]
    before=[collection.get_offsets().copy() for collection in fig.axes[0].collections]
    for suffix in ('png','pdf','png'):
        save_figure(fig,tmp_path/f'calendar.{suffix}')
        renderer=fig.canvas.get_renderer()
        assert footer.get_visible()
        assert footer.get_window_extent(renderer).y1 < legend.get_window_extent(renderer).y0
        assert footer.get_text()=='Excluded: volume unavailable=0; numeric volume without collection date=1'
        for collection,expected in zip(fig.axes[0].collections,before,strict=True):
            import numpy as np
            np.testing.assert_array_equal(collection.get_offsets(),expected)
    plt.close(fig)
