"""Descriptive CIRCALL blast and WBC trajectories in recorded count units."""
from analysis.figure_layout import remove_plot_text
import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path

import pandas as pd
from matplotlib.lines import Line2D

from analysis.sample_analysis import reporting
from analysis.sample_analysis.preparation import read_sheet, subject_key, text

plt = reporting.plt
FIELDS = {'blast': 'blast_count_x10*9/L', 'wbc': 'wbc_count_x10*9/L'}
LABELS = {'blast': 'Blast', 'wbc': 'WBC'}
OVERLAY_COLORS = {'blast': reporting.COLORS['circall'], 'wbc': '#4E79A7'}
MISSING = {'', 'na', 'n/a', 'none'}


def number(value, coordinate):
    if text(value).casefold() in MISSING:
        return None
    try:
        result = float(text(value).replace(',', '.'))
    except ValueError:
        raise ValueError(f'Non-numeric measurement at {coordinate}; review source entry') from None
    if isinstance(value, bool) or not math.isfinite(result) or result < 0:
        raise ValueError(f'Expected a finite nonnegative count at {coordinate}')
    return result


def observations(path):
    records = []
    for sheet, field in FIELDS.items():
        _, rows, _ = read_sheet(path, sheet, {'circall_id', 'day', field})
        seen = set()
        for row in rows:
            cell = row.cells[field]
            value = number(cell.value, f'{sheet}!{cell.coordinate}')
            if value is None and cell.formula:
                raise ValueError(f'Missing cached count at {sheet}!{cell.coordinate}; recalculate workbook in Excel')
            key = subject_key('circall', row.value('circall_id'))
            if key is None:
                raise ValueError(f'Missing patient identifier at {sheet} row {row.number}')
            day = None
            if value is not None:
                raw_day = row.value('day')
                try:
                    day = float(raw_day)
                except (TypeError, ValueError):
                    raise ValueError(f'Missing or invalid day at {sheet} row {row.number}') from None
                if isinstance(raw_day, bool) or not math.isfinite(day) or not day.is_integer():
                    raise ValueError(f'Expected an integer day at {sheet} row {row.number}')
                day = int(day)
                if (key, day) in seen:
                    raise ValueError(f'Repeated patient/day at {sheet} row {row.number}; no measurements combined')
                seen.add((key, day))
            records.append({'measurement': sheet, 'patient_key': key, 'day': day,
                            'count_x10_9_per_L': value,
                            'status': 'missing' if value is None else 'measured',
                            'source_sheet': sheet, 'source_row': row.number,
                            'source_count_cell': cell.coordinate,
                            'source_day_cell': row.cells['day'].coordinate})
    if not records:
        raise ValueError('No count records in blast or wbc sheets')
    frame = pd.DataFrame(records)
    for sheet in FIELDS:
        if frame.loc[frame.measurement.eq(sheet) & frame.status.eq('measured')].empty:
            raise ValueError(f'No measured counts in {sheet}')
    return frame


def summary_table(frame, measurements=FIELDS):
    records = []
    for sheet in measurements:
        group = frame.loc[frame.measurement.eq(sheet)]
        measured = group.loc[group.status.eq('measured')]
        plotted = group.loc[group.selected_for_plot] if 'selected_for_plot' in group else measured
        records.append({'measurement': sheet, 'source_rows': len(group),
                        'patients_in_sheet': group.patient_key.nunique(),
                        'patients_with_measurements': measured.patient_key.nunique(),
                        'measurements': len(measured), 'missing_counts': int(group.status.eq('missing').sum()),
                        'plotted_measurements': len(plotted), 'earlier_diagnostic_measurements_not_plotted': len(measured) - len(plotted),
                        'zero_counts': int(measured.count_x10_9_per_L.eq(0).sum()),
                        'first_day': int(measured.day.min()), 'last_day': int(measured.day.max())})
    return pd.DataFrame(records)


