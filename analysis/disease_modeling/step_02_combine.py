"""Construct aggregate pooled and comparison scopes."""
from analysis.disease_modeling.step_01_evaluate import base_result
from analysis.disease_modeling.common import clean
from analysis.disease_modeling import mrd


def combined_results(evaluated, args, d):
    results = {}
    clean_cohorts = {c: p for c, (r, p, _) in evaluated.items() if r['status'] == 'complete'}
    if args.pool_mrd and args.analysis != 'counts' and args.cohort == 'all':
        blocked = len(clean_cohorts) != 2
        ready = not blocked and all(p['mrd'] for p in clean_cohorts.values())
        status = 'blocked' if blocked else 'complete' if ready else 'unavailable'
        r = base_result('pooled', status, [] if ready else [dict(reason='Both cohorts need retained MRD populations and completed gates')])
        prepared = dict(mrd=mrd.pool({c: p['mrd'] for c, p in clean_cohorts.items()}, d) if ready else [], counts=[])
        r['tables']['Coverage'] = [dict(analysis='mrd', status='available' if ready else status,
                                         reason='Fixed union of source-specific retained MRD populations; descriptive only')]
        r['tables']['MRD'] = mrd.summary(prepared['mrd'], d['pooled_visits'], fixed=True) if ready else []
        r['summary']['retained_mrd_patients'] = len({(row['cohort'], row['subject_hash']) for row in prepared['mrd']}) if ready else None
        results['pooled'] = clean(r), prepared
    if args.analysis != 'mrd' and args.cohort == 'all':
        ready = len(clean_cohorts) == 2 and all(any(r['measurement'] == 'blast' and r['value'] is not None for r in p['counts']) for p in clean_cohorts.values())
        r = base_result('comparisons', 'complete' if ready else 'unavailable', [] if ready else [dict(reason='Both cohorts need recorded blast counts and completed gates')])
        prepared = dict(mrd=[], counts=[r for p in clean_cohorts.values() for r in p['counts']] if ready else [])
        r['tables']['Counts'] = [dict(cohort=c, **row) for c, (result, _, _) in evaluated.items() if ready for row in result['tables']['Counts'] if row['measurement'] == 'blast']
        r['tables']['Coverage'] = [dict(analysis='blast_cohort_comparison', status='available' if ready else 'unavailable', reason='Separate cohort populations and trajectories; no pooled counts or fit')]
        results['comparisons'] = clean(r), prepared
    return results
