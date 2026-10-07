"""Descriptive pooled MRD views; patient records remain in memory."""
import json
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np
import pandas as pd

from analysis.sample_analysis import reporting

VISITS = ('Diagnosis', 'TP1', 'TP2')
LABELS = {
    'normalized_baseline': 'Disease-positive reference (assumed)',
    'quantified': 'Quantified positive',
    'positive_nonquantifiable': 'Positive nonquantifiable',
    'unknown_significance': 'Uncertain significance',
    'negative': 'Negative',
    'missing': 'Missing / no recorded result',
}
COLORS = ('#9C4242', '#D56757', '#E5AB48', '#9778AF', '#65A58C', '#D9D9D9')


def prepare(circall, retrospective):
    """Retain each source's population; complete follow-up grid for display only."""
    circall = circall.loc[circall.timepoint.ne('D1')].copy()
    circall['timepoint'] = circall.timepoint.replace({'TP1 (D29)': 'TP1', 'TP2 (D71)': 'TP2'})
    data = pd.concat([circall, retrospective], ignore_index=True)
    keys = ['cohort', 'patient_key']
    if data.duplicated([*keys, 'timepoint']).any():
        raise ValueError('Pooled MRD requires one prepared annotation per cohort/patient/visit')
    people = data[keys].drop_duplicates()
    grid = people.merge(pd.DataFrame({'timepoint': VISITS}), how='cross')
    data = grid.merge(data, on=[*keys, 'timepoint'], how='left', validate='one_to_one')
    data['status'] = data.status.fillna('missing')
    data.loc[data.timepoint.eq('Diagnosis'), 'status'] = 'normalized_baseline'
    if not set(data.status).issubset(LABELS):
        raise ValueError('Unsupported pooled MRD status')
    if 'reported_upper_bound_fraction' not in data:
        data['reported_upper_bound_fraction'] = np.nan
    return data


def summary_table(data):
    rows = []
    for scope in ('pooled', 'circall', 'retrospective'):
        selected = data if scope == 'pooled' else data.loc[data.cohort.eq(scope)]
        for visit in VISITS:
            group = selected.loc[selected.timepoint.eq(visit)]
            denominator = len(group)
            counts = group.status.value_counts()
            for status in LABELS:
                count = int(counts.get(status, 0))
                rows.append(dict(cohort=scope, timepoint=visit, status=status, patients=count,
                                 denominator=denominator, percent=100*count/denominator if denominator else np.nan))
    return pd.DataFrame(rows)


def plot_status(summary, path):
    fig, ax = plt.subplots(figsize=(8, 7))
    pooled = summary.loc[summary.cohort.eq('pooled')]
    bottom = np.zeros(3)
    small_labels = {x: [] for x in range(3)}
    display_groups = (
        (('normalized_baseline', 'quantified'), 'Quantifiable blasts', '#D56757'),
        (('positive_nonquantifiable', 'unknown_significance'), 'Pos NQ', '#E5AB48'),
        (('negative',), 'Negative', '#65A58C'),
    )
    for statuses, label, color in display_groups:
        rows = pooled.loc[pooled.status.isin(statuses)].groupby('timepoint')[['percent', 'patients']].sum().reindex(VISITS)
        heights = rows.percent.to_numpy()
        ax.bar(range(3), heights, bottom=bottom, color=color, edgecolor='white', label=label, width=.65)
        for x, (height, count) in enumerate(zip(heights, rows.patients)):
            if height >= 5:
                ax.text(x, bottom[x]+height/2, f'{height:.1f}%\n(n={count})', ha='center', va='center', fontsize=9)
            elif height > 0:
                small_labels[x].append((bottom[x]+height/2, height, count))
        bottom += heights
    for x, entries in small_labels.items():
        last_y = -5
        for center, height, count in entries:
            label_y = max(center, last_y+6, 4)
            ax.annotate(f'{height:.1f}% (n={count})', xy=(x+.325, center), xytext=(x+.37, label_y),
                        fontsize=8, va='center', arrowprops=dict(arrowstyle='-', color='#666666', lw=.6))
            last_y = label_y
    ax.set_xlim(-.5, 2.85)
    n = pooled.groupby('timepoint').denominator.first()
    ax.set_xticks(range(3), [f'{v}\nN={n[v]}' for v in VISITS])
    ax.set(ylim=(0, 100), ylabel='Patients (%) — fixed pooled denominator', title='Pooled MRD status over time')
    ax.legend(loc='upper center', bbox_to_anchor=(.5, -.14), ncol=2, frameon=False, fontsize=9)
    fig.text(.5, .015, 'Diagnosis is an assumed disease-positive reference, not a measured blast-cell percentage.\n'
             'Missing results are hidden; percentages retain the fixed pooled denominator.',
             ha='center', fontsize=8)
    ax.get_legend().set_in_layout(False)
    fig.tight_layout(rect=(0, .10, 1, 1))
    reporting.save(fig, path)