def assign_baseline(frame, *, baseline_day_max, baseline_selection='latest'):
    """Keep recorded days in the export while aligning diagnostic points for display."""
    frame = frame.copy()
    frame['diagnostic_baseline'] = frame.status.eq('measured') & frame.day.le(baseline_day_max)
    frame['display_day'] = frame.day.mask(frame.diagnostic_baseline, baseline_day_max)
    frame['selected_for_plot'] = frame.status.eq('measured')
    frame['plot_exclusion_reason'] = frame.status.map({'missing': 'missing count', 'measured': ''})
    if baseline_selection not in {'latest', 'all'}:
        raise ValueError('baseline_selection must be latest or all')
    if baseline_selection == 'latest':
        baseline = frame.loc[frame.diagnostic_baseline]
        latest = baseline.groupby(['measurement', 'patient_key']).day.transform('max')
        excluded = baseline.index[baseline.day.lt(latest)]
        frame.loc[excluded, 'selected_for_plot'] = False
        frame.loc[excluded, 'plot_exclusion_reason'] = 'earlier diagnostic measurement; latest day selected'
    return frame


def trajectory(ax, patient, *, y_scale, color, line_color=None, marker='o', size=40, alpha=.85):
    """Break log trajectories at zeros without drawing off-axis zero markers."""
    values = patient.count_x10_9_per_L
    displayed = values.mask(values.eq(0)) if y_scale == 'log' else values
    ax.plot(patient.display_day, displayed, color=line_color or color, linewidth=.8, alpha=.35)
    ax.scatter(patient.display_day, displayed, s=size, color=color, marker=marker, alpha=alpha, zorder=3)


def count_axis(ax, *, y_scale):
    if y_scale == 'log':
        ax.relim()  # Only count trajectories affect limits.
        reporting.format_log_yaxis(ax, nonpositive='mask')
        if not math.isfinite(ax.dataLim.minposy):
            ax.set_ylim(1, 10)
            ax.text(.5, .5, 'No positive counts', transform=ax.transAxes, ha='center')
        else:
            ax.autoscale_view(scalex=False, scaley=True)
        ax.set_ylabel(ax.get_ylabel() + ' — log scale')
    else:
        ax.set_ylim(bottom=-.035 * max(ax.get_ylim()[1], 1))
        ax.ticklabel_format(axis='y', style='plain', useOffset=False)


def scale_note(y_scale):
    return ('Log y-axis; zeros not displayed; lines break at zero. '
            if y_scale == 'log' else 'Linear axes; zeros retained. ') + 'Missing counts not plotted; no baseline normalisation.'


def draw(ax, frame, sheet, *, baseline_day_max, cohort='circall', blast_max_day=8, y_scale='log'):
    data = frame.loc[frame.measurement.eq(sheet) & frame.selected_for_plot]
    for _, patient in data.groupby('patient_key', sort=True):
        patient = patient.sort_values('day')
        trajectory(ax, patient, y_scale=y_scale, color=reporting.COLORS[cohort], line_color='#777777')
    label = 'CIRCALL' if cohort == 'circall' else 'Retrospective'
    ax.set(title=f'{label} {LABELS[sheet]} counts over time',
           xlabel='Diagnostic baseline, then recorded treatment day', ylabel=f'{LABELS[sheet]} count (×10⁹/L)')
    ticks = sorted({baseline_day_max, *(int(x) for x in ax.get_xticks()
                                      if baseline_day_max < x <= data.display_day.max())})
    ax.set_xticks(ticks, [f'Diagnostic\n(day ≤{baseline_day_max})' if x == baseline_day_max else f'D{x}' for x in ticks])
    if sheet == 'blast':
        ticks = range(baseline_day_max, blast_max_day + 1)
        ax.set_xticks(ticks, [f'Diagnostic\n(day ≤{baseline_day_max})' if x == baseline_day_max else f'D{x}' for x in ticks])
        ax.set_xlim(baseline_day_max - .3, blast_max_day + .3)
    count_axis(ax, y_scale=y_scale)
    ax.grid(axis='y', alpha=.18)
    ax.text(.98, .96, f'{data.patient_key.nunique()} patients; {len(data)} measurements',
            transform=ax.transAxes, ha='right', va='top', fontsize=9)


