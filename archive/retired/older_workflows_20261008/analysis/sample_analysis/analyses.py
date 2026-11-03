"""Shared cohort analyses operating on the prepared inventory, never on Excel."""
from itertools import combinations
import math

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from analysis.sample_analysis import statistics
from analysis.sample_analysis.policies import CORRELATION_MINIMUM, CORRELATION_TIMEPOINTS, PAIRS, PRIMARY, TIMEPOINTS, correlation_pairs, eligible, pooled_controls

VOLUME_METRICS = ['volume_ml', 'elution_volume_uL']
PELLET_COUNT_METRICS = []
YIELD_METRICS = ['dna_concentration_ng_per_uL', 'dna_total_ng', PRIMARY,
                 'mnc_vario_ng_per_uL', 'mnc_vario_total_ng', 'mnc_albumin_ng_per_uL']


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
                         not_received_records=missing if cohort == 'circall' else None,
                         timepoint_not_yet_reached_records=blank if cohort == 'circall' else None,
                         assessed_records=assessed if cohort == 'circall' else None,
                         missing_rate=missing / assessed if cohort == 'circall' and assessed else None,
                         missingness_policy='na = not received; blank = timepoint not yet reached; rate = not received / (present + not received), excluding future timepoints' if cohort == 'circall' else 'collection denominator not established'))
    return pd.DataFrame(rows)


def missing_samples_list(frame):
    """List explicitly missing CIRCALL collections, combining blood fractions."""
    columns = ['circall_id', 'timepoint', 'compartment']
    data = frame.loc[frame.cohort.eq('circall') & ~frame.is_control
                     & frame.patient_id.notna() & frame.patient_id.ne('')
                     & frame.timepoint.notna() & frame.timepoint.ne('')
                     & frame.compartment.notna()
                     & ~frame.compartment.isin(['', 'unknown']),
                     ['patient_id', 'timepoint', 'compartment', 'sample_state']].copy()
    data = data.rename(columns={'patient_id': 'circall_id'})
    data['compartment'] = data.compartment.replace(
        {'plasma': 'peripheral blood', 'blood pellet': 'peripheral blood'})
    states = data.groupby(columns, sort=True).sample_state.agg(set)
    missing = states.map(lambda values: 'explicit_missing' in values and 'present' not in values)
    result = states.loc[missing].reset_index()[columns]
    print(f'CIRCALL missing collections: {len(result)}; plasma and blood pellet count as '
          'peripheral blood; any present fraction takes precedence; blank IDs excluded')
    return result


def missing_samples_by_hospital(frame):
    """Restore the two compact CIRCALL bilan tables from canonical sample states."""
    data = frame.loc[frame.cohort.eq('circall') & ~frame.is_control & frame.patient_key.notna()].copy()
    # All identified patients enter the patient denominator, including scheduled visits.
    recorded = data.loc[data.timepoint.notna() & data.timepoint.ne('')
                        & data.compartment.notna() & ~data.compartment.isin(['', 'unknown'])]
    timepoints = [('diag','Diagnosis'),('d4','J4'),('d8','J8'),('d15','J15'),('tp1','TP1'),('tp2','TP2')]
    compartments = [('plasma','Plasma'),('blood pellet','Blood pellet'),('bone marrow','Bone marrow'),('CSF','CSF')]

    def rate(missing, assessed):
        return f'{missing}/{assessed} ({100 * missing / assessed if assessed else 0:.1f}%)'

    def sample_rate(group):
        missing = int(group.sample_state.eq('explicit_missing').sum())
        assessed = missing + int(group.sample_state.eq('present').sum())
        return rate(missing, assessed)

    by_timepoint, by_compartment = [], []
    for hospital in ('RDB','TRS','Overall'):
        sites = ['RDB','TRS'] if hospital == 'Overall' else [hospital]
        group = recorded.loc[recorded.hospital.isin(sites)]
        affected = group.loc[group.sample_state.eq('explicit_missing'), 'patient_key'].nunique()
        patients = data.loc[data.hospital.isin(sites), 'patient_key'].nunique()
        by_timepoint.append(dict(hospital=hospital, affected_patients=rate(affected, patients),
            all_assessed_samples=sample_rate(group),
            **{label: sample_rate(group.loc[group.timepoint.eq(tp)]) for tp,label in timepoints}))
        selected = group.loc[group.compartment.isin([c for c,_ in compartments])]
        by_compartment.append(dict(hospital=hospital, all_assessed_samples=sample_rate(selected),
            **{label: sample_rate(group.loc[group.compartment.eq(compartment)]) for compartment,label in compartments}))
    return {'missing_samples_by_hospital_timepoint': pd.DataFrame(by_timepoint),
            'missing_samples_by_hospital_compartment': pd.DataFrame(by_compartment)}


