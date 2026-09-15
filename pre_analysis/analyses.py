"""Shared cohort analyses operating on the prepared inventory, never on Excel."""
from itertools import combinations
import math

import numpy as np
import pandas as pd
from scipy.stats import pearsonr, spearmanr

from . import statistics
from .policies import CORRELATION_TIMEPOINTS, PAIRS, PRIMARY, TIMEPOINTS, eligible, pooled_controls

VOLUME_METRICS = ['volume_ml', 'blood_volume_ml', 'elution_volume_uL', 'mnc_tube_count_million', 'mnc_aliquot_count_million']
YIELD_METRICS = ['dna_concentration_ng_per_uL', 'dna_total_ng', PRIMARY,
                 'mnc_vario_ng_per_uL', 'mnc_vario_total_ng', 'mnc_albumin_ng_per_uL', 'mnc_DIN']


def availability(frame):
    rows = []
    patient_data = frame.loc[~frame.is_control].copy()
    patient_data['timepoint'] = patient_data.timepoint.fillna('unmapped')
    for keys, data in patient_data.groupby(['cohort', 'compartment', 'timepoint', 'hospital'], dropna=False, sort=True):
        cohort, compartment, timepoint, hospital = keys
        state = data.sample_state.value_counts()
        present, missing, blank = [int(state.get(s, 0)) for s in ('present', 'explicit_missing', 'blank')]
        assessed = present + missing
        rows.append(dict(cohort=cohort, compartment=compartment, timepoint=timepoint, hospital=hospital,
                         inventory_records=len(data), unique_patients=data.patient_key.nunique(),
                         unique_samples=data.sample_key.nunique(), present_records=present,
                         na_coded_records=missing, blank_id_records=blank,
                         assessed_records=assessed if cohort == 'circall' else None,
                         missing_rate=missing / assessed if cohort == 'circall' and assessed else None,
                         missingness_policy='explicit na / nonblank IDs' if cohort == 'circall' else 'collection denominator not established'))
    return pd.DataFrame(rows)


def measurement_summary(frame, metrics):
    rows = []
    data = frame.copy(); data['timepoint'] = data.timepoint.fillna('unmapped')
    for keys, group in data.groupby(['cohort', 'compartment', 'timepoint'], dropna=False, sort=True):
        for metric in metrics:
            valid = group.loc[np.isfinite(group[metric])]
            values = valid[metric]
            rows.append(dict(cohort=keys[0], compartment=keys[1], timepoint=keys[2], measurement=metric,
                             inventory_records=len(group), measured_records=len(values),
                             measured_samples=valid.sample_key.nunique(), measured_patients=valid.patient_key.nunique(),
                             unavailable_records=len(group)-len(values), mean=values.mean(), median=values.median(),
                             minimum=values.min(), maximum=values.max(),
                             status='complete' if len(values) else 'unavailable'))
    return pd.DataFrame(rows)


def transformed_y(metric, values):
    return np.log10(1 + np.asarray(values)) if metric == 'dna_total_ng' else np.log10(np.asarray(values))


def correlations(frame, cohort):
    data, audit = eligible(frame, cohort, 'correlations')
    rows, events = [], []
    for x, y in PAIRS:
        valid = data.loc[np.isfinite(data[x]) & np.isfinite(data[y])
                         & (data[y].ge(0) if y == 'dna_total_ng' else data[y].gt(0))]
        for tp in ['Overall', *CORRELATION_TIMEPOINTS[cohort]]:
            group = valid if tp == 'Overall' else valid.loc[valid.timepoint.eq(tp)]
            minimum = 3 if tp == 'Overall' else 5
            base = dict(cohort=cohort, timepoint=tp, variable_x=x, variable_y=y,
                        correlation_scale='X raw; Y log10(1+Y)' if y == 'dna_total_ng' else 'X raw; Y log10',
                        paired_sample_count=len(group), unique_patient_count=group.patient_key.nunique())
            if len(group) < minimum:
                rows.append(dict(**base, status='unavailable', reason=f'fewer than {minimum} paired observations'))
                continue
            vx, vy = group[x].to_numpy(), transformed_y(y, group[y])
            if np.ptp(vx) == 0 or np.ptp(vy) == 0:
                rows.append(dict(**base, status='unavailable', reason='constant input'))
                continue
            pearson, spearman = pearsonr(vx, vy), spearmanr(vx, vy)
            rows.append(dict(**base, pearson_r=pearson.statistic, pearson_p_value=pearson.pvalue,
                             spearman_rho=spearman.statistic, spearman_p_value=spearman.pvalue,
                             status='complete', reason=''))
    return pd.DataFrame(rows), audit


