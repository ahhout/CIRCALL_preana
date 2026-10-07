"""Pooled analyses using the approved common timepoints and source eligibility rules."""
import pandas as pd

from analysis.sample_analysis import analyses
from analysis.sample_analysis import reporting
from analysis.sample_analysis.policies import PRIMARY, TIMEPOINTS, correlation_pairs, eligible, pooled_controls

DEFAULT_TIMEPOINTS = [tp for tp in TIMEPOINTS['retrospective'] if tp in TIMEPOINTS['circall']]


def run(frame, output, tasks, timepoints, *, diagnosis_as_d1=True,
        followups=('tp1', 'tp2'), descriptive_visits=('circall:tp2',)):
    if not timepoints or len(set(timepoints)) != len(timepoints):
        raise ValueError('Pooled timepoints must be nonempty and unique')
    if not set(timepoints).issubset(DEFAULT_TIMEPOINTS):
        raise ValueError(f'Pooled timepoints must be shared canonical labels: {DEFAULT_TIMEPOINTS}')
    tables, events, audit_tables = {}, [], []
    cohorts = ('retrospective', 'circall')
    if not all(frame.cohort.eq(c).any() for c in cohorts):
        return [dict(analysis='pooled', cohort='combined', status='unavailable', reason='both cohorts required')]

    def select(question):
        selected = []
        for cohort in cohorts:
            data, audit = eligible(frame, cohort, question)
            in_scope = data.timepoint.isin(timepoints) & data.compartment.eq('plasma')
            selected.append(data.loc[in_scope].copy())
            audit['pool_eligible'] = audit.eligible & audit.timepoint.isin(timepoints) & audit.compartment.eq('plasma')
            audit_tables.append(audit)
        data = pd.concat(selected, ignore_index=True)
        tables[f'{question}_contributions'] = data.groupby(['cohort', 'timepoint']).agg(
            observations=('record_id', 'size'), patients=('patient_key', 'nunique')).reset_index()
        print(f'{question}: {len(data)} pooled plasma records, {data.patient_key.nunique()} patients; timepoints={timepoints}')
        return data

    for question, metrics in [('volumes', ['volume_ml']), ('yield', analyses.YIELD_METRICS[:3])]:
        if question in tasks:
            data = select(question)
            data['cohort'] = 'combined'
            tables[question] = analyses.measurement_summary(data, metrics)
    if 'yield' in tasks:
        data = select('correlations')
        pairs = [p for p in correlation_pairs('retrospective') if p in correlation_pairs('circall')]
        tables['correlations'] = analyses.correlation_table(data, 'combined', pairs, timepoints)
    if 'longitudinal' in tasks:
        data = select('longitudinal')
        data = data.loc[~(data.cohort + ':' + data.timepoint).isin(descriptive_visits)]
        controls = pooled_controls(frame)
        controls = controls.loc[controls[PRIMARY].gt(0)]
        print(f'Controls included once: {len(controls)} records')
        longitudinal, notes = analyses.longitudinal_tables(data, controls, 'combined', timepoints,
            output, diagnosis_as_d1=diagnosis_as_d1, followups=followups, descriptive_visits=descriptive_visits)
        tables.update(longitudinal)
        events.extend(notes)
    tables['methods'] = pd.DataFrame([
        {'setting': 'cohorts', 'value': 'retrospective + circall; pooling authorized by user'},
        {'setting': 'timepoints', 'value': ', '.join(timepoints)},
        {'setting': 'scope', 'value': 'Plasma; shared timepoints only, including Overall summaries and correlations'},
        {'setting': 'model', 'value': 'Categorical timepoint, patient random intercept; no cohort covariate'},
        {'setting': 'identity', 'value': 'Investigator confirms no patient overlap between cohorts. Existing source-qualified patient keys retained; controls included once'},
        {'setting': 'control_populations', 'value': 'CIRCALL controls are pediatric; cfDNA_donors.xlsx controls are adult. Both sources are pooled without age adjustment.'},
        {'setting': 'tests', 'value': 'Planned diagnosis-to-follow-up mixed-model contrasts only; BH within the pooled family. Optional cohort sensitivity models are not pooled.'},
        {'setting': 'correlations', 'value': 'Descriptive Pearson/Spearman coefficients only; no correlation p-values'},
        {'setting': 'exclusions', 'value': 'Existing cohort eligibility retained. Elution, blood pellet assays, inventory missingness and MRD are not pooled because availability or definitions differ'},
    ])
    for name, table in tables.items():
        reporting.table(output / f'{name}.csv', table)
    if audit_tables:
        reporting.table(output / 'eligibility.csv', pd.concat(audit_tables, ignore_index=True))
    events.append(dict(analysis='pooled', cohort='combined', status='complete', reason='Shared plasma analyses recalculated from pooled observations; see methods'))
    return events
