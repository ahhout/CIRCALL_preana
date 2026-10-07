"""Reuse the established association fits without legacy row-export paths."""
import math

import numpy as np
import pandas as pd
from statsmodels.stats.multitest import multipletests

from analysis import association_methods as engine


DEFERRED = {
    'peripheral_blast_count': 'No approved absolute peripheral blast source; not derived from WBC',
    'marrow_blast_count': 'No approved absolute marrow blast source',
    'hematocrit': 'No approved hematocrit source; Hb is hemoglobin',
}


def clean(value):
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [clean(v) for v in value]
    if isinstance(value, np.generic):
        value = value.item()
    if value is pd.NA or isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def pairs(frame, predictor):
    selected = frame.loc[frame.cfdna_ng_per_ml.gt(0)].copy()
    # Concatenating a genuinely empty cohort can leave numeric columns as object
    # dtype. Cast validated measurements explicitly, without coercing bad text.
    selected['cfdna_ng_per_ml'] = selected.cfdna_ng_per_ml.astype(float)
    if predictor.kind == 'continuous':
        selected[predictor.variable] = selected[predictor.variable].astype(float)
    return engine.prepare_analysis_data(selected, predictor)


def unit(variable, scope, args, definitions):
    if variable == 'gb_per_l' and scope in ('retrospective', 'pooled') and args.retrospective_wbc_unit != 'x10^9/L':
        return 'unconfirmed source unit'
    return definitions['units'][variable]