def overlay_plot(frame, output, *, baseline_day_max, baseline_selection, overlay_max_day=8, y_scale='log'):
    if overlay_max_day < baseline_day_max:
        raise ValueError('Overlay final day must be at or after the diagnostic baseline')
    fig, ax = plt.subplots(figsize=(10.5, 6.5))
    data = frame.loc[frame.selected_for_plot & frame.display_day.le(overlay_max_day)]
    handles = []
    for sheet in ('wbc', 'blast'):
        group = data.loc[data.measurement.eq(sheet)]
        color = OVERLAY_COLORS[sheet]
        marker = 'o' if sheet == 'blast' else 's'
        for _, patient in group.groupby('patient_key', sort=True):
            patient = patient.sort_values('day')
            trajectory(ax, patient, y_scale=y_scale, color=color, marker=marker)
        handles.append(Line2D([], [], color=color, marker=marker, linewidth=1,
                             label=f'{LABELS[sheet]}: {group.patient_key.nunique()} patients, {len(group)} measurements'))
    ticks = range(baseline_day_max, overlay_max_day + 1)
    ax.set_xticks(ticks, [f'Diagnostic\n(day ≤{baseline_day_max})' if x == baseline_day_max else f'D{x}' for x in ticks])
    ax.set_xlim(baseline_day_max - .3, overlay_max_day + .3)
    ax.set(title=f'CIRCALL blast and WBC counts — diagnostic baseline to day {overlay_max_day}', ylabel='Cell count (×10⁹/L)',
           xlabel='Diagnostic baseline, then recorded treatment day')
    count_axis(ax, y_scale=y_scale)
    ax.grid(axis='y', alpha=.18)
    ax.legend(handles=handles[::-1], frameon=False, loc='upper right')
    note = ('Points: recorded counts; coloured lines connect measurements from the same patient.\n'
            + scale_note(y_scale) + '\n'
            + ('Diagnostic repeats: latest recorded day selected.' if baseline_selection == 'latest'
               else 'All diagnostic measurements retained.'))
    fig.text(.5, .015, note, ha='center', fontsize=9)
    fig.tight_layout(rect=(0, .11, 1, 1))
    from analysis.figure_layout import legends_below
    remove_plot_text(fig)
    legends_below(fig)
    fig.savefig(output / 'circall_blast_wbc_overlay.pdf', bbox_inches='tight')
    reporting.save(fig, output / 'circall_blast_wbc_overlay.png')


def plots(frame, output, *, baseline_day_max, baseline_selection, overlay_max_day=8, y_scale='log'):
    note = ('Dots: recorded counts; grey lines connect measurements from the same patient.\n'
            + scale_note(y_scale) + '\n'
            + ('Diagnostic repeats: latest recorded day selected.' if baseline_selection == 'latest'
               else 'All diagnostic measurements retained.'))
    for sheet in FIELDS:
        fig, ax = plt.subplots(figsize=(10.5, 6.5))
        draw(ax, frame, sheet, baseline_day_max=baseline_day_max, blast_max_day=overlay_max_day, y_scale=y_scale)
        fig.text(.5, .015, note, ha='center', fontsize=9)
        fig.tight_layout(rect=(0, .11, 1, 1))
        reporting.save(fig, output / f'circall_{sheet}_trajectories.png')
    fig, axes = plt.subplots(1, 2, figsize=(14, 6))
    for ax, sheet in zip(axes, FIELDS):
        draw(ax, frame, sheet, baseline_day_max=baseline_day_max, blast_max_day=overlay_max_day, y_scale=y_scale)
    fig.text(.5, .015, note + '\nPanels show different recorded day ranges.', ha='center', fontsize=9)
    fig.tight_layout(rect=(0, .15, 1, 1))
    from analysis.figure_layout import legends_below
    remove_plot_text(fig)
    legends_below(fig)
    fig.savefig(output / 'circall_blast_wbc_trajectories.pdf', bbox_inches='tight')
    reporting.save(fig, output / 'circall_blast_wbc_trajectories.png')
    overlay_plot(frame, output, baseline_day_max=baseline_day_max, baseline_selection=baseline_selection,
                 overlay_max_day=overlay_max_day, y_scale=y_scale)


