"""Aggregate Excel and disease figures; no clinical row export paths."""
from analysis.figure_layout import remove_plot_text
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import FuncFormatter
import numpy as np
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill

from analysis.figure_layout import legends_below
from .common import clean

TABS = ('Summary', 'Coverage', 'MRD', 'Counts', 'Models', 'Diagnostics', 'Definitions')


def report_tables(result, d, settings):
    return dict(Summary=[dict(metric='scope', value=result['scope']), dict(metric='status', value=result['status']),
                         *[dict(metric=k, value=v) for k, v in result['summary'].items()],
                         *[dict(metric='blocking_reason', value=b['reason'], analysis=b.get('analysis'),
                                sheet=b.get('sheet'), cell=b.get('cell'), visit=b.get('visit'),
                                occurrences=b.get('occurrences', len(b.get('cells', [])) or None),
                                cell_references=', '.join(b.get('cells', [])) if len(b.get('cells', [])) < 10 else None)
                           for b in result['blocking']]],
                **result['tables'], Definitions=[dict(section='definition', field=k, value=v) for k, v in d.items()]
                + [dict(section='resolved setting', field=k, value=v) for k, v in settings.items()
                   if k not in ('inventory', 'circall', 'donors', 'blood_counts', 'retrospective_blasts', 'rules', 'definitions', 'workflow')])