def measurement_summary(frame, metrics):
    rows = []
    data = frame.copy(); data['timepoint'] = data.timepoint.fillna('unmapped')
    grouped = [(keys, group) for keys, group in data.groupby(['cohort', 'compartment', 'timepoint'], dropna=False, sort=True)]
    grouped += [((cohort, compartment, 'Overall'), group) for (cohort, compartment), group in data.groupby(['cohort','compartment'], dropna=False, sort=True)]
    for keys, group in grouped:
        for metric in metrics:
            if not metric_allowed(keys[0], keys[1], metric):
                continue
            valid = group.loc[np.isfinite(group[metric])]
            values = valid[metric]
            rows.append(dict(cohort=keys[0], compartment=keys[1], timepoint=keys[2], measurement=metric.replace("mnc_", "blood_pellet_"),
                             inventory_records=len(group), measured_records=len(values),
                             measured_samples=valid.sample_key.nunique(), measured_patients=valid.patient_key.nunique(),
                             unavailable_records=len(group)-len(values),
                             total=values.sum() if len(values) else np.nan,
                             mean=values.mean(), standard_deviation=values.std(ddof=1),
                             q1=values.quantile(.25), median=values.median(), q3=values.quantile(.75),
                             minimum=values.min(), maximum=values.max(),
                             status='complete' if len(values) else 'unavailable'))
    return pd.DataFrame(rows)


def metric_allowed(cohort, compartment, metric):
    if metric == 'blood_volume_ml':
        return False
    if metric == 'elution_volume_uL' and cohort == 'retrospective':
        return False
    if metric == 'volume_ml' and compartment in ('blood', 'blood pellet', 'cell pellet'):
        return False
    return True


def blood_pellet_summary(frame, cohorts):
    pellet = frame.loc[frame.cohort.isin(cohorts) & frame.compartment.eq('blood pellet') & ~frame.qc_hold]
    tables = []
    for cohort in cohorts:
        data = pellet.loc[pellet.cohort.eq(cohort)]
        metrics = (PELLET_COUNT_METRICS + YIELD_METRICS[3:]) if cohort == 'retrospective' else YIELD_METRICS[:2]
        if not data.empty:
            tables.append(measurement_summary(data, metrics))
    return pd.concat(tables, ignore_index=True) if tables else pd.DataFrame()


def csf_volumes_by_site(frame):
    """Descriptive CIRCALL CSF volumes, retaining unknown site and missing-volume counts."""
    data = frame.loc[frame.cohort.eq('circall') & frame.compartment.eq('CSF') & ~frame.qc_hold].copy()
    rows = []
    for site, group in data.groupby('hospital', dropna=False, sort=True):
        measured = group.loc[np.isfinite(group.volume_ml)]
        rows.append(dict(cohort='circall', hospital=site,
            inventory_records=len(group), measured_records=len(measured),
            measured_patients=measured.patient_key.nunique(), unavailable_records=len(group)-len(measured),
            mean_volume_ml=measured.volume_ml.mean(), median_volume_ml=measured.volume_ml.median(),
            standard_deviation_ml=measured.volume_ml.std(ddof=1),
            q1_volume_ml=measured.volume_ml.quantile(.25), q3_volume_ml=measured.volume_ml.quantile(.75)))
    return pd.DataFrame(rows, columns=['cohort','hospital','inventory_records','measured_records',
        'measured_patients','unavailable_records','mean_volume_ml','median_volume_ml','standard_deviation_ml',
        'q1_volume_ml','q3_volume_ml'])


