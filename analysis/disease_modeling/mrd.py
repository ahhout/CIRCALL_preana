"""Local MRD parsing, harmonized selection and descriptive aggregation."""
from collections import Counter, defaultdict
import math
import re

from .common import ClinicalError, cell_state, clean, identity, source_rows, token

STATUSES = ('normalized_baseline', 'quantified', 'positive_nonquantifiable',
            'unknown_significance', 'negative', 'missing')


def parse_annotation(value, cohort, d):
    """Return status, measurement and reported limit (CIRCALL sensitivity or retrospective bound)."""
    label = ' '.join(token(value).split())
    if label in d['missing_tokens'] + d['unknown_tokens']:
        return 'missing', None, None
    if label in ('negative', 'neg'):
        return 'negative', None, None
    if label in ('unknown significance', 'unknown signif', 'unknown signif.'):
        if cohort != 'circall':
            raise ClinicalError('unconfirmed_retrospective_mrd_category')
        return 'unknown_significance', None, None
    if cohort in ('retrospective', 'circall'):
        labels = d['mrd']['circall_positive_nq']['labels'] if cohort == 'circall' else ['pos nq']
        prefix = '|'.join(re.escape(v).replace(r'\ ', r'\s+') for v in labels)
        match = re.fullmatch(r'(?:'+prefix+r')(?:\s*<\s*(.+))?', label)
        if match:
            bound = None
            if match[1] is not None:
                encoded = match[1].replace(' ', '')
                power = re.fullmatch(r'(?:(\d+(?:[.,]\d+)?)[.*×])?10\^?(-\d+)', encoded)
                try:
                    bound = (float((power[1] or '1').replace(',', '.')) * 10.**int(power[2])
                             if power else float(encoded.replace(',', '.')))
                except (ValueError, OverflowError):
                    raise ClinicalError('invalid_mrd_bound') from None
                if not math.isfinite(bound) or not 0 < bound <= d['mrd']['maximum_inclusive']:
                    raise ClinicalError('invalid_mrd_bound')
            return 'positive_nonquantifiable', None, bound
    try:
        number = float(label.replace(',', '.'))
    except ValueError:
        raise ClinicalError('invalid_mrd_annotation') from None
    if isinstance(value, bool) or not math.isfinite(number) or not 0 < number <= d['mrd']['maximum_inclusive']:
        raise ClinicalError('invalid_mrd_fraction')
    return 'quantified', number, None


