"""Recorded study rules and legacy question-specific analysis settings."""
import numpy as np

PRIMARY = 'dna_ng_per_mL_plasma'
TIMEPOINTS = {
    'retrospective': ['diag', 'tp0,5', 'tp1', 'tp2'],
    'circall': ['diag', 'd4', 'd8', 'd15', 'tp1', 'tp2'],
}
CORRELATION_TIMEPOINTS = {
    'retrospective': ['diag', 'tp0,5', 'tp1', 'tp2', 'tp1,5', 'tp3'],
    'circall': TIMEPOINTS['circall'],
}
PAIRS = [
    ('volume_ml', 'dna_concentration_ng_per_uL'),
    ('elution_volume_uL', 'dna_concentration_ng_per_uL'),
    ('elution_volume_uL', PRIMARY),
    ('volume_ml', 'dna_total_ng'),
    ('elution_volume_uL', 'dna_total_ng'),
]
SETTINGS = {
    'primary_endpoint': 'unadjusted dna_total_ng / volume_ml',
    'timepoints': TIMEPOINTS, 'correlation_timepoints': CORRELATION_TIMEPOINTS,
    'correlation_pairs': PAIRS, 'correlation_min_overall': 3, 'correlation_min_timepoint': 5,
    'correlation_transforms': {'dna_total_ng': 'log10(1+x)', 'concentration': 'log10(x)', 'x': 'raw'},
    'longitudinal_transform': 'log10(x), positive values only',
    'descriptive_violin_transform': 'log10(1+x), nonnegative values',
    'multiple_testing': 'BH within each cohort and test family',
    'mixed_model': '0 + C(timepoint), patient random intercept, ML',
    'pairwise_checks': ['sample-level Welch', 'patient-median Welch', 'patient-median Mann-Whitney'],
    'sensitivity': 'disabled unless requested; legacy numeric TP scale for retrospective only',
    'mrd_negative_tokens': ['na', 'negative', 'neg', 'n/a'],
    'cohort_rules': {
        'retrospective': 'cfDNA extraction, plasma, parsed timepoint; sample ID optional for longitudinal, required for dosage/correlations; post-inotuzumab excluded from correlations',
        'circall': 'plasma, present sample ID and timepoint for dosage/correlations/longitudinal',
    },
}


def eligible(frame, cohort, question):
    data = frame.loc[frame.cohort.eq(cohort)].copy()
    reason = data.record_id.map(lambda _: '')
    def exclude(mask, label):
        reason.loc[mask & reason.eq('')] = label
    exclude(data.qc_hold, 'qc_hold')
    if question not in ('volumes', 'inventory'):
        exclude(~data.compartment.eq('plasma'), 'not_plasma')
        if cohort == 'retrospective':
            exclude(~data.extraction_type.str.contains('cfdna', case=False, na=False), 'not_cfDNA_extraction')
        exclude(data.timepoint.isna(), 'unmapped_timepoint')
        if cohort == 'circall' or question in ('yield', 'correlations'):
            exclude(~data.sample_state.eq('present'), 'sample_id_required')
        if cohort == 'retrospective' and question == 'correlations':
            exclude(data.timepoint.eq('après inotuzumab'), 'post_inotuzumab_excluded')
        if question == 'longitudinal':
            exclude(~data.timepoint.isin(TIMEPOINTS[cohort]), 'outside_model_timepoints')
            exclude(data.patient_key.isna(), 'patient_key_required')
            exclude(~np.isfinite(data[PRIMARY]) | ~data[PRIMARY].gt(0), 'missing_or_nonpositive_endpoint')
    audit = data[['record_id', 'cohort', 'source_row', 'sample_id', 'compartment', 'timepoint']].copy()
    audit['analysis'] = question
    audit['exclusion_reason'] = reason
    audit['eligible'] = reason.eq('')
    return data.loc[reason.eq('')].copy(), audit


def pooled_controls(frame):
    return frame.loc[frame.is_control & frame.compartment.eq('plasma') & ~frame.qc_hold
                     & frame.sample_state.eq('present') & frame.patient_key.notna()
                     & np.isfinite(frame[PRIMARY])].copy()
