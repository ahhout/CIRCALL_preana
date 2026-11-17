"""MRD trajectories preserving measured, bounded and assigned display levels."""
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np

from analysis.utils.figure_layout import remove_plot_text


def mrd_figure(records, scope, args, d):
    if not any(r['status'] not in ('missing', 'normalized_baseline') for r in records):
        return None
    from analysis.utils.plot_style import CENTER_MARKERS, COHORT_COLORS, point_handles
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

