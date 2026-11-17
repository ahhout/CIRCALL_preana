"""Evaluate a single cohort under the inventory and clinical gates."""
from analysis.utils.retrospective_controls import inspect_with_controls
from analysis.utils.sample_io import SourceReadError
from analysis.disease_modeling.common import ClinicalError, clean
from analysis.disease_modeling import counts, mrd


def base_result(scope, status='complete', blocking=None):
    return dict(scope=scope, status=status, summary={'population_basis': 'Modality-specific populations; no count/MRD linkage'},
                blocking=blocking or [], tables=dict(Coverage=[], MRD=[], Counts=[],
                Models=[dict(status='disabled', reason='Descriptive first release; normalized modeling is a later opt-in increment')],
                Diagnostics=[dict(status='descriptive', note='Source integrity, clinical annotation and count validation; no hypothesis tests')]))

def evaluate(cohort, args, d, rules):
    result = base_result(cohort)
    prepared = dict(mrd=[], counts=[])
    inventory = args.inventory if cohort == 'retrospective' else args.circall
    stage = 'inventory_integrity'
    integrity = None
    try:
        integrity = inspect_with_controls(inventory, cohort, args.include_controls, rules, args.donors)
        result['summary'].update(integrity_errors=integrity['summary']['errors'], integrity_reviews=integrity['summary']['reviews'])
        if integrity['summary']['errors']:
            result.update(status='blocked', blocking=[dict(reason='layer1_error', sheet=g['sheet'], field=g['field'], rule=g['rule'], occurrences=g['count'])
                                                     for g in integrity['groups'] if g['severity'] == 'error'])
            return clean(result), prepared, integrity
        if args.analysis != 'counts':
            stage = 'mrd'
            prepared['mrd'], coverage = mrd.prepare(inventory, cohort, d, duplicate_policy=args.retrospective_mrd_duplicate_policy)
            result['summary']['mrd_retained_patients'] = coverage['retained_patients']
            result['tables']['Coverage'].append(dict(analysis='mrd', **coverage,
                                                    status='available' if any(r['status'] not in ('missing', 'normalized_baseline') for r in prepared['mrd']) else 'unavailable',
                                                    reason='Source-specific MRD population; no receipt or cfDNA eligibility filter'))
            result['tables']['MRD'] = mrd.summary(prepared['mrd'], d['pooled_visits'] if cohort == 'circall' else d['visits'])
        else:
            result['tables']['Coverage'].append(dict(analysis='mrd', status='not_selected'))
        if args.analysis != 'mrd':
            stage = 'counts'
            path = args.retrospective_blasts if cohort == 'retrospective' else args.blood_counts
            prepared['counts'], availability = counts.prepare(path, cohort, d, baseline_day_max=args.baseline_day_max,
                                                               baseline_selection=args.baseline_selection, overlay_max_day=args.overlay_max_day)
            result['tables']['Coverage'].append(dict(analysis='counts', **availability,
                                                    status='available' if any(r['value'] is not None for r in prepared['counts']) else 'unavailable',
                                                    reason='Recorded source population; no inventory matching or count derivation'))
            result['tables']['Counts'] = counts.summary(prepared['counts'], d['counts'][cohort]['sheets'], overlay_max_day=args.overlay_max_day)
            if cohort == 'retrospective':
                result['tables']['Coverage'].append(dict(analysis='wbc', status='unavailable', reason='No retrospective longitudinal WBC source; not reconstructed'))
            result['summary']['count_identity_basis'] = d['counts'][cohort]['identity_rule']
        else:
            result['tables']['Coverage'].append(dict(analysis='counts', status='not_selected'))
        result['summary']['clinical_cache_unavailable'] = sum(v for c in result['tables']['Coverage'] for k, v in c.items() if k.endswith('cache_unavailable'))
        if result['summary']['clinical_cache_unavailable']:
            result['tables']['Diagnostics'].append(dict(status='review', note='Clinical formula caches unavailable; counts/annotations remain unavailable rather than zero'))
        return clean(result), prepared, integrity
    except ClinicalError as error:
        result.update(status='blocked', blocking=[dict(analysis=stage, **error.finding)])
    except SourceReadError as error:
        result.update(status='blocked', blocking=[dict(reason=error.code, analysis=stage)])
    except Exception as error:
        # Even external library exception messages can contain identifiers.
        result.update(status='execution_failed', blocking=[dict(reason=type(error).__name__)])
    result['tables']['MRD'] = []
    result['tables']['Counts'] = []
    return clean(result), dict(mrd=[], counts=[]), integrity
