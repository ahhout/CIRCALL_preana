"""Categorical associations with original log-scale boxes and seeded jitter."""
import textwrap

import numpy as np
from matplotlib.cbook import boxplot_stats

from analysis.utils.plot_style import COHORT_LABELS, BOX_STYLE, scatter_points, point_handles


def draw_categorical(ax, data, predictor, scope, definitions):
    centers = lambda part: part['center'].fillna('unknown') if 'center' in part else ['unknown']*len(part)
    rng = np.random.default_rng(definitions['rules']['jitter_seed'])
    categories = sorted(data[predictor.variable].astype(str).unique())
    for pos, category in enumerate(categories, 1):
        group = data.loc[data[predictor.variable].astype(str).eq(category)]
        # Compute the historical boxes on log10 values, then change coordinates.
        box = boxplot_stats(group.log10_cfDNA.to_numpy())[0]
        for key in ('mean', 'med', 'q1', 'q3', 'whislo', 'whishi', 'cilo', 'cihi', 'fliers'):
            box[key] = np.power(10., box[key])
        ax.bxp([box], positions=[pos], widths=.55, showfliers=False, **BOX_STYLE)
        for cohort, part in group.groupby('cohort', sort=True):
            scatter_points(ax, pos+rng.normal(0, .045, len(part)), part.cfdna_ng_per_ml, cohort, centers(part),
                       circall_only=scope=='circall',
                       edgecolor='white', linewidths=.5, alpha=.8, s=38, zorder=3)
    ax.set_xticks(range(1, len(categories)+1), ['\n'.join(textwrap.wrap(c, width=18, break_long_words=False))+f'\n(n={int(data[predictor.variable].astype(str).eq(c).sum())})' for c in categories])
    ax.tick_params(axis='x', labelsize=9, rotation=30)
    from matplotlib.lines import Line2D
    ax.legend(handles=[h for c,g in data.groupby('cohort',sort=True)
                       for h in point_handles(c,centers(g),circall_only=scope=='circall',
                       label=COHORT_LABELS[c] if scope=='pooled' else f'{COHORT_LABELS[c]} patients (n={len(g)})')],frameon=False)
