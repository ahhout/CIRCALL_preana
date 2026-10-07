"""Diagnosis-only associations, with separate cohort preparation and explicit coverage."""
from dataclasses import asdict, replace
from pathlib import Path
import json

import numpy as np
import pandas as pd

from analysis.sample_analysis.preparation import read_sheet, subject_key, text, numeric
from . import analyze_blast_cfdna as engine

# Explicit diagnostic fields; CIRCALL percentages are Excel fractions formatted as %.
CIRCALL_FIELDS = {
    'genetic_subtype': 'genetic_subtype',
    'peripheral_blast_percent': 'diag_blood_blast_pct',
    'tumor_fraction_percent': 'diag_bm_blast_pct',
    'gb_per_l': 'diag_blood_wbc_x10*9/L',
}
DEFERRED = {
    'peripheral_blast_count': 'No absolute peripheral blast count in the selected diagnosis inventory; not derived',
    'marrow_blast_count': 'No absolute marrow blast count in the selected diagnosis inventory; not derived',
}
UNITS = {
    'sex': 'recorded category', 'age_diag': 'years', 'genetic_subtype': 'recorded category',
    'peripheral_blast_percent': 'percentage points', 'tumor_fraction_percent': 'percentage points',
}


def prepare_circall(path):
    required = {'circall_id', 'timepoint', 'compartment', 'sample_id', 'cfDNA_ng_per_mL_plasma'}
    _, rows, headers = read_sheet(path, 'cohorte_lal', required)
    grouped = {}
    counts = dict(input_rows=len(rows), diagnosis_rows=0, plasma_candidate_rows=0,
                  missing_or_nonpositive_cfdna_rows=0, rows_missing_patient_key=0)
    for row in rows:
        if text(row.value('timepoint')).casefold() != 'diag':
            continue
        counts['diagnosis_rows'] += 1
        key = subject_key('circall', row.value('circall_id'))
        if key is None:
            counts['rows_missing_patient_key'] += 1
            continue
        patient = grouped.setdefault(key, {'cfdna': [], 'samples': set(), 'metadata': {k:set() for k in CIRCALL_FIELDS}})
        for variable, column in CIRCALL_FIELDS.items():
            value = text(row.value(column)) if variable == 'genetic_subtype' else numeric(row.value(column))
            if value is None or (isinstance(value,str) and value.casefold() in ('','na','n/a','none','nan')):
                continue
            if variable.endswith('_percent'):
                if not 0 <= value <= 1:
                    raise ValueError('CIRCALL diagnostic blast fields must be fractions in [0, 1]')
                value *= 100
            elif variable == 'gb_per_l' and value < 0:
                raise ValueError('CIRCALL diagnostic WBC counts must be nonnegative')
            patient['metadata'][variable].add(value)
        if text(row.value('compartment')).casefold() != 'plasma':
            continue
        sample = text(row.value('sample_id'))
        if sample.casefold() in ('','na','n/a','none','nan'):
            continue
        counts['plasma_candidate_rows'] += 1
        value = numeric(row.value('cfDNA_ng_per_mL_plasma'))
        if value is None or value <= 0:
            counts['missing_or_nonpositive_cfdna_rows'] += 1
            continue
        patient['cfdna'].append(value)
        patient['samples'].add(sample)
    records = []
    for patient in grouped.values():
        if not patient['cfdna']:
            continue
        if any(len(values)>1 for values in patient['metadata'].values()):
            raise ValueError('Conflicting CIRCALL diagnosis metadata for a patient; no value selected')
        record = {p.variable:np.nan for p in engine.PREDICTORS}
        record.update({variable:next(iter(values)) if values else np.nan for variable,values in patient['metadata'].items()})
        record.update(cfdna_ng_per_ml=float(np.median(patient['cfdna'])),
                      blood_sample_ids=';'.join(sorted(patient['samples'])),marrow_sample_ids='',cohort='circall')
        records.append(record)
    columns=['observation','cohort','blood_sample_ids','marrow_sample_ids','cfdna_ng_per_ml',*[p.variable for p in engine.PREDICTORS]]
    frame=pd.DataFrame(records)
    if frame.empty:
        frame=pd.DataFrame(columns=columns)
    else:
        frame.insert(0,'observation',np.arange(1,len(frame)+1))
    counts['analysis_patients']=len(frame)
    counts['patients_with_diagnosis_rows']=len(grouped)
    return frame, counts


def complete_count(frame, variable):
    return int((frame.cfdna_ng_per_ml.gt(0) & frame[variable].notna()).sum())


def coverage(cohorts, *, retrospective_wbc_unit='unknown'):
    rows=[]
    for name, frame in cohorts.items():
        for predictor in engine.PREDICTORS:
            n=complete_count(frame,predictor.variable)
            unit=UNITS.get(predictor.variable, 'x10^9/L' if name=='circall' else 'unconfirmed source unit')
            if predictor.variable == 'gb_per_l' and name == 'retrospective' and retrospective_wbc_unit == 'x10^9/L':
                unit = 'x10^9/L'
            reason='' if n else 'No usable diagnosis cfDNA/predictor pairs in the selected source'
            if name=='circall' and predictor.variable in ('sex','age_diag'):
                reason='Field not present in the selected CIRCALL inventory; skipped'
            rows.append(dict(cohort=name,predictor=predictor.variable,label=predictor.label,n=n,
                             status='available' if n else 'skipped',unit=unit,reason=reason))
        for variable,reason in DEFERRED.items():
            rows.append(dict(cohort=name,predictor=variable,label=variable,n=0,status='skipped',unit='',reason=reason))
    result = pd.DataFrame(rows)
    result['predictor_tissue'] = result.predictor.map(engine.PREDICTOR_TISSUES).fillna('Not tissue-specific')
    result['cfdna_specimen'] = 'Blood plasma'
    return result


