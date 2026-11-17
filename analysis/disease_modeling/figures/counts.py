"""Recorded blood-count trajectories with established windows and zero handling."""
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import FuncFormatter
import numpy as np

from analysis.utils.figure_layout import remove_plot_text


def count_figure(records, measurement, args, d, *, early=False, comparison=False):
    data = [r for r in records if r['measurement'] == measurement and r['selected_for_plot']
            and (not early or r['display_day'] <= args.overlay_max_day)]
    if not data:
        return None
    fig, ax = plt.subplots(figsize=(10, 6))
    from analysis.utils.plot_style import CENTER_MARKERS, COHORT_COLORS, point_handles
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