def run(path, output, *, baseline_day_max, baseline_selection='latest', overlay_max_day=8,
        retrospective_path=None, retrospective_unit=None, y_scale='log'):
    if y_scale not in {'linear', 'log'}:
        raise ValueError('y_scale must be linear or log')
    path, output = Path(path) if path is not None else None, Path(output)
    if output.exists():
        raise ValueError(f'Output directory already exists: {output}; choose a new directory')
    if overlay_max_day < baseline_day_max:
        raise ValueError('Overlay final day must be at or after the diagnostic baseline')
    retro = None
    if retrospective_path is not None:
        from . import retrospective_blasts
        retro = assign_baseline(retrospective_blasts.observations(retrospective_path, unit=retrospective_unit),
                                baseline_day_max=baseline_day_max, baseline_selection=baseline_selection)
    if path is None:
        if retro is None:
            raise ValueError('Select at least one blood-count source')
        output.mkdir(parents=True)
        return retrospective_blasts.write_results(retro, None, retrospective_path, output, unit=retrospective_unit,
                baseline_day_max=baseline_day_max, baseline_selection=baseline_selection, overlay_max_day=overlay_max_day, y_scale=y_scale)
    frame = assign_baseline(observations(path), baseline_day_max=baseline_day_max,
                            baseline_selection=baseline_selection)
    summary = summary_table(frame)
    output.mkdir(parents=True)
    reporting.table(output / 'circall_blood_count_observations.csv', frame)
    reporting.table(output / 'circall_blood_count_summary.csv', summary)
    settings = {'source_file': str(path.resolve()), 'source_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                'columns': FIELDS, 'units': 'x10^9/L', 'y_scale': y_scale,
                'overlay_colors': OVERLAY_COLORS,
                'overlay_max_day': overlay_max_day,
                'overlay_day_filter_scope': 'Overlay filtering and blast trajectory x-axis limit; observation tables retain all days',
                'overlay_lines': 'Within-patient trajectories; no fitted population trend',
                'day_source': 'Workbook day column preserved; treatment start is day 1',
                'diagnostic_baseline_day_max': baseline_day_max,
                'diagnostic_baseline_selection': baseline_selection,
                'baseline_display': 'Days at or below baseline_day_max displayed at the diagnostic position',
                'normalization': None, 'filtering_thresholds': None,
                'zero_counts': 'Recorded zeros retained in data and summaries; not displayed on log axes; lines break at zero', 'missing_counts': 'retained in table; not plotted',
                'day_for_missing_counts': 'not used, including formula artifacts from blank dates',
                'patient_identifiers': 'hashed; names and raw IDs not exported',
                'duplicate_patient_days': 'fail; no aggregation', 'statistical_tests': None}
    (output / 'plot_settings.json').write_text(json.dumps(settings, indent=2) + '\n')
    plots(frame, output, baseline_day_max=baseline_day_max, baseline_selection=baseline_selection,
          overlay_max_day=overlay_max_day, y_scale=y_scale)
    if retro is not None:
        summary = retrospective_blasts.write_results(retro, frame, retrospective_path, output, unit=retrospective_unit,
                baseline_day_max=baseline_day_max, baseline_selection=baseline_selection, overlay_max_day=overlay_max_day, y_scale=y_scale)
    log = '\n'.join(f'{r.measurement}: {r.measurements} measurements, {r.plotted_measurements} plotted in {r.patients_with_measurements} patients; '
                    f'{r.zero_counts} zeros; {r.missing_counts} missing counts; days {r.first_day} to {r.last_day}'
                    for r in summary.itertuples())
    (output / 'run.log').write_text(log + f'\nDiagnostic: day <= {baseline_day_max}; selection: {baseline_selection}; scale: {y_scale}; units: x10^9/L; no normalization.\n')
    print(log)
    print(f'Output: {output.resolve()}')
    return summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, required=True, help='Workbook containing blast and wbc sheets')
    parser.add_argument('--baseline-day-max', type=int, required=True, help='Recorded days at or below this value are diagnostic baseline')
    parser.add_argument('--baseline-selection', choices=['latest', 'all'], default='latest',
                        help='Use latest diagnostic measurement (default) or retain all')
    parser.add_argument('--kinetics-y-scale', choices=['linear', 'log'], default='log')
    parser.add_argument('--overlay-max-day', type=int, default=8, help='Final day shown in overlays and blast trajectory axes (default: 8)')
    parser.add_argument('--output-dir', type=Path, help='New output directory; existing directories are refused')
    args = parser.parse_args(argv)
    output = args.output_dir or Path('output') / datetime.now(timezone.utc).strftime('run_%Y-%m-%d_%H-%M-%S.%f_UTC_blood_counts')
    try:
        run(args.input, output, baseline_day_max=args.baseline_day_max, baseline_selection=args.baseline_selection,
            overlay_max_day=args.overlay_max_day, y_scale=args.kinetics_y_scale)
    except ValueError as exc:
        parser.error(str(exc))


if __name__ == '__main__':
    main()
