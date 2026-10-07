"""Recorded study rules and legacy question-specific analysis settings."""
import numpy as np

PRIMARY = 'dna_ng_per_mL_plasma'
CORRELATION_MINIMUM = {'Overall': 3, 'timepoint': 5}
CONTROL_POPULATIONS = {'existing_controls': 'adult', 'pediatric_controls': 'pediatric'}
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
def correlation_pairs(cohort):
    return [pair for pair in PAIRS if cohort != 'retrospective' or 'elution_volume_uL' not in pair]


SETTINGS = {
    'control_populations': CONTROL_POPULATIONS,
    'cohort_overlap': 'User confirmed that no patient can occur in both cohorts',
    'preanalytical_purpose': 'Assess whether sample-handling choices are associated with DNA recovery; not a mechanistic biological analysis',
    'inventory_output': 'tables only',
    'volume_output': 'tables only',
    'cohort_boxplots': 'side-by-side and pooled distributions; points colored by cohort; separate cohort models',
    'excluded_blood_pellet_outputs': ['DIN', 'tube count', 'aliquot count'],
    'blood_pellet_plot_axis': 'canonical timepoints; original linear measurement scale',
    'circall_sample_id_states': {'na': 'sample not received', 'blank': 'timepoint not yet reached (ongoing cohort)'},
    'circall_missingness_denominator': 'present IDs + na IDs; blank future timepoints excluded',
    'primary_endpoint': 'unadjusted dna_total_ng / volume_ml',
    'timepoints': TIMEPOINTS, 'correlation_timepoints': CORRELATION_TIMEPOINTS,
    'correlation_pairs': {c:correlation_pairs(c) for c in TIMEPOINTS},
    'excluded_analyses': ['blood volume', 'retrospective elution volume'],
    'compartment_plots': 'one compartment per figure; cohorts adjacent within a compartment',
    'blood_pellet_selection': 'compartment == blood pellet in both cohorts; assays kept separate', 'correlation_min_overall': CORRELATION_MINIMUM['Overall'], 'correlation_min_timepoint': CORRELATION_MINIMUM['timepoint'],
    'correlation_transforms': {'dna_total_ng': 'log10(1+x)', 'concentration': 'log10(x)', 'x': 'raw'},
    'longitudinal_transform': 'log10(x), positive values only',
    'descriptive_box_transform': 'log10(1+x), nonnegative values',
    'multiple_testing': {'longitudinal': 'BH within each cohort planned diagnosis-to-follow-up family',
                         'pooled_longitudinal': 'BH within each pooled test family',
                         'correlations': 'descriptive Pearson/Spearman coefficients only; no hypothesis tests'},
    'mixed_model': '0 + C(timepoint), patient random intercept, ML',
    'pairwise_checks': [],
    'control_inference': 'Controls remain descriptive; excluded from patient longitudinal models',
    'sensitivity': 'disabled unless requested; legacy numeric TP scale for retrospective only',
    'mrd_negative_tokens': ['negative', 'neg'],
    'mrd_missing_tokens': ['na', 'n/a', ''],
    'dna_plot_markers': 'circles for all observations; no MRD status encoding',
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