def paired_counts(data, timepoints):
    patients = {tp: set(data.loc[data.timepoint.eq(tp), 'patient_key'].dropna()) for tp in timepoints}
    return pd.DataFrame([{'timepoint_a': a, 'timepoint_b': b, 'paired_patients': len(patients[a] & patients[b])}
                         for a, b in combinations(timepoints, 2)])


def longitudinal(frame, cohort, output, *, random_slope=False, outlier_drop_n=0):
    """Fit one cohort with the pooled controls. Failures propagate to the runner."""
    patients, audit = eligible(frame, cohort, 'longitudinal')
    controls = pooled_controls(frame)
    controls = controls.loc[controls[PRIMARY].gt(0)]
    requested = TIMEPOINTS[cohort]
    available = [tp for tp in requested if patients.timepoint.eq(tp).any()]
    events = []
    for tp in requested:
        if tp not in available:
            events.append(dict(analysis='longitudinal', cohort=cohort, status='unavailable', reason=f'no eligible observations at {tp}'))
    if patients.empty or controls.empty:
        return {}, audit, events + [dict(analysis='longitudinal', cohort=cohort, status='unavailable', reason='patient or measured control data unavailable')]
    bins = ['Control', *available]
    tables = {}
    for unit, name in [('sample', 'welch_sample'), ('patient_median', 'welch_patient_median')]:
        tables[name] = statistics.compute_pairwise_bins(df_patients=patients, donors=controls, bins=bins,
                                                       unit=unit, scale='log10', correction='bh')
    tables['mannwhitney_patient_median'] = statistics.compute_mannwhitney_bins(
        df_patients=patients, donors=controls, bins=bins, unit='patient_median', scale='log10', correction='bh')
    tables['paired_counts'] = paired_counts(patients, available)
    tables['timepoint_counts'] = patients.groupby('timepoint').agg(n_observations=(PRIMARY, 'count'),
                                                                  n_patients=('patient_key', 'nunique')).reset_index()
    tables['timepoint_counts'] = pd.concat([pd.DataFrame([{'timepoint': 'Control', 'n_observations': len(controls),
                                                          'n_patients': controls.patient_key.nunique()}]), tables['timepoint_counts']], ignore_index=True)
    statistics.write_pairwise_log10_diagnostics(df_patients=patients, donors=controls, bins=bins, out_dir=output/'diagnostics/pairwise_log10')
    if not patients.groupby('patient_key').timepoint.nunique().gt(1).any():
        events.append(dict(analysis='mixed_model', cohort=cohort, status='unavailable', reason='no patients observed at multiple model timepoints'))
    else:
        tables['mixed_contrasts'] = statistics.compute_mixedlm_contrasts(
            df_patients=patients, donors=controls, timepoints=available, correction='bh', diagnostics_dir=output/'diagnostics/mixedlm')
        mixed = tables['mixed_contrasts']
        if not np.isfinite(mixed[['delta_log10', 'p_adj']].to_numpy()).all():
            raise RuntimeError('Mixed model produced nonfinite contrasts')
        mixed = mixed.merge(tables['paired_counts'], on=['timepoint_a','timepoint_b'], how='left')
        mixed['primary_family'] = [(a == 'Control' and b == 'diag') or (a == 'diag' and b in requested)
                                   for a,b in zip(mixed.timepoint_a,mixed.timepoint_b)]
        mixed['intermediate_tp_exploratory'] = mixed.timepoint_a.eq('tp0,5') | mixed.timepoint_b.eq('tp0,5')
        tables['mixed_contrasts'] = mixed
        tables['primary_contrasts'] = mixed.loc[mixed.primary_family].copy()
        if outlier_drop_n:
            sensitivity = statistics.mixedlm_outlier_drop_sensitivity(df_patients=patients, donors=controls,
                timepoints=available, correction='bh', drop_n=outlier_drop_n)
            for name, table in sensitivity.items():
                tables[f'outlier_drop{outlier_drop_n}_{name}'] = table
        if random_slope:
            if cohort == 'circall':
                events.append(dict(analysis='random_slope',cohort=cohort,status='unavailable',reason='no agreed numeric mapping between CIRCALL day labels and TP labels; no labels silently dropped'))
            else:
                tables['random_slope'] = statistics.mixedlm_random_slope_time_sensitivity(
                    df_patients=patients, timepoints=available, correction='bh', diagnostics_dir=output/'diagnostics/random_slope')
    for table in tables.values():
        table.insert(0, 'cohort', cohort)
    return tables, audit, events