def write(output, retrospective, counts, circall_path, *, predictors, pool=True, spearman_enabled=True, retrospective_wbc_unit='unknown'):
    output=Path(output);output.mkdir(parents=True,exist_ok=True)
    retrospective=retrospective.copy();retrospective['cohort']='retrospective'
    circall,circall_counts=prepare_circall(circall_path)
    cohorts={'retrospective':retrospective,'circall':circall}
    available=coverage(cohorts, retrospective_wbc_unit=retrospective_wbc_unit)
    def labelled(predictor, scope):
        if predictor.variable == 'gb_per_l':
            unit = '×10⁹/L' if scope == 'circall' or retrospective_wbc_unit == 'x10^9/L' else 'source units'
            return replace(predictor, label=f'Peripheral blood WBC count ({unit})')
        return predictor
    scopes=[]
    selected=engine.select_predictors(predictors)
    for name,frame in cohorts.items():
        views=tuple(labelled(p, name) for p in engine.PREDICTORS if complete_count(frame,p.variable)>0)
        tested=selected
        engine.write_outputs(output/name,frame,counts if name=='retrospective' else circall_counts,
                             predictors=predictors,view_predictors=views,spearman_enabled=spearman_enabled)
        scopes.append(dict(name=name,relative_dir=name,predictors=[asdict(p) for p in tested],
            descriptive_predictors=[asdict(p) for p in views if p.variable not in predictors]))
    if pool:
        pooled_rows=[];views=[]
        for predictor in engine.PREDICTORS:
            entries=available.loc[available.predictor.eq(predictor.variable)]
            usable=entries.status.eq('available').all() and entries.unit.nunique()==1
            reason='' if usable else 'Unavailable in one cohort or units not confirmed comparable'
            n=sum(complete_count(f,predictor.variable) for f in cohorts.values()) if usable else 0
            pooled_rows.append(dict(cohort='pooled',predictor=predictor.variable,label=predictor.label,
                n=n,status='available' if usable else 'skipped',unit=entries.unit.iat[0] if usable else '',reason=reason))
            if usable:views.append(labelled(predictor, 'pooled'))
        for variable,reason in DEFERRED.items():
            pooled_rows.append(dict(cohort='pooled',predictor=variable,label=variable,n=0,status='skipped',unit='',reason=reason))
        pooled=pd.concat(list(cohorts.values()),ignore_index=True)
        pooled['observation']=np.arange(1,len(pooled)+1)
        engine.write_outputs(output/'pooled',pooled,{name+'_patients':len(f) for name,f in cohorts.items()},
                             descriptive_only=True,view_predictors=views)
        scopes.append(dict(name='pooled',relative_dir='pooled',predictors=[],descriptive_predictors=[asdict(p) for p in views]))
        available=pd.concat([available,pd.DataFrame(pooled_rows)],ignore_index=True)
    available['predictor_tissue'] = available.predictor.map(engine.PREDICTOR_TISSUES).fillna('Not tissue-specific')
    available['cfdna_specimen'] = 'Blood plasma'
    available['label'] = available['label'].replace({
        'peripheral_blast_count': 'Peripheral blood absolute blast count',
        'marrow_blast_count': 'Bone marrow absolute blast count'})
    available.to_csv(output/'diagnosis_availability.csv',index=False)
    settings=dict(spearman_sensitivity=spearman_enabled, spearman_scope='Selected peripheral-blast tests within cohorts only; two-sided asymptotic p-value, unadjusted sensitivity', question='Diagnosis cfDNA versus diagnosis metadata',phase='diag',
        cfdna_endpoint='Recorded cfDNA_ng_per_mL_plasma, positive ng/mL; log10 for plots/regressions',
        retrospective_metadata='Only treatment_phase=diag; preserve established tissue-specific matching and patient medians',
        circall_metadata='Only timepoint=diag; explicit diagnostic fields; plasma cfDNA patient medians; metadata conflicts fail',
        circall_field_mapping=CIRCALL_FIELDS,circall_blast_source_unit='fraction formatted as percent',
        patient_linkage='Within-cohort only; cohorts concatenated without cross-cohort identity linkage',
        pooled='Descriptive only, cohort-colored points, both cohorts required per predictor and common confirmed units; no pooled p-values',
        retrospective_wbc_unit=retrospective_wbc_unit,
        missing_fields='Listed as skipped; no derived absolute counts or borrowed follow-up measurements',
        longitudinal='Separate workflow: MRD and yield over time are not used as diagnosis metadata')
    (output/'diagnosis_settings.json').write_text(json.dumps(settings,indent=2)+'\n')
    return scopes, available.to_dict(orient='records'), circall_counts
