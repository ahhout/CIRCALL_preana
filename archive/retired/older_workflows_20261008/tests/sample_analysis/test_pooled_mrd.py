"""Synthetic checks for pooled denominators, censoring, and privacy."""
from unittest.mock import patch

import matplotlib.pyplot as plt
import pandas as pd
import pytest

from analysis.sample_analysis import pooled_mrd as mrd
from analysis.cli import arguments
from analysis.pipeline import option_argv


def prepared():
    circall = pd.DataFrame([
        dict(cohort='circall', patient_key='same', timepoint='TP1 (D29)', status='quantified', measured_fraction=.001),
        dict(cohort='circall', patient_key='same', timepoint='TP2 (D71)', status='negative', measured_fraction=None)])
    retro = pd.DataFrame([
        dict(cohort='retrospective', patient_key='same', timepoint='TP1', status='positive_nonquantifiable', measured_fraction=None, reported_upper_bound_fraction=.0001),
        dict(cohort='retrospective', patient_key='other', timepoint='TP2', status='positive_nonquantifiable', measured_fraction=None, reported_upper_bound_fraction=None)])
    return circall, retro


def test_fixed_denominator_missing_and_cohort_identity():
    data = mrd.prepare(*prepared())
    assert len(data)==9
    summary=mrd.summary_table(data)
    pooled=summary.loc[summary.cohort.eq('pooled')]
    assert set(pooled.denominator)=={3}
    assert pooled.groupby('timepoint').percent.sum().tolist()==pytest.approx([100]*3)
    tp2=pooled.loc[pooled.timepoint.eq('TP2')].set_index('status')
    assert tp2.loc['negative','patients']==1
    assert tp2.loc['missing','patients']==1
    assert tp2.loc['positive_nonquantifiable','patients']==1
    assert data.loc[data.timepoint.eq('Diagnosis'),'measured_fraction'].isna().all()
    assert 'patient_key' not in summary


def test_bounds_not_connected_and_no_row_export(tmp_path):
    data=mrd.prepare(*prepared())
    with patch.object(mrd.reporting, 'save') as save:
        mrd.plot_trajectories(data, tmp_path/'unused.png', unknown_level=1e-6, negative_level=1e-8)
    fig=save.call_args.args[0]
    values = [float(c.get_offsets()[0, 1]) for c in fig.axes[0].collections]
    assert values.count(1e-6) == 2  # Both bounded and unbounded NQ are positioned.
    assert .0001 not in values
    assert len(values) == 7
    assert data.loc[data.status.eq('positive_nonquantifiable'), 'measured_fraction'].isna().all()
    assert data.reported_upper_bound_fraction.max() == .0001
    assert len(fig.axes[0].lines)==2  # Only the CIRCALL baseline/quantified/negative chain.
    assert [line.get_linestyle() for line in fig.axes[0].lines]==['-', ':']
    plt.close(fig)
    mrd.run(*prepared(), tmp_path, unknown_level=1e-6, negative_level=1e-8)
    assert {p.name for p in tmp_path.iterdir()}=={'pooled_mrd_summary.csv', 'pooled_mrd_settings.json',
        'pooled_mrd_trajectories.png', 'pooled_mrd_status_stacked.png'}
    assert 'patient_key' not in (tmp_path/'pooled_mrd_summary.csv').read_text()


def test_duplicate_prepared_visits_fail():
    circall, retro=prepared()
    with pytest.raises(ValueError, match='one prepared annotation'):
        mrd.prepare(pd.concat([circall, circall]), retro)


def test_explicit_pooling_option():
    assert arguments(['--circall', 'synthetic.xlsx', *option_argv({'pool-mrd': True})]).pool_mrd
    assert not arguments(['--circall', 'synthetic.xlsx']).pool_mrd
