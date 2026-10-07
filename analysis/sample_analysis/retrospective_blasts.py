"""Retrospective blast ingestion and descriptive cohort figures; no row exports."""
import hashlib
import json
from pathlib import Path

import pandas as pd
from matplotlib.lines import Line2D

from . import blood_counts as counts
from .preparation import read_sheet


def observations(path, *, unit):
    if unit != 'x10^9/L':
        raise ValueError('Retrospective blast counts require an explicitly confirmed x10^9/L unit')
    sheet = 'blast'
    _, rows, _ = read_sheet(path, sheet, {'lastname', 'day', 'blast_count_x10*9/L'})
    records = []
    seen = set()
    for row in rows:
        # Preserve the normalized engine's case-sensitive, whitespace-trimmed identity.
        raw_id = row.value('lastname')
        if raw_id is None or not str(raw_id).strip():
            raise ValueError(f'Missing retrospective subject identifier at row {row.number}')
        key = 'retrospective_blast:' + hashlib.sha256(str(raw_id).strip().encode()).hexdigest()
        cell = row.cells['blast_count_x10*9/L']
        value = counts.number(cell.value, f'{sheet}!{cell.coordinate}')
        if value is None and cell.formula:
            raise ValueError(f'Missing cached blast count at {sheet}!{cell.coordinate}; recalculate workbook')
        day = None
        if value is not None:
            day = _day(row)
            if (key, day) in seen:
                raise ValueError(f'Repeated retrospective patient/day at row {row.number}; no measurements combined')
            seen.add((key, day))
        records.append({'measurement': 'blast', 'patient_key': key, 'day': day,
                        'count_x10_9_per_L': value, 'status': 'missing' if value is None else 'measured'})
    frame = pd.DataFrame(records)
    if frame.empty or not frame.status.eq('measured').any():
        raise ValueError('No measured retrospective blast counts in blast')
    return frame


def _day(row):
    import math
    raw = row.value('day')
    try:
        value = float(str(raw).replace(',', '.'))
    except (TypeError, ValueError):
        raise ValueError(f'Invalid retrospective measurement day at row {row.number}') from None
    if isinstance(raw, bool) or not math.isfinite(value) or not value.is_integer():
        raise ValueError(f'Expected an integer retrospective day at row {row.number}')
    return int(value)


def write_results(frame, circall, path, output, *, unit, baseline_day_max, baseline_selection, overlay_max_day, y_scale='log'):
    """Write aggregate counts, provenance and unlabeled patient trajectories only."""
    plt = counts.plt
    retro_summary = counts.summary_table(frame, measurements=('blast',)).assign(cohort='retrospective')
    parts = [retro_summary]
    if circall is not None:
        parts.append(counts.summary_table(circall).assign(cohort='circall'))
    summary = pd.concat(parts, ignore_index=True)
    counts.reporting.table(output / 'blood_count_summary.csv', summary)
    settings = {'cohort': 'retrospective', 'source_file': str(Path(path).resolve()),
                'source_sha256': hashlib.sha256(Path(path).read_bytes()).hexdigest(),
                'sheet': 'blast', 'columns': {'subject': 'lastname', 'day': 'day', 'blast': 'blast_count_x10*9/L'},
                'units': unit, 'unit_basis': 'Investigator confirmation on 2026-10-01; no conversion',
                'diagnostic_baseline_day_max': baseline_day_max, 'diagnostic_baseline_selection': baseline_selection,
                'overlay_max_day': overlay_max_day, 'day_filter_scope': 'Overlay filtering and blast trajectory x-axis limit; summaries retain all days',
                'y_scale': y_scale, 'normalization': None, 'winsorization': None, 'statistical_tests': None,
                'minimum_measurements': None, 'positive_baseline_required': False,
                'identity': 'Case-sensitive trimmed surname within source; source-qualified digest in memory only',
                'cross_cohort_matching': False, 'row_level_export': False,
                'missing_counts': 'Retained in memory and aggregate summary; not plotted', 'zero_counts': 'Recorded zeros retained in data and summaries; not displayed on log axes; lines break at zero',
                'wbc': 'Not supplied; not inferred from blast fractions', 'mrd': 'CIRCALL only'}
    (output / 'retrospective_plot_settings.json').write_text(json.dumps(settings, indent=2) + '\n')
    note = ('Recorded counts; lines connect measurements within each patient.\n'
            + counts.scale_note(y_scale) + '\n' +
            ('Latest diagnostic measurement selected.' if baseline_selection == 'latest' else 'All diagnostic measurements retained.'))
    fig, ax = plt.subplots(figsize=(10.5, 6.5))
    counts.draw(ax, frame, 'blast', baseline_day_max=baseline_day_max, cohort='retrospective', blast_max_day=overlay_max_day, y_scale=y_scale)
    fig.text(.5, .015, note, ha='center', fontsize=9)
    fig.tight_layout(rect=(0, .13, 1, 1))
    counts.reporting.save(fig, output / 'retrospective_blast_trajectories.png')
    if circall is not None:
        fig, axes = plt.subplots(1, 2, figsize=(14, 6), sharey=True)
        for ax, data, cohort in zip(axes, (frame, circall), ('retrospective', 'circall')):
            counts.draw(ax, data, 'blast', baseline_day_max=baseline_day_max, cohort=cohort, blast_max_day=overlay_max_day, y_scale=y_scale)
        fig.text(.5, .015, note + '\nCohorts shown separately; common count scale and display window.', ha='center', fontsize=9)
        fig.tight_layout(rect=(0, .17, 1, 1))
        counts.reporting.save(fig, output / 'blast_trajectories_by_cohort.png')
        fig, ax = plt.subplots(figsize=(10.5, 6.5))
        handles = []
        for data, cohort in ((frame, 'retrospective'), (circall, 'circall')):
            selected = data.loc[data.measurement.eq('blast') & data.selected_for_plot & data.display_day.le(overlay_max_day)]
            color = counts.reporting.COLORS[cohort]
            for _, patient in selected.groupby('patient_key', sort=True):
                patient = patient.sort_values('day')
                counts.trajectory(ax, patient, y_scale=y_scale, color=color, size=30, alpha=.8)
            handles.append(Line2D([], [], color=color, marker='o', label=f'{cohort.title()}: {selected.patient_key.nunique()} patients; {len(selected)} measurements'))
        ticks = range(baseline_day_max, overlay_max_day + 1)
        ax.set_xticks(ticks, [f'Diagnostic\n(day ≤{baseline_day_max})' if d == baseline_day_max else f'D{d}' for d in ticks])
        ax.set(xlim=(baseline_day_max-.3, overlay_max_day+.3),
               title=f'Blast counts by cohort — diagnostic baseline to day {overlay_max_day}',
               xlabel='Diagnostic baseline, then recorded treatment day', ylabel='Blast count (×10⁹/L)')
        counts.count_axis(ax, y_scale=y_scale)
        ax.grid(axis='y', alpha=.18)
        ax.legend(handles=handles, frameon=False)
        fig.text(.5, .015, note, ha='center', fontsize=9)
        fig.tight_layout(rect=(0, .13, 1, 1))
        from analysis.figure_layout import legends_below
        legends_below(fig)
        fig.savefig(output / 'blast_cohort_overlay.pdf', bbox_inches='tight')
        counts.reporting.save(fig, output / 'blast_cohort_overlay.png')
    return summary
