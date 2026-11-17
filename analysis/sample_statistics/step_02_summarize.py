"""Aggregate the approved inventory and measurement views."""
from collections import Counter, defaultdict
import numpy as np


def dimensions(rows, views):
    """Disjoint groups within each named view; totals never add across views."""
    specs = {'overall': (), 'center': ('center',), 'specimen': ('specimen',),
             'visit': ('visit',), 'specimen_visit': ('specimen','visit'),
             'center_specimen': ('center', 'specimen'),
             'center_specimen_visit': ('center', 'specimen', 'visit')}
    for view in views:
        fields=specs[view]
        groups = defaultdict(list)
        for row in rows:
            groups[tuple(row[f] for f in fields)].append(row)
        for values, group in sorted(groups.items()):
            yield dict(view=view, **dict(zip(fields, values))), group

def describe(values):
    if not values:
        return dict(n=0, mean=None, sd=None, median=None, q1=None, q3=None, minimum=None, maximum=None)
    a = np.asarray(values, dtype=float)
    return dict(n=len(a), mean=float(a.mean()), sd=float(a.std(ddof=1)) if len(a)>1 else None,
                median=float(np.median(a)), q1=float(np.quantile(a,.25)), q3=float(np.quantile(a,.75)),
                minimum=float(a.min()), maximum=float(a.max()))

def aggregate(rows, d, pooled=False, *, detailed=False):
    totals, receipts, measures, availability, checklist = [], [], [], [], []
    views=['overall','center','specimen','visit','center_specimen','center_specimen_visit'] if detailed else d['inventory_views']
    for dims, group in dimensions(rows, views):
        received = [r for r in group if r['receipt'] in ('received', 'received_early')]
        totals.append({**dims, 'samples': len(group), 'patients': len({r['subject_key'] for r in group}),
                       'received_samples': len(received), 'received_patients': len({r['subject_key'] for r in received})})
        for status, count in sorted(Counter(r['extraction_status'] for r in group).items()):
            availability.append({**dims, 'field': 'extraction_status', 'state': status, 'count': count})
        if not pooled:
            for basis in sorted({r['receipt_basis'] for r in group}):
                subset = [r for r in group if r['receipt_basis'] == basis]
                counts = Counter(r['receipt'] for r in subset)
                received_due=sum(r.get('due_received',False) for r in subset)
                overdue=sum(r.get('overdue',False) and r['receipt']=='marked_missing' for r in subset)
                denominator = received_due + overdue
                percentages = basis == 'deadline' and not any(r['control'] for r in subset)
                for status, count in sorted(counts.items()):
                    classified=received_due if status=='received' else overdue if status=='marked_missing' else 0
                    receipts.append({**dims, 'basis': basis, 'status': status, 'samples': count,
                                     'patients': len({r['subject_key'] for r in subset if r['receipt']==status}),
                                     'overdue_samples':sum(r.get('overdue',False) for r in subset if r['receipt']==status),
                                     'classified_samples':classified if percentages else None,
                                     'classified_denominator': denominator if percentages else None,
                                     'classified_percentage': classified/denominator if percentages and denominator and status in ('received','marked_missing') else None})
    for row in rows:
        if not pooled and row.get('overdue',False):
            checklist.append({**{k: row[k] for k in ('patient_id','center','visit','specimen','sheet','row','receipt_reason')},
                              'status':row['overdue_status']})
    # Each metric/specimen/assay has its own denominator; cohort contributions stay visible.
    for field, definition in d['metrics'].items():
        eligible = [r for r in rows if r['specimen'] in definition['specimens'] and r['cohort'] not in definition.get('exclude_cohorts', [])
                    and (not pooled or (r['specimen'] in definition['pool'] and r['visit'] in d['pooled_visits']))]
        for view, keys in [('specimen', ('specimen','assay')), ('visit', ('specimen','assay','visit')),
                           ('center_visit', ('specimen','assay','center','visit')),
                           *([('cohort_visit', ('specimen','assay','cohort','visit'))] if pooled else [])]:
            if not detailed and view not in d['measurement_views']:continue
            groups = defaultdict(list)
            for row in eligible:
                # Plasma endpoints and pooled fragment size have approved common
                # groups; other recorded DNA-type distinctions remain separate.
                key = tuple(('specimen volume' if k=='assay' and field=='extraction_input_volume_ml' else 'cfDNA size' if k=='assay' and pooled and field=='cfdna_avg_size_bp' else 'plasma DNA' if k=='assay' and row['specimen']=='plasma' else row[k]) for k in keys)
                groups[key].append(row)
            for key, group in sorted(groups.items()):
                dims = dict(view=view, field=field, unit=definition['unit'], **dict(zip(keys,key)))
                received = [r for r in group if r['receipt'] in ('received','received_early')]
                observed = [r for r in received if r['measurements'][field]['value'] is not None]
                values = [r['measurements'][field]['value'] for r in observed]
                measures.append({**dims, 'received_samples':len(received), 'available_patients':len({r['subject_key'] for r in observed}),
                                 'unavailable_samples':len(received)-len(values), **describe(values),
                                 'total':sum(values) if values and definition['sum'] else None})
                states = Counter()
                for r in group:
                    state = r['measurements'][field]['state']
                    if r['receipt'] not in ('received','received_early'):
                        state = 'receipt_unconfirmed_numeric' if r['measurements'][field]['value'] is not None else 'receipt_unconfirmed_'+state
                    states[state] += 1
                availability.extend({**dims, 'state':state,'count':count} for state,count in sorted(states.items()))
    result=dict(summary=totals, receipt=receipts, measurements=measures, availability=availability, missed=checklist)
    if not detailed:
        detail=aggregate(rows,d,pooled=pooled,detailed=True)
        detail.pop('missed')
        result['audit_detail']=detail
    return result