def plot_trajectories(data, path, *, unknown_level, negative_level, positive_nq_level=1e-6):
    if not 0 < positive_nq_level <= 1:
        raise ValueError('Positive NQ display fraction must be in (0, 1]')
    fig, ax = plt.subplots(figsize=(8, 7.5))
    rng = np.random.default_rng(42)
    positions = {v: i for i, v in enumerate(VISITS)}
    levels = [1., unknown_level, negative_level, positive_nq_level]
    symbols = {'normalized_baseline': 'o', 'quantified': 'o', 'negative': 'v',
               'unknown_significance': 'D', 'positive_nonquantifiable': 'v'}
    for (cohort, _), group in data.groupby(['cohort', 'patient_key'], sort=True):
        color = reporting.COLORS[cohort]
        jitter = rng.uniform(-.09, .09)
        points = []
        for row in group.itertuples():
            status = row.status
            value = {'normalized_baseline': 1., 'negative': negative_level,
                     'unknown_significance': unknown_level}.get(status, row.measured_fraction)
            if status == 'positive_nonquantifiable':
                value = positive_nq_level
            if status == 'missing' or pd.isna(value):
                continue
            x = positions[row.timepoint]+jitter
            levels.append(value)
            points.append((positions[row.timepoint], x, value, status))
            ax.scatter(x, value, marker=symbols[status], s=32, alpha=.75,
                       edgecolors=color, facecolors='none' if status in ('positive_nonquantifiable', 'unknown_significance') else color)
        points.sort()
        for a, b in zip(points[:-1], points[1:]):
            # No bridging missing visits or drawing a bound as a measured trajectory.
            if b[0]-a[0] != 1 or 'positive_nonquantifiable' in (a[3], b[3]):
                continue
            assigned = any(s in ('negative', 'unknown_significance') for s in (a[3], b[3]))
            ax.plot([a[1], b[1]], [a[2], b[2]], color=color, alpha=.22, linewidth=.7,
                    linestyle=':' if assigned else '-')
    low = min(levels)
    ax.set_yscale('log')
    ax.set_ylim(low/3, 2.5)
    ax.set_xticks(range(3), [f'{v}\nn={int(((data.timepoint == v) & (data.status != "missing")).sum())}' for v in VISITS])
    ax.set(xlim=(-.35, 2.35), ylabel='Residual clone fraction (diagnostic reference = 1)', title='Pooled MRD trajectories')
    ax.grid(axis='y', alpha=.18)
    handles = [Line2D([], [], color=color, marker='o', linestyle='', label=cohort.upper() if cohort=='circall' else cohort.title())
               for cohort, color in reporting.COLORS.items() if cohort in ('circall', 'retrospective')]
    handles += [Line2D([], [], color='#555555', marker=marker, linestyle='', markerfacecolor=face, label=label)
                for marker, face, label in [('o', '#555555', 'Quantified / diagnostic reference'),
                    ('v', 'none', f'Positive NQ: assigned {positive_nq_level:g}'),
                    ('D', 'none', f'Uncertain: assigned {unknown_level:g}'),
                    ('v', '#555555', f'Negative: assigned {negative_level:g}')]]
    ax.legend(handles=handles, loc='upper center', bbox_to_anchor=(.5, -.13), ncol=2, frameon=False, fontsize=8)
    fig.text(.5, .015, 'Diagnosis = 1 is a normalization reference, not measured MRD. No shared calendar days assumed.\n'
             f'All positive NQ results are displayed at {positive_nq_level:g}; assigned levels are not measurements.\n'
             'Missing visits and positive NQ are not connected; dotted lines touch other assigned levels.',
             ha='center', fontsize=8)
    ax.get_legend().set_in_layout(False)
    fig.tight_layout(rect=(0, .10, 1, 1))
    reporting.save(fig, path)


def run(circall, retrospective, output, *, unknown_level, negative_level, positive_nq_level=1e-6):
    data = prepare(circall, retrospective)
    output = Path(output)
    summary = summary_table(data)
    reporting.table(output/'pooled_mrd_summary.csv', summary)
    plot_trajectories(data, output/'pooled_mrd_trajectories.png', unknown_level=unknown_level, negative_level=negative_level, positive_nq_level=positive_nq_level)
    plot_status(summary, output/'pooled_mrd_status_stacked.png')
    settings = dict(scope='descriptive pooling; no cross-cohort linkage or hypothesis tests',
                    denominator='fixed union of patients retained by existing cohort-specific MRD preparation; absent visits shown as missing',
                    diagnosis='assumed disease-positive reference, normalized fraction 1; not measured blast-cell percentage',
                    categories=LABELS, unknown_display_fraction=unknown_level, negative_display_fraction=negative_level,
                    positive_nonquantifiable_display_fraction=positive_nq_level,
                    bounds='preserved in source preparation; all positive NQ shown at assigned level, not a measured value or bound',
                    row_level_export=False, jitter_seed=42,
                    limitation='cohort visit labels do not establish equivalent calendar windows; changing status is not a causal effect')
    (output/'pooled_mrd_settings.json').write_text(json.dumps(settings, indent=2)+'\n')
    return summary