def transformed_y(metric, values):
    return np.log10(1 + np.asarray(values)) if metric == 'dna_total_ng' else np.log10(np.asarray(values))


def correlations(frame, cohort):
    data, audit = eligible(frame, cohort, 'correlations')
    return correlation_table(data, cohort, correlation_pairs(cohort), CORRELATION_TIMEPOINTS[cohort]), audit


def correlation_table(data, cohort, pairs, timepoints):
    rows, events = [], []
    for x, y in pairs:
        valid = data.loc[np.isfinite(data[x]) & np.isfinite(data[y])
                         & (data[y].ge(0) if y == 'dna_total_ng' else data[y].gt(0))]
        for tp in ['Overall', *timepoints]:
            group = valid if tp == 'Overall' else valid.loc[valid.timepoint.eq(tp)]
            minimum = CORRELATION_MINIMUM['Overall' if tp == 'Overall' else 'timepoint']
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
            rho = spearmanr(vx, vy).statistic
            rows.append(dict(**base, pearson_r=float(np.corrcoef(vx, vy)[0, 1]), spearman_rho=rho,
                             inference='descriptive only; repeated records and visit effects are not adjusted',
                             status='complete', reason=''))
    return pd.DataFrame(rows)


def cohort_comparison(frame):
    """Existing descriptive dosage comparison; matched labels are not calendar mappings."""
    groups={}
    for cohort in ('retrospective','circall'):
        data,_=eligible(frame,cohort,'yield')
        data=data.loc[np.isfinite(data[PRIMARY])]
        groups[cohort]={tp:values[PRIMARY] for tp,values in data.groupby('timepoint')}
    rows=[]
    labels=sorted(set(groups['retrospective'])|set(groups['circall']))
    for tp in labels:
        result={'timepoint':tp,'matching_basis':'timepoint label only'}
        means={}
        for cohort in ('retrospective','circall'):
            values=groups[cohort].get(tp,pd.Series(dtype=float))
            result[cohort+'_sample_count']=len(values)
            result[cohort+'_mean_ng_per_ml']=values.mean()
            result[cohort+'_median_ng_per_ml']=values.median()
            means[cohort]=values.mean()
        r,c=means['retrospective'],means['circall']
        both=np.isfinite(r) and np.isfinite(c)
        result['comparison_status']='matched labels' if both else 'retrospective only' if np.isfinite(r) else 'circall only'
        result['mean_difference_ng_per_ml']=c-r if both else np.nan
        result['mean_ratio_circall_to_retrospective']=c/r if both and r!=0 else np.nan
        result['mean_percent_difference']=(c/r-1)*100 if both and r!=0 else np.nan
        rows.append(result)
    return pd.DataFrame(rows)


def paired_counts(data, timepoints):
    patients = {tp: set(data.loc[data.timepoint.eq(tp), 'patient_key'].dropna()) for tp in timepoints}
    return pd.DataFrame([{'timepoint_a': a, 'timepoint_b': b, 'paired_patients': len(patients[a] & patients[b])}
                         for a, b in combinations(timepoints, 2)])


def longitudinal(frame, cohort, output, *, random_slope=False, outlier_drop_n=0, diagnosis_as_d1=False,
                 followups=('tp1', 'tp2'), descriptive_visits=('circall:tp2',)):
    """Fit one cohort with the pooled controls. Failures propagate to the runner."""
    patients, audit = eligible(frame, cohort, 'longitudinal')
    controls = pooled_controls(frame)
    controls = controls.loc[controls[PRIMARY].gt(0)]
    requested = TIMEPOINTS[cohort]
    tables, events = longitudinal_tables(patients, controls, cohort, requested, output,
        random_slope=random_slope, outlier_drop_n=outlier_drop_n, diagnosis_as_d1=diagnosis_as_d1,
        followups=followups, descriptive_visits=descriptive_visits)
    return tables, audit, events


