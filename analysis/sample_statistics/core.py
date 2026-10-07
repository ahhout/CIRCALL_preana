"""Receipt and descriptive rules; raw identifying columns never enter results."""
from collections import Counter, defaultdict
from datetime import date, datetime, time, timedelta, timezone
import json
import re
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np

from analysis.configuration import unique_object
from analysis.data_integrity.checks import number
from analysis.sample_io import read_sheet


def load_definitions(path):
    try:
        d = json.loads(Path(path).read_text(), object_pairs_hook=unique_object)
        if d['schema_version'] != 1 or d['timezone'] != 'Europe/Paris' or d['grace_hours'] != 72:
            raise ValueError()
        ZoneInfo(d['timezone'])
        expected = json.loads((Path(__file__).resolve().parents[2]/'configs/definitions/sample_statistics.json').read_text())
        # This version implements only the investigator-approved semantics. Different
        # scientific policies require an explicit versioned code/contract change.
        if d != expected:
            raise ValueError()
        return d
    except (ValueError, KeyError, TypeError, OSError):
        raise ValueError('Invalid sample-statistics definitions') from None


def assessment(value=None):
    result = datetime.fromisoformat(value.replace('Z', '+00:00')) if value else datetime.now(timezone.utc)
    if result.tzinfo is None:
        raise ValueError('Assessment timestamp needs an explicit UTC offset')
    return result.astimezone(timezone.utc)


def token(value):
    return '' if value is None else str(value).strip().casefold()


def id_kind(value, d):
    s = token(value)
    if s == d['manual_missed_token']:
        return 'manual_na'
    if s in d['unknown_tokens']:
        return 'unknown'
    if s in d['missing_tokens']:
        return 'absent'
    return 'present'


def receipt(sample, visit, planned, cohort, as_of, d, control=False):
    kind = id_kind(sample, d)
    timed = not control and cohort == 'circall' and visit in d['deadline_visits'] and isinstance(planned, (date, datetime))
    start = None
    if timed:
        day = planned.date() if isinstance(planned, datetime) else planned
        start = datetime.combine(day, time(), ZoneInfo(d['timezone'])).astimezone(timezone.utc)
    basis = 'deadline' if timed else ('retrospective_inventory' if cohort == 'retrospective' else 'manual_or_id')
    if kind == 'present':
        status = 'received_early' if timed and as_of < start else 'received'
    elif timed:
        status = ('not_yet_due' if as_of < start else
                  'pending' if as_of <= start + timedelta(hours=d['grace_hours']) else 'missed')
    elif cohort == 'retrospective' or control:
        status = {'manual_na': 'marked_na', 'unknown': 'unknown', 'absent': 'absent'}[kind]
    else:
        status = 'missed' if kind == 'manual_na' else 'unassessed'
    return dict(receipt=status, receipt_basis=basis, receipt_reason=(
        'deadline_elapsed' if status == 'missed' and timed else
        'manual_na' if status == 'missed' else status), id_state=kind)


def measurement(cell, extraction_status, d):
    if cell is None:
        return {'value': None, 'state': 'field_unavailable'}
    if cell.data_type == 'e' or cell.cached_type == 'e':
        return {'value': None, 'state': 'excel_error'}
    if cell.formula and cell.value is None:
        return {'value': None, 'state': 'intentional_empty' if cell.cached_type == 'str' else 'cache_unavailable'}
    s = token(cell.value)
    if s in d['unknown_tokens']:
        return {'value': None, 'state': 'unknown'}
    if cell.value is None or s == '':
        return {'value': None, 'state': 'not_applicable' if extraction_status == 'not_extracted' else 'blank'}
    if s in d['missing_tokens']:
        return {'value': None, 'state': 'not_applicable' if s in ('na', 'n/a') else 'missing_marker'}
    value, state = number(cell.value, d['missing_tokens'], d['unknown_tokens'])
    return {'value': value, 'state': 'available' if state in ('number', 'text') else 'qualified_or_invalid'}