def workbook(path, result, d, settings):
    book = Workbook()
    book.remove(book.active)
    for name, rows in report_tables(result, d, settings).items():
        sheet = book.create_sheet(name)
        headers = list(dict.fromkeys(k for row in rows for k in row)) or ['status', 'reason']
        sheet.append(headers)
        for row in rows:
            sheet.append([json.dumps(row.get(h), ensure_ascii=False, sort_keys=True) if isinstance(row.get(h), (list, dict)) else row.get(h) for h in headers])
        for row in sheet:
            for cell in row:
                if isinstance(cell.value, str):
                    cell.data_type = 's'
                if isinstance(cell.value, float):
                    cell.number_format = '0.000000E+00' if 0 < abs(cell.value) < 1e-4 else '0.######'
                cell.alignment = Alignment(wrap_text=True, vertical='top')
        for cell in sheet[1]:
            cell.font = Font(bold=True, color='FFFFFF')
            cell.fill = PatternFill('solid', fgColor='24576E')
        for column in sheet.columns:
            sheet.column_dimensions[column[0].column_letter].width = min(70, max(16, max(len(str(c.value or '')) for c in column)+2))
        for i in range(2, sheet.max_row+1):
            if name == 'Definitions':
                lines = max((len(str(c.value or ''))//max(1, int(sheet.column_dimensions[c.column_letter].width)-3)+1 for c in sheet[i]), default=1)
                sheet.row_dimensions[i].height = min(409, max(34, lines*15))
            else:
                sheet.row_dimensions[i].height = 34
        sheet.freeze_panes = 'A2'
        sheet.auto_filter.ref = sheet.dimensions
        sheet.sheet_view.showGridLines = False
        sheet.page_setup.orientation = 'landscape'
        sheet.page_setup.paperSize = sheet.PAPERSIZE_A3
        sheet.page_setup.fitToWidth = 1
        sheet.page_setup.fitToHeight = 0
        sheet.print_title_rows = '1:1'
    book.save(path)


def validate_workbook(path, result, d, settings):
    book = load_workbook(path, read_only=True, data_only=False)
    try:
        if book.sheetnames != list(TABS):
            raise ValueError('Disease workbook tabs differ')
        for name, rows in report_tables(result, d, settings).items():
            actual = list(book[name].values)
            headers = actual[0]
            if len(actual)-1 != len(rows):
                raise ValueError('Disease workbook row counts differ')
            for exported, row in zip(actual[1:], rows, strict=True):
                for value, h in zip(exported, headers, strict=True):
                    expected = row.get(h)
                    if isinstance(expected, (list, dict)):
                        expected = json.dumps(expected, ensure_ascii=False, sort_keys=True)
                    if isinstance(expected, float) and value is not None:
                        if not np.isclose(value, expected, rtol=1e-12, atol=1e-14):
                            raise ValueError('Disease workbook numeric mismatch')
                    elif (None if value == '' else value) != (None if expected == '' else expected):
                        raise ValueError('Disease workbook value mismatch')
            if any(c.data_type == 'f' for row in book[name] for c in row):
                raise ValueError('Unexpected formula in aggregate workbook')
    finally:
        book.close()


def save(fig, destination, pdf_output=True):
    from analysis.plot_style import save_figure
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    remove_plot_text(fig)
    fig.tight_layout()
    legends_below(fig)
    try:
        for ext in (('png', 'pdf') if pdf_output else ('png',)):
            remove_plot_text(fig)
            save_figure(fig, destination.with_suffix('.'+ext), dpi=200)
    finally:
        plt.close(fig)


def mrd_figure(records, scope, args, d):
    if not any(r['status'] not in ('missing', 'normalized_baseline') for r in records):
        return None
    from analysis.plot_style import CENTER_MARKERS, COHORT_COLORS, point_handles
    pooled = scope == 'pooled'
    colors = d['colors'] if pooled else {**d['colors'], **COHORT_COLORS}
    visits = d['pooled_visits'] if pooled or scope == 'circall' else d['visits']
    levels = dict(negative=args.mrd_negative_level, unknown_significance=args.mrd_unknown_level,
                  positive_nonquantifiable=args.mrd_positive_nq_level, normalized_baseline=1.)
    positions = {v: i for i, v in enumerate(visits)}
    fig, ax = plt.subplots(figsize=(8.5, 6.3))
    rng = np.random.default_rng(args.jitter_seed)
    groups = {}
    for r in records:
        groups.setdefault((r['cohort'], r['subject_hash']), []).append(r)
    drawn = []
    for (cohort, _), group in sorted(groups.items()):
        jitter = rng.uniform(-.09, .09)
        points = []
        for r in group:
            status = r['status']
            value = r['measured_fraction']
            if status == 'positive_nonquantifiable':
                value = args.mrd_positive_nq_level if pooled else r['upper_bound_fraction']
            elif status in levels:
                value = levels[status]
            if value is None or status == 'missing':
                continue
            drawn.append(value)
            x = positions[r['visit']]+jitter
            points.append((positions[r['visit']], x, value, status))
            color = colors[cohort]
            marker = 'v' if status in ('negative', 'positive_nonquantifiable') else 'D' if status == 'unknown_significance' else 'o'
            if scope == 'circall':
                marker = CENTER_MARKERS.get(r.get('center','unknown'), 'o')
            ax.scatter(x, value, color=color, marker=marker, facecolors='none' if status in ('positive_nonquantifiable', 'unknown_significance') else color,
                       edgecolors=color, alpha=.75, s=34)
        points.sort()
        for first, second in zip(points, points[1:]):
            if second[0]-first[0] != 1:
                continue
            if scope == 'retrospective' and (first[3] != 'quantified' or second[3] != 'quantified'):
                continue
            if 'positive_nonquantifiable' in (first[3], second[3]):
                continue
            assigned = any(s in ('negative', 'unknown_significance') for s in (first[3], second[3]))
            ax.plot([first[1], second[1]], [first[2], second[2]], color=colors[cohort], alpha=.25,
                    linewidth=.7, linestyle=':' if assigned else '-')
    ax.set(yscale='log', ylabel='MRD residual clone fraction', xlabel='Nominal treatment visit',
           title=f'{scope.upper() if scope == "circall" else scope.capitalize()} MRD trajectories')
    upper = max(drawn)*3 if scope == 'retrospective' else max([*drawn, 1.])*2.5
    ax.set_ylim(min([*drawn, args.mrd_negative_level])/3, upper)
    ax.set_xticks(range(len(visits)), [f'{v}\nn={sum(r["visit"] == v and r["status"] != "missing" for r in records)}' for v in visits])
    ax.set_xlim(-.35, len(visits)-.65)
    ax.grid(axis='y', alpha=.18)
    handles = [Line2D([], [], color=colors[cohort], marker='o', linestyle='', label=(cohort.upper() if cohort == 'circall' else 'Retrospective') if pooled else f'{cohort.upper() if cohort == "circall" else "Retrospective"} (n={sum(c == cohort for c, _ in groups)})') for cohort in sorted({r['cohort'] for r in records})]
    handles += [Line2D([], [], color='#555555', marker=marker, linestyle='', markerfacecolor=face, label=label) for marker, face, label in
                [('o', '#555555', 'Quantified MRD / assumed diagnosis reference' if scope != 'retrospective' else 'Quantified MRD'),
                 ('v', '#555555', f'Negative: assigned {args.mrd_negative_level:g}'),
                 ('v', 'none', f'Positive NQ: assigned {args.mrd_positive_nq_level:g}' if pooled else
                  'Positive NQ: counted, not positioned' if scope == 'circall' else 'Positive NQ: upper bound, not a measurement')]]
    if any(r['status'] == 'unknown_significance' for r in records):
        handles.append(Line2D([], [], color='#555555', marker='D', linestyle='', markerfacecolor='none', label=f'Uncertain: assigned {args.mrd_unknown_level:g}'))
    if scope == 'circall':
        handles = point_handles('circall', [r.get('center','unknown') for r in records], circall_only=True)
        # Center owns shape; status is conveyed by assigned level and fill.
        handles += [Line2D([], [], linestyle='', color='none', label=text) for text in (
            'Filled: quantified MRD / assumed diagnosis reference',
            f'Negative: assigned {args.mrd_negative_level:g}',
            'Positive NQ: counted, not positioned',
            f'Hollow: uncertain significance, assigned {args.mrd_unknown_level:g}')]
    ax.legend(handles=handles, frameon=False, fontsize=9,
              title=f'CIRCALL: {len(groups)} patients' if scope=='circall' else None)
    unbounded = sum(r['status'] == 'positive_nonquantifiable' and r['upper_bound_fraction'] is None for r in records)
    note = 'Descriptive only. Assigned levels are not measurements or detection limits. No shared calendar days assumed.'
    if scope != 'retrospective':
        note += '\nDiagnosis = 1 is an assumed reference, not measured MRD or blast-cell percentage.'
    if scope == 'retrospective':
        note += f'\nUnbounded positive NQ counted, not positioned: {unbounded}. Lines connect quantified pairs only.'
    else:
        note += '\nMissing visits and positive NQ are not connected; dotted lines touch other assigned levels.'
        if scope == 'circall':
            note += f'\nPositive NQ counted, not positioned: {unbounded}. Reported sensitivity is not measured MRD.'
    fig.text(.5, -.01, note, ha='center', va='top', fontsize=8)
    remove_plot_text(fig)
    return fig


def mrd_status_figure(rows, d):
    fig, ax = plt.subplots(figsize=(8.4, 6))
    bottom = np.zeros(len(rows))
    for group in d['mrd']['pooled_status_display_groups']:
        counts = np.array([sum(r[s] for s in group['statuses']) for r in rows])
        percentages = np.array([100*c/r['patients'] if r['patients'] else 0 for c, r in zip(counts, rows, strict=True)])
        ax.bar(range(len(rows)), percentages, bottom=bottom, color=group['color'], label=group['label'], edgecolor='white')
        for pos, (height, count) in enumerate(zip(percentages, counts, strict=True)):
            if height >= 5:
                ax.text(pos, bottom[pos]+height/2, f'{height:.1f}%\n(n={count})', ha='center', va='center', fontsize=9)
        bottom += percentages
    ax.set_xticks(range(len(rows)), [f'{r["visit"]}\nN={r["patients"]}' for r in rows])
    ax.set(ylim=(0, 100), ylabel='Patients (%) — fixed MRD population', title='Pooled MRD status')
    ax.legend(frameon=False)
    fig.text(.5, -.01, 'Diagnosis is an assumed disease-positive reference. Missing results are hidden; fixed denominators retained.\n'
             'Display groups combine statuses; the workbook retains all clinical categories and missing counts.',
             ha='center', va='top', fontsize=8)
    remove_plot_text(fig)
    return fig


def count_figure(records, measurement, args, d, *, early=False, comparison=False):
    data = [r for r in records if r['measurement'] == measurement and r['selected_for_plot']
            and (not early or r['display_day'] <= args.overlay_max_day)]
    if not data:
        return None
    fig, ax = plt.subplots(figsize=(10, 6))
    from analysis.plot_style import CENTER_MARKERS, COHORT_COLORS, point_handles
    circall_only = not comparison and {r['cohort'] for r in data} == {'circall'}
    colors = d['colors'] if comparison else {**d['colors'], **COHORT_COLORS}
    handles = []
    for cohort in sorted({r['cohort'] for r in data}):
        selected = [r for r in data if r['cohort'] == cohort]
        groups = {}
        for r in selected:
            groups.setdefault(r['subject_hash'], []).append(r)
        for group in groups.values():
            ordered = sorted(group, key=lambda r: r['day'])
            x = [r['display_day'] for r in ordered]
            y = [r['value'] if r['value'] > 0 or args.kinetics_y_scale == 'linear' else np.nan for r in ordered]
            ax.plot(x, y, color=colors[cohort], alpha=.3, linewidth=.8)
            marker = CENTER_MARKERS.get(group[0].get('center','unknown'), 'o') if circall_only else 'o'
            ax.scatter(x, y, color=colors[cohort], marker=marker, s=24, alpha=.8)
        handles.append(Line2D([], [], color=colors[cohort], marker='o', label=f'{cohort.upper() if cohort == "circall" else "Retrospective"}: {len(groups)} patients; {len(selected)} measurements'))
    if circall_only:
        handles = point_handles('circall', [r.get('center','unknown') for r in data], circall_only=True)
    scope = 'Cohort comparison' if comparison else data[0]['cohort'].upper() if data[0]['cohort'] == 'circall' else 'Retrospective'
    window = f'Diagnostic baseline through day {args.overlay_max_day}' if early else 'Full recorded range'
    ax.set(title=f'{scope} {"blast" if measurement == "blast" else "WBC"} counts · {window}',
           xlabel='Diagnostic display baseline, then recorded treatment day', ylabel='Blast count (×10⁹/L)' if measurement == 'blast' else 'WBC count (×10⁹/L)')
    if args.kinetics_y_scale == 'log':
        ax.set_yscale('log')
        ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f'{v:g}'))
        if not any(r['value'] > 0 for r in data):
            ax.set_ylim(1, 10)
            ax.text(.5, .5, 'No positive counts for logarithmic display', transform=ax.transAxes, ha='center')
    else:
        ax.set_ylim(bottom=0)
    if early:
        ticks = list(range(args.baseline_day_max, args.overlay_max_day+1))
        ax.set_xticks(ticks, [f'Diagnostic\n(day ≤{v})' if v == args.baseline_day_max else f'D{v}' for v in ticks])
        ax.set_xlim(args.baseline_day_max-.3, args.overlay_max_day+.3)
    else:
        # NaN y values deliberately hide zeros on a log axis, but must not hide
        # their recorded time range. Set x limits independently of positive y.
        last_day = max(r['display_day'] for r in data)
        span = max(1, last_day-args.baseline_day_max)
        ax.set_xlim(args.baseline_day_max-.03*span, last_day+.03*span)
        from matplotlib.ticker import MaxNLocator
        candidates = MaxNLocator(nbins=7, integer=True).tick_values(args.baseline_day_max, last_day)
        gap = max(1, span/8)
        ticks = sorted({args.baseline_day_max, *(int(v) for v in candidates if args.baseline_day_max+gap <= v <= last_day)})
        ax.set_xticks(ticks, [f'Diagnostic\n(day ≤{v})' if v == args.baseline_day_max else f'D{v}' for v in ticks])
    ax.grid(alpha=.18)
    ax.legend(handles=handles, frameon=False,
              title=f'CIRCALL: {len({r["subject_hash"] for r in data})} patients; {len(data)} measurements' if circall_only else None)
    zero_n = sum(r['value'] == 0 for r in data)
    note = f'Recorded counts; no normalization or inference. Diagnostic repeats: {args.baseline_selection}.\n'
    note += f'Log display: zeros omitted ({zero_n}); lines break at zero; no pseudocount.' if args.kinetics_y_scale == 'log' else f'Linear display: zeros retained ({zero_n}).'
    if comparison:
        note += '\nCohorts remain separate; no pooled count population or fit.'
    fig.text(.5, -.01, note, ha='center', va='top', fontsize=8)
    remove_plot_text(fig)
    return fig


def figures(destination, scope, prepared, result, args, d):
    destination = Path(destination)
    fig = mrd_figure(prepared['mrd'], scope, args, d)
    if fig is not None:
        save(fig, destination/'mrd'/'mrd_trajectories', pdf_output=getattr(args, 'pdf_output', True))
    if scope == 'pooled':
        if prepared['mrd']:
            save(mrd_status_figure(result['tables']['MRD'], d), destination/'mrd'/'mrd_status', pdf_output=getattr(args, 'pdf_output', True))
        return
    for measurement in d['counts'][scope]['sheets']:
        for early in (False, True):
            fig = count_figure(prepared['counts'], measurement, args, d, early=early)
            if fig is not None:
                save(fig, destination/'blood_counts'/f'{measurement}_{"early_window" if early else "full_range"}', pdf_output=getattr(args, 'pdf_output', True))