def longitudinal_tables(patients, controls, cohort, requested, output, *, random_slope=False,
                        outlier_drop_n=0, diagnosis_as_d1=False, followups=('tp1', 'tp2'),
                        descriptive_visits=('circall:tp2',)):
    available = [tp for tp in requested if patients.timepoint.eq(tp).any()]
    events = [dict(analysis='longitudinal', cohort=cohort, status='unavailable',
                   reason=f'no eligible observations at {tp}') for tp in requested if tp not in available]
    tables = {'paired_counts': paired_counts(patients, available),
              'timepoint_counts': patients.groupby('timepoint').agg(n_observations=(PRIMARY, 'count'),
                                    n_patients=('patient_key', 'nunique')).reset_index()}
    tables['timepoint_counts'] = pd.concat([pd.DataFrame([dict(timepoint='Control',
        n_observations=len(controls), n_patients=controls.patient_key.nunique())]), tables['timepoint_counts']], ignore_index=True)
    model_times = [tp for tp in available if f'{cohort}:{tp}' not in descriptive_visits]
    model_patients = patients.loc[patients.timepoint.isin(model_times)]
    pairs = [('diag', tp) for tp in followups if 'diag' in model_times and tp in model_times]
    tables['planned_comparisons'] = pd.DataFrame([dict(timepoint_a='diag', timepoint_b=tp,
        status='planned' if ('diag', tp) in pairs else 'descriptive',
        reason='' if ('diag', tp) in pairs else 'visit unavailable or configured as descriptive')
        for tp in followups if tp in requested])
    # Mixed adult/pediatric controls are a descriptive reference, not a model group.
    model_controls = controls.iloc[:0]
    if not pairs or not model_patients.groupby('patient_key').timepoint.nunique().gt(1).any():
        events.append(dict(analysis='mixed_model', cohort=cohort, status='unavailable',
                           reason='no available planned comparison or no repeated patients'))
    else:
        mixed = statistics.compute_mixedlm_contrasts(df_patients=model_patients, donors=model_controls,
            timepoints=model_times, correction='bh', contrast_pairs=pairs, diagnostics_dir=output/'diagnostics/mixedlm')
        tables['model_diagnostics'] = pd.DataFrame([mixed.attrs['model_diagnostics']])
        if not np.isfinite(mixed[['delta_log10', 'se', 'p_adj']].to_numpy()).all() or mixed.se.le(0).any():
            raise RuntimeError('Mixed model produced invalid contrast uncertainty')
        if mixed.attrs['model_diagnostics']['status'] == 'review':
            events.append(dict(analysis='mixed_model', cohort=cohort, status='review',
                reason='Numerical warnings require review; see model_diagnostics'))
        mixed = mixed.merge(tables['paired_counts'], on=['timepoint_a','timepoint_b'], how='left')
        mixed['primary_family'] = True
        tables['mixed_contrasts'] = mixed
        # Keep the established primary-table name as an exact copy, not another test family.
        tables['primary_contrasts'] = mixed.copy()
        if outlier_drop_n:
            sensitivity = statistics.mixedlm_outlier_drop_sensitivity(df_patients=model_patients, donors=model_controls,
                timepoints=model_times, correction='bh', drop_n=outlier_drop_n)
            for name, table in sensitivity.items():
                tables[f'outlier_drop{outlier_drop_n}_{name}'] = table
        if random_slope:
            if cohort == 'circall':
                events.append(dict(analysis='random_slope',cohort=cohort,status='unavailable',reason='no agreed numeric mapping between CIRCALL day labels and TP labels'))
            else:
                tables['random_slope'] = statistics.mixedlm_random_slope_time_sensitivity(
                    df_patients=model_patients, timepoints=model_times, correction='bh', diagnostics_dir=output/'diagnostics/random_slope')
    for table in tables.values():
        table.insert(0, 'cohort', cohort)
    from analysis.sample_analysis.statistical_plots import write_test_plots
    write_test_plots(tables, patients, controls, output, cohort, diagnosis_as_d1=diagnosis_as_d1)
    return tables, events