def prepare(path, cohort, controls, as_of, d):
    rows, issues, skipped = [], [], 0
    sheets = ['Inventaire'] if cohort == 'retrospective' else ['cohorte_lal'] + (['cohorte_control'] if controls else [])
    for sheet_name in sheets:
        sheet = read_sheet(path, sheet_name)
        headers = [c.value for c in sheet.headers]
        control = sheet_name == 'cohorte_control'
        identity = 'patient_id' if cohort == 'retrospective' else 'circall_id'
        required = ['sample_id', 'specimen_type', identity] + ([] if control else ['timepoint'])
        for field in required:
            if headers.count(field) != 1:
                issues.append({'sheet': sheet_name, 'row': None, 'reason': 'identity_or_header_unavailable', 'field': field})
        if cohort == 'retrospective' and 'patient_id' not in headers:
            issues.append({'sheet': sheet_name, 'row': None, 'reason': 'identity_migration_pending', 'field': 'patient_id'})
        for cells in sheet.rows:
            source = {h: c for h, c in zip(headers, cells) if h is not None}
            val = lambda field: source[field].value if field in source else None
            anchors = ('sample_id', 'specimen_type', 'timepoint', 'dna_id', identity)
            if not any(val(f) is not None and token(val(f)) != '' for f in anchors):
                skipped += 1
                continue
            row = cells[0].row
            pid = val(identity)
            valid_identity = id_kind(pid, d) == 'present' and not (identity in source and source[identity].formula)
            if cohort == 'circall' and valid_identity:
                # CIRCALL pseudonyms are the existing protocol IDs, never name fallbacks.
                valid_identity = bool(re.fullmatch(r'\d{3}-\d{4}-[A-Za-z]-[A-Za-z]', str(pid).strip()))
            if not valid_identity:
                issues.append({'sheet': sheet_name, 'row': row, 'reason': 'patient_identity_unavailable', 'field': identity})
                continue
            pid = str(pid).strip()
            center = d['retrospective_center'] if cohort == 'retrospective' else d['centers'].get(pid[:3], 'unknown')
            visit = token(val('timepoint')) if not control else 'control'
            visit = visit if visit in d['visits'] or control else 'unclassified'
            specimen = val('specimen_type')
            specimen = specimen if specimen in d['specimens'] else 'unclassified'
            acid = token(val('nucleic_acid'))
            assay = acid if acid in ('cfdna', 'celdna') else 'not_recorded'
            extraction = token(val('extraction_status'))
            extraction = extraction if extraction in ('not_extracted', 'extracted', 'pending', 'unknown') else 'unclassified'
            item = dict(cohort=cohort, sheet=sheet_name, row=row, patient_id=pid,
                        subject_key=f'{cohort}:{sheet_name}:{pid}', center=center,
                        visit=visit, specimen=specimen, assay=assay, control=control,
                        extraction_status=extraction)
            item.update(receipt(val('sample_id'), visit, val('sampling_plan'), cohort, as_of, d, control))
            item['measurements'] = {f: measurement(source.get(f), 'unclassified' if f=='extraction_input_volume_ml' else extraction, d) for f in d['metrics']}
            rows.append(item)
    return rows, issues, skipped


def dimensions(rows, pooled=False):
    """Disjoint groups within each named view; totals never add across views."""
    specs = [('overall', ()), ('center', ('center',)), ('specimen', ('specimen',)),
             ('visit', ('visit',)), ('center_specimen_visit', ('center', 'specimen', 'visit'))]
    for view, fields in specs:
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


def aggregate(rows, d, pooled=False):
    totals, receipts, measures, availability, checklist = [], [], [], [], []
    for dims, group in dimensions(rows):
        received = [r for r in group if r['receipt'] in ('received', 'received_early')]
        totals.append({**dims, 'samples': len(group), 'patients': len({r['subject_key'] for r in group}),
                       'received_samples': len(received), 'received_patients': len({r['subject_key'] for r in received})})
        for status, count in sorted(Counter(r['extraction_status'] for r in group).items()):
            availability.append({**dims, 'field': 'extraction_status', 'state': status, 'count': count})
        if not pooled:
            for basis in sorted({r['receipt_basis'] for r in group}):
                subset = [r for r in group if r['receipt_basis'] == basis]
                counts = Counter(r['receipt'] for r in subset)
                denominator = counts['received'] + counts['missed']
                percentages = basis in ('deadline', 'manual_or_id') and not any(r['control'] for r in subset)
                for status, count in sorted(counts.items()):
                    receipts.append({**dims, 'basis': basis, 'status': status, 'samples': count,
                                     'patients': len({r['subject_key'] for r in subset if r['receipt']==status}),
                                     'classified_denominator': denominator if percentages else None,
                                     'classified_percentage': count/denominator if percentages and denominator and status in ('received','missed') else None})
    for row in rows:
        if not pooled and row['receipt'] == 'missed':
            checklist.append({k: row[k] for k in ('patient_id','center','visit','specimen','sheet','row','receipt_reason')})
    # Each metric/specimen/assay has its own denominator; cohort contributions stay visible.
    for field, definition in d['metrics'].items():
        eligible = [r for r in rows if r['specimen'] in definition['specimens'] and r['cohort'] not in definition.get('exclude_cohorts', [])
                    and (not pooled or (r['specimen'] in definition['pool'] and r['visit'] in d['pooled_visits']))]
        for view, keys in [('specimen', ('specimen','assay')), ('visit', ('specimen','assay','visit')),
                           ('center_visit', ('specimen','assay','center','visit')),
                           *([('cohort_visit', ('specimen','assay','cohort','visit'))] if pooled else [])]:
            groups = defaultdict(list)
            for row in eligible:
                # Approved plasma pooling permits the two cohort layouts despite missing
                # CIRCALL nucleic-acid labels; other assays remain separate.
                key = tuple(('specimen volume' if k=='assay' and field=='extraction_input_volume_ml' else 'plasma DNA' if k=='assay' and row['specimen']=='plasma' else row[k]) for k in keys)
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
    return dict(summary=totals, receipt=receipts, measurements=measures, availability=availability, missed=checklist)