def prepare(path, cohort, d, *, duplicate_policy):
    config = d['mrd'][cohort]
    required = [config['identity']]
    if cohort == 'retrospective':
        required += [config[k] for k in ('value', 'visit', 'specimen')]
    else:
        required += list(config['values'].values())
    rows = source_rows(path, config['sheet'], required)
    people = defaultdict(lambda: defaultdict(dict))
    represented = set()
    centers = {}
    counters = Counter(source_rows=len(rows), selected_source_rows=0, identified_source_patients=0,
                       resolved_disagreements=0, excluded_other_specimen_or_visit=0)
    states = Counter()
    for row in rows:
        if cohort == 'retrospective':
            visit = token(row[config['visit']].value).upper()
            if token(row[config['specimen']].value) != config['specimen_filter'] or visit not in d['visits']:
                counters['excluded_other_specimen_or_visit'] += 1
                continue
            fields = {visit: config['value']}
        else:
            fields = config['values']
            # Numbering-only rows are not participants.
            if (cell_state(row[config['identity']], d) != 'available'
                    and all(cell_state(row[f], d) in ('missing', 'unknown', 'intentional_empty', 'cache_unavailable') for f in fields.values())):
                continue
        key = identity(row[config['identity']], cohort, 'mrd', d)
        if key is None:
            raise ClinicalError('invalid_mrd_participant_id', sheet=config['sheet'], cell=row[config['identity']].coordinate)
        from analysis.plot_style import center_from_id
        centers[key] = center_from_id(row[config['identity']].value, cohort)
        represented.add(key)
        counters['selected_source_rows'] += 1
        for visit, field in fields.items():
            cell = row[field]
            state = cell_state(cell, d)
            states[state] += 1
            if state == 'invalid':
                raise ClinicalError('invalid_mrd_cell', sheet=config['sheet'], cell=cell.coordinate)
            try:
                annotation = parse_annotation(cell.value, cohort, d) if state == 'available' else ('missing', None, None)
            except ClinicalError as error:
                raise ClinicalError(error.finding['reason'], sheet=config['sheet'], cell=cell.coordinate) from None
            visits = people[key]
            values = visits[visit]
            if annotation[0] != 'missing':
                values.setdefault(annotation, []).append(cell.coordinate)
    records = []
    for key, visits in sorted(people.items()):
        if cohort == 'circall' and not any(visits.values()):
            continue
        for visit, values in sorted(visits.items()):
            if len(values) > 1 and (cohort == 'circall' or duplicate_policy == 'error'):
                raise ClinicalError('conflicting_mrd_metadata', sheet=config['sheet'], visit=visit,
                                    cells=sorted(c for coordinates in values.values() for c in coordinates))
            if values:
                priority = {s: i for i, s in enumerate(d['mrd']['retrospective_repeat_priority'])}
                def rank(a):
                    return priority.get(a[0], 0), a[1] if a[1] is not None else a[2] if a[2] is not None else -math.inf
                status, fraction, bound = max(values, key=rank)
            else:
                status, fraction, bound = 'missing', None, None
            counters['resolved_disagreements'] += int(len(values) > 1)
            records.append(dict(cohort=cohort, subject_hash=key, center=centers[key], visit=visit, status=status,
                                measured_fraction=fraction, upper_bound_fraction=bound if cohort == 'retrospective' else None,
                                reported_sensitivity_fraction=bound if cohort == 'circall' else None,
                                measured_log10_reduction=-math.log10(fraction) if fraction is not None else None,
                                distinct_annotations=len(values), resolved_disagreement=len(values) > 1,
                                contributing_source_entries=sum(len(c) for c in values.values())))
        if cohort == 'circall':
            records.append(dict(cohort=cohort, subject_hash=key, center=centers[key], visit='Diagnosis', status='normalized_baseline',
                                measured_fraction=None, upper_bound_fraction=None, reported_sensitivity_fraction=None, measured_log10_reduction=None,
                                distinct_annotations=0, resolved_disagreement=False, contributing_source_entries=0))
    counters.update(identified_source_patients=len(represented), retained_patients=len({r['subject_hash'] for r in records}),
                    retained_patient_visits=len(records), patients_without_any_clinical_result=len(represented)-len({r['subject_hash'] for r in records}))
    counters.update({'source_'+state: states[state] for state in ('available', 'missing', 'unknown', 'cache_unavailable', 'intentional_empty')})
    return records, dict(counters)


def summary(records, visits, *, fixed=False):
    rows = []
    for visit in visits:
        group = [r for r in records if r['visit'] == visit]
        counts = Counter(r['status'] for r in group)
        measured = [r['measured_fraction'] for r in group if r['measured_fraction'] is not None]
        sensitivities = Counter(r['reported_sensitivity_fraction'] for r in group
                                if r.get('reported_sensitivity_fraction') is not None)
        import numpy as np
        rows.append(dict(visit=visit, patients=len(group), patients_with_result=sum(counts[s] for s in STATUSES if s not in ('missing', 'normalized_baseline')),
                         **{s: counts[s] for s in STATUSES}, quantified_median=float(np.median(measured)) if measured else None,
                         quantified_min=min(measured) if measured else None, quantified_max=max(measured) if measured else None,
                         positive_nq_with_bound=sum(r['upper_bound_fraction'] is not None for r in group),
                         positive_nq_with_sensitivity=sum(sensitivities.values()),
                         reported_sensitivity_counts=[dict(fraction=value, patients=count) for value, count in sorted(sensitivities.items())],
                         resolved_disagreements=sum(r['resolved_disagreement'] for r in group),
                         denominator_basis='Fixed retained MRD population' if fixed else 'Source-specific represented patient/visit population',
                         retrospective_patients=sum(r['cohort'] == 'retrospective' for r in group),
                         circall_patients=sum(r['cohort'] == 'circall' for r in group)))
    return clean(rows)


def pool(cohorts, d):
    people = {(r['cohort'], r['subject_hash']) for records in cohorts.values() for r in records}
    existing = {(r['cohort'], r['subject_hash'], r['visit']): r for records in cohorts.values() for r in records if r['visit'] != 'Diagnosis'}
    result = []
    for cohort, key in sorted(people):
        for visit in d['pooled_visits']:
            record = existing.get((cohort, key, visit))
            if record is None:
                record = dict(cohort=cohort, subject_hash=key, visit=visit,
                              status='normalized_baseline' if visit == 'Diagnosis' else 'missing', measured_fraction=None,
                              upper_bound_fraction=None, reported_sensitivity_fraction=None, measured_log10_reduction=None, distinct_annotations=0,
                              resolved_disagreement=False, contributing_source_entries=0)
            result.append(record)
    return result
