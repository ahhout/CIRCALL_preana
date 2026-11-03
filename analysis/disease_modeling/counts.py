"""Recorded-count preparation and display selection, without legacy imports."""
from collections import Counter, defaultdict
from datetime import date, datetime
import math

import numpy as np

from .common import ClinicalError, cell_state, clean, identity, source_rows


def prepare(path, cohort, d, *, baseline_day_max, baseline_selection, overlay_max_day):
    config = d['counts'][cohort]
    records = []
    states = Counter()
    for sheet, field in config['sheets'].items():
        rows = source_rows(path, sheet, [config['identity'], d['counts']['day'], field])
        seen = set()
        for row in rows:
            cell = row[field]
            state = cell_state(cell, d)
            states[sheet+'_'+state] += 1
            key = identity(row[config['identity']], cohort, 'counts', d)
            if key is None:
                raise ClinicalError('invalid_count_participant_id', sheet=sheet, cell=row[config['identity']].coordinate)
            value = day = None
            if state == 'available':
                try:
                    value = float(str(cell.value).strip().replace(',', '.'))
                except (ValueError, TypeError):
                    raise ClinicalError('invalid_count', sheet=sheet, cell=cell.coordinate) from None
                if isinstance(cell.value, (bool, date, datetime)) or not math.isfinite(value) or value < 0:
                    raise ClinicalError('invalid_count', sheet=sheet, cell=cell.coordinate)
                day_cell = row[d['counts']['day']]
                try:
                    day = float(str(day_cell.value).strip().replace(',', '.'))
                except (ValueError, TypeError):
                    raise ClinicalError('unavailable_measured_day', sheet=sheet, cell=day_cell.coordinate) from None
                if isinstance(day_cell.value, (bool, date, datetime)) or not math.isfinite(day) or not day.is_integer():
                    raise ClinicalError('invalid_measured_day', sheet=sheet, cell=day_cell.coordinate)
                day = int(day)
                if (key, day) in seen:
                    raise ClinicalError('duplicate_measured_subject_day', sheet=sheet, cell=cell.coordinate)
                seen.add((key, day))
            elif state == 'invalid':
                raise ClinicalError('invalid_count_cell', sheet=sheet, cell=cell.coordinate)
            from analysis.plot_style import center_from_id
            records.append(dict(cohort=cohort, subject_hash=key,
                                center=center_from_id(row[config['identity']].value, cohort),
                                measurement=sheet, day=day,
                                value=value, source_state=state, selected_for_plot=value is not None,
                                display_day=baseline_day_max if day is not None and day <= baseline_day_max else day,
                                source_sheet=sheet, source_row=cell.row,
                                source_count_cell=cell.coordinate, source_day_cell=row[d['counts']['day']].coordinate,
                                source_dates={f:row[f] for f in d['counts']['date_fields'] if f in row}))
    grouped = defaultdict(list)
    for r in records:
        if r['value'] is not None and r['day'] <= baseline_day_max:
            grouped[r['measurement'], r['subject_hash']].append(r)
    if baseline_selection == 'latest':
        for group in grouped.values():
            latest = max(r['day'] for r in group)
            for r in group:
                if r['day'] < latest:
                    r['selected_for_plot'] = False
    return records, dict(states)


def summary(records, measurements, *, overlay_max_day):
    rows = []
    for measurement in measurements:
        group = [r for r in records if r['measurement'] == measurement]
        observed = [r for r in group if r['value'] is not None]
        selected = [r for r in observed if r['selected_for_plot']]
        early = [r for r in selected if r['display_day'] <= overlay_max_day]
        values = [r['value'] for r in observed]
        rows.append(dict(measurement=measurement, unit='x10^9/L', source_rows=len(group),
                         patients_in_source=len({r['subject_hash'] for r in group}),
                         patients_with_measurements=len({r['subject_hash'] for r in observed}), measurements=len(observed),
                         missing_counts=len(group)-len(observed), zero_counts=sum(v == 0 for v in values),
                         plotted_full_range_measurements=len(selected), plotted_early_measurements=len(early),
                         earlier_diagnostic_measurements_not_plotted=len(observed)-len(selected),
                         full_range_patients=len({r['subject_hash'] for r in selected}),
                         early_range_patients=len({r['subject_hash'] for r in early}),
                         first_recorded_day=min((r['day'] for r in observed), default=None),
                         last_recorded_day=max((r['day'] for r in observed), default=None),
                         median=float(np.median(values)) if values else None,
                         mean=float(np.mean(values)) if values else None,
                         minimum=min(values) if values else None, maximum=max(values) if values else None,
                         status='available' if observed else 'unavailable'))
    return clean(rows)
