"""Receipt and descriptive rules; raw identifying columns never enter results."""
from analysis.sample_statistics.step_02_summarize import dimensions, describe, aggregate
from datetime import date, datetime, time, timedelta, timezone
import json
import re
from pathlib import Path
from zoneinfo import ZoneInfo


from analysis.configuration import unique_object
from analysis.data_integrity.step_01_inspect import number
from analysis.utils.sample_io import read_sheet
from analysis.utils.sample_definitions import extraction_state
from .calendar_volumes import collection_date


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
    overdue = kind in d['overdue_id_states'] and timed and as_of > start + timedelta(hours=d['grace_hours'])
    due_received = kind == 'present' and timed and as_of >= start
    if kind == 'present':
        status = 'received'
        timing = 'received_early' if timed and as_of < start else 'received' if timed else 'not_assessed'
    elif kind == 'manual_na':
        status = 'marked_missing'
        timing = ('not_yet_due' if timed and as_of < start else 'overdue' if overdue else
                  'pending' if timed else 'not_assessed')
    else:
        status = 'unassessed'
        timing = ('not_yet_due' if timed and as_of < start else 'late' if overdue else
                  'pending' if timed else 'not_assessed')
    return dict(receipt=status, receipt_basis=basis, receipt_reason=(
        'deadline_elapsed' if overdue else 'manual_na' if kind == 'manual_na' else status), id_state=kind,
        receipt_timing=timing, overdue=bool(overdue),
        overdue_status=('marked_missing' if kind=='manual_na' else 'late') if overdue else None,
        overdue_assessed=timed and kind in d['overdue_id_states'],
        due_received=bool(due_received))


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
        return {'value': None, 'state': 'not_applicable' if extraction_status == 'no' else 'blank'}
    if s in d['missing_tokens']:
        return {'value': None, 'state': 'not_applicable' if extraction_status == 'no' else 'missing_marker'}
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
            # Unassigned template visits are not missing patient records. Keep
            # identified planned visits and orphaned records with actual data.
            missing = set(d['missing_tokens']) | set(d['unknown_tokens'])
            empty_template = all(
                field in d['unassigned_template_fields'] or (
                    token(cell.value) in missing and cell.data_type != 'e' and cell.cached_type != 'e'
                    and not (field in (identity, 'sample_id', 'dna_id') and cell.formula))
                for field, cell in source.items())
            if empty_template:
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
            extraction = extraction_state(source.get(d['extraction_basis']), d['missing_tokens'], d['unknown_tokens'])
            item = dict(cohort=cohort, sheet=sheet_name, row=row, patient_id=pid,
                        subject_key=f'{cohort}:{sheet_name}:{pid}', center=center,
                        visit=visit, specimen=specimen, assay=assay, control=control,
                        extraction_status=extraction)
            item.update(receipt(val('sample_id'), visit, val('sampling_plan'), cohort, as_of, d, control))
            item['measurements'] = {f: measurement(source.get(f), 'unclassified' if f=='extraction_input_volume_ml' else extraction, d) for f in d['metrics']}
            volume = d['metrics'].get('extraction_input_volume_ml', {})
            calendar = volume.get('calendar_plot', {})
            if not control and cohort in calendar.get('cohorts', []) and specimen in volume['specimens']:
                item['collection_date'] = collection_date(source.get(calendar['date_field']), d)
            rows.append(item)
    return rows, issues, skipped
