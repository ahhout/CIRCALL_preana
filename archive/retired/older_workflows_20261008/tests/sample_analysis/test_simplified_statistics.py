"""Scientific output contracts for the approved reduced inference plan."""
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
from scipy.stats import norm
from statsmodels.stats.multitest import multipletests

from analysis.cli import arguments
from analysis.pipeline import option_argv
from analysis.sample_analysis import analyses, statistics
from analysis.sample_analysis.policies import PRIMARY, pooled_controls
from tests.fixtures.sample_analysis import fixture


def test_cli_defaults_and_explicit_configuration():
    args = arguments(['--workflow', 'canonical', '--circall', 'synthetic.xlsx'])
    assert not args.pool_cohorts
    assert args.longitudinal_followups == ['tp1', 'tp2']
    assert args.longitudinal_descriptive_visits == ['circall:tp2']
    override = option_argv({'longitudinal-followups': ['d4'], 'longitudinal-descriptive-visits': []})
    args = arguments(['--workflow', 'canonical', '--circall', 'synthetic.xlsx', *override])
    assert args.longitudinal_followups == ['d4'] and args.longitudinal_descriptive_visits == []


def test_descriptive_correlations_have_no_inferential_columns():
    table, _ = analyses.correlations(fixture(), 'circall')
    assert 'spearman_rho' in table
    assert 'pearson_r' in table
    assert not any('p_value' in name for name in table.columns)
    assert table.loc[table.status.eq('complete'), 'inference'].str.contains('descriptive only').all()


def test_sparse_visits_and_controls_retained_only_descriptively(tmp_path):
    frame = fixture()
    extra = frame.loc[frame.cohort.eq('circall') & frame.timepoint.eq('diag')].iloc[:3].copy()
    extra['timepoint'] = 'tp2'
    frame = pd.concat([frame, extra], ignore_index=True)
    patients, _ = analyses.eligible(frame, 'circall', 'longitudinal')
    captured = {}
    def fit(**kwargs):
        captured.update(kwargs)
        result = pd.DataFrame([dict(timepoint_a='diag', timepoint_b='tp1', delta_log10=-.2,
            se=.1, p_adj=.04)])
        result.attrs['model_diagnostics'] = dict(status='review', numerical_warnings='variance boundary')
        return result
    with patch.object(statistics, 'compute_mixedlm_contrasts', side_effect=fit), patch('analysis.sample_analysis.statistical_plots.write_test_plots'):
        tables, events = analyses.longitudinal_tables(patients, pooled_controls(frame), 'circall',
            ['diag','tp1','tp2'], tmp_path)
    assert captured['donors'].empty
    assert 'tp2' not in set(captured['df_patients'].timepoint)
    assert captured['contrast_pairs'] == [('diag','tp1')]
    assert tables['timepoint_counts'].set_index('timepoint').loc['tp2','n_patients'] == 3
    assert set(tables).isdisjoint({'welch_sample','welch_patient_median','mannwhitney_patient_median'})
    assert any(e['status']=='review' for e in events)
    pd.testing.assert_frame_equal(tables['mixed_contrasts'], tables['primary_contrasts'])


def test_patient_only_fit_corrects_only_planned_contrasts():
    rng = np.random.default_rng(13)
    rows = []
    for subject in range(35):
        intercept = rng.normal(1, .45)
        for visit, effect in [('diag',0),('tp0,5',-.1),('tp1',-.35),('tp2',-.5)]:
            rows.append(dict(patient_key=f'synthetic-{subject}', timepoint=visit,
                             dna_ng_per_mL_plasma=10**(intercept+effect+rng.normal(0,.3))))
    patients = pd.DataFrame(rows)
    empty = patients.iloc[:0]
    result = statistics.compute_mixedlm_contrasts(df_patients=patients, donors=empty,
        timepoints=['diag','tp0,5','tp1','tp2'], correction='bh', contrast_pairs=[('diag','tp1'),('diag','tp2')])
    assert list(zip(result.timepoint_a,result.timepoint_b)) == [('diag','tp1'),('diag','tp2')]
    np.testing.assert_allclose(result.p_value, 2*norm.sf(np.abs(result.delta_log10/result.se)))
    np.testing.assert_allclose(result.p_adj, multipletests(result.p_value,method='fdr_bh')[1])
    assert result.attrs['model_diagnostics']['n_patients'] == 35
    assert result.p_value.gt(0).all()
    np.testing.assert_allclose(result.fold_change, 10**result.delta_log10)


def test_converged_but_infinite_likelihood_uses_existing_optimizer_fallback():
    from types import SimpleNamespace
    from unittest.mock import Mock
    bad = SimpleNamespace(converged=True, llf=np.inf)
    good = SimpleNamespace(converged=True, llf=-12., fe_params=np.array([1.]), scale=.2,
        cov_params=lambda: np.array([[.1]]), fittedvalues=np.array([1.]), resid=np.array([.1]))
    model = Mock()
    model.fit.side_effect = [bad, good]
    result = statistics._fit_mixedlm(model)
    assert result is good
    assert result.audit_optimizer == 'powell'
    assert result.audit_attempts == ['lbfgs: rejected (ValueError)', 'powell: accepted']
    assert [call.kwargs['method'] for call in model.fit.call_args_list] == ['lbfgs','powell']