def analyze(frame, scope, args, definitions, *, status='complete', counts=None, blocking=None, cohorts=None):
    result = dict(scope=scope, status=status, summary=counts or {}, blocking=blocking or [],
                  tables={k: [] for k in ('Coverage', 'Associations', 'Descriptions', 'Diagnostics')})
    models, residuals = {}, []
    tested = set(args.predictors) if scope != 'pooled' else set()
    for p in engine.PREDICTORS:
        if status != 'complete':
            available = pd.DataFrame()
            data = pd.DataFrame()
        else:
            available = frame.loc[frame.cfdna_ng_per_ml.notna() & frame[p.variable].notna()]
            data = pairs(frame, p)
        reason = '' if len(data) else 'No complete positive cfDNA/predictor pairs'
        if scope == 'circall' and p.variable in ('sex', 'age_diag'):
            reason = 'Unavailable in CIRCALL; not derived'
        comparable = True
        if scope == 'pooled' and status == 'complete':
            comparable = all(len(pairs(f, p)) for f in cohorts.values()) and set(cohorts) == {'retrospective', 'circall'}
            if p.variable == 'gb_per_l' and args.retrospective_wbc_unit != 'x10^9/L':
                comparable = False
                reason = 'Retrospective WBC units not explicitly confirmed comparable'
            elif not comparable:
                reason = 'Both cohorts require complete positive pairs for this predictor'
        if status != 'complete':
            reason = 'Cohort blocked by integrity or preparation failure' if status == 'blocked' else 'Cohort execution failed'
        n = len(data)
        coverage = dict(cohort=scope, predictor=p.variable, label=p.label, unit=unit(p.variable, scope, args, definitions),
                        eligible_patients=len(frame) if status == 'complete' else 0, predictor_patients=int(frame[p.variable].notna().sum()) if status == 'complete' else 0,
                        raw_complete_pairs=len(available), available_positive_pairs=n, analysis_patients=n if comparable else 0, nonpositive_pairs=len(available)-n,
                        contributing_outcome_samples=int(data.outcome_sample_n.sum()) if n else 0,
                        contributing_predictor_records=int(data[p.variable+'_sample_n'].sum()) if n else 0,
                        status='available' if n and comparable else 'unavailable', reason=reason,
                        inference=('selected hypothesis' if status == 'complete' else 'selected hypothesis; not run') if p.variable in tested else 'descriptive only',
                        retrospective_analysis_patients=int((data.cohort == 'retrospective').sum()) if n else 0,
                        circall_analysis_patients=int((data.cohort == 'circall').sum()) if n else 0)
        result['tables']['Coverage'].append(coverage)
        if status != 'complete' or not comparable:
            if p.variable in tested:
                result['tables']['Associations'].append(dict(predictor=p.variable, status='skipped', reason=reason, n=0))
            continue
        groups = available.groupby(p.variable, sort=True) if p.kind == 'categorical' else [('Overall', available)]
        described = False
        for category, group in groups:
            values = group.cfdna_ng_per_ml
            desc = dict(predictor=p.variable, category=str(category), n=len(group),
                        outcome_samples=int(group.outcome_sample_n.sum()), nonpositive_outcomes=int(values.le(0).sum()),
                        median_cfdna_ng_per_ml=values.median(), q1_cfdna_ng_per_ml=values.quantile(.25),
                        q3_cfdna_ng_per_ml=values.quantile(.75), minimum_cfdna_ng_per_ml=values.min(), maximum_cfdna_ng_per_ml=values.max(),
                        status='descriptive', correlation_scale='log10(cfDNA), positive complete pairs')
            if p.kind == 'continuous':
                desc.update(predictor_median=group[p.variable].median(), predictor_q1=group[p.variable].quantile(.25), predictor_q3=group[p.variable].quantile(.75))
                if n >= 2 and data[p.variable].nunique() > 1:
                    slope, intercept = np.polyfit(data[p.variable], data.log10_cfDNA, 1)
                    desc.update(slope_log10_per_unit=slope, intercept_log10=intercept)
                    if data.log10_cfDNA.nunique() > 1:
                        desc.update(pearson_r=data[p.variable].corr(data.log10_cfDNA),
                                    spearman_rho=data[p.variable].rank().corr(data.log10_cfDNA.rank()))
            result['tables']['Descriptions'].append(desc)
            described = True
        if not described:
            result['tables']['Descriptions'].append(dict(predictor=p.variable, n=0, status='unavailable', reason=reason))
        if p.variable not in tested:
            continue
        model, table = engine.fit_regression(data, p)
        models[p.variable] = model
        if model is not None:
            diag = engine.model_diagnostics(model).iloc[0].to_dict()
            diag['predictor'] = p.variable
            result['tables']['Diagnostics'].append(diag)
            influence = model.get_influence()
            for i, (_, observation) in enumerate(data.iterrows()):
                residuals.append(dict(subject_hash=observation.subject_hash, predictor=p.variable,
                                      fitted_log10=float(model.fittedvalues.iloc[i]), residual=float(model.resid.iloc[i]),
                                      leverage=float(influence.hat_matrix_diag[i]), cooks_distance=float(influence.cooks_distance[0][i])))
            if p.kind == 'continuous':
                table = table.loc[table.term.eq(p.variable)].copy()
                increment = 10.0 if p.variable.endswith('_percent') else 1.0
                table['predictor_increment'] = increment
                for source, target in [('coefficient', 'fold_change'), ('ci95_low', 'ci95_low_fc'), ('ci95_high', 'ci95_high_fc')]:
                    table[target] = np.power(10., table[source]*increment)
            else:
                table = table.iloc[[0]].copy()
                table['term'] = 'overall predictor'
                table['p_value'] = table.f_p_value
                table[['coefficient', 'ci95_low', 'ci95_high']] = np.nan
                table[['std_error', 't_statistic']] = np.nan
        else:
            result['tables']['Diagnostics'].append(dict(predictor=p.variable, status='skipped', n=n, note=table.reason.iat[0]))
        if args.spearman_sensitivity and p.variable == 'peripheral_blast_percent':
            for key, value in engine.spearman_sensitivity(data, p).items():
                table[key] = value
        row = table.iloc[0].to_dict()
        row.update(inference='Single-predictor association; no covariate adjustment or causal interpretation',
                   correction='BH across configured predictors within cohort; unavailable p=1 for adjustment only',
                   family_size=len(tested), contributing_outcome_samples=coverage['contributing_outcome_samples'])
        result['tables']['Associations'].append(row)
    tables = result['tables']['Associations']
    if tables:
        adjusted = multipletests([r['p_value'] if r['status'] == 'fit' else 1.0 for r in tables], method='fdr_bh')[1]
        for row, padj in zip(tables, adjusted, strict=True):
            row['p_adj_bh'] = float(padj) if row['status'] == 'fit' else None
    for variable, reason in DEFERRED.items():
        result['tables']['Coverage'].append(dict(cohort=scope, predictor=variable, status='unavailable', analysis_patients=0,
                                                  inference='unavailable', reason=reason))
    return clean(result), models, clean(residuals)
