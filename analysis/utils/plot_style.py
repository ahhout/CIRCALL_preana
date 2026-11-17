"""Shared Layer 2/3 presentation; no observation selection or transformations."""
from functools import lru_cache

from analysis.utils.figure_layout import FONT_FAMILY, FONT_SIZE, prepare_figure

COHORT_COLORS = {'circall': '#D55E00', 'retrospective': '#0072B2'}
COHORT_MARKERS = {'circall': 'o', 'retrospective': '^'}
COHORT_LABELS = {'circall': 'CIRCALL', 'retrospective': 'Retrospective'}
INK = '#243746'
BOX_STYLE = dict(patch_artist=True, boxprops={'facecolor': '#E9EDF1', 'edgecolor': '#667585', 'linewidth': 1},
                 medianprops={'color': INK, 'linewidth': 2},
                 whiskerprops={'color': '#667585', 'linewidth': 1},
                 capprops={'color': '#667585', 'linewidth': 1})


def style_axes(ax):
    ax.set_axisbelow(True)
    ax.grid(False)
    ax.grid(axis='y', which='major', color='#DFE5EB', linewidth=.7)
    ax.spines[['top', 'right']].set_visible(False)
    for side in ('left', 'bottom'):
        ax.spines[side].set_color('#8795A1')
        ax.spines[side].set_linewidth(.7)
    ax.tick_params(axis='both', which='both', color='#8795A1', labelcolor=INK)
    for label in (ax.xaxis.label, ax.yaxis.label):
        label.set_fontsize(12)
        label.set_color(INK)
    ax.title.set_color(INK)


def save_figure(fig, path, *, dpi=300):
    """Print-quality bitmap or vector PDF with embedded TrueType fonts."""
    import matplotlib
    with matplotlib.rc_context({'pdf.fonttype': 42, 'font.family': FONT_FAMILY,
                                'font.size': FONT_SIZE, 'mathtext.fontset': 'custom',
                                'mathtext.rm': FONT_FAMILY, 'mathtext.sf': FONT_FAMILY,
                                'mathtext.it': FONT_FAMILY + ':italic',
                                'mathtext.bf': FONT_FAMILY + ':bold'}):
        prepare_figure(fig)
        fig.savefig(path, dpi=dpi, bbox_inches='tight', pad_inches=.15)


CENTER_MARKERS = {'TRS': '^', 'RDB': 's', 'unknown': 'o'}


def center_from_id(value, cohort):
    """Presentation metadata using the established Layer 2 center definition."""
    if cohort != 'circall':
        return 'RDB'
    return _center_mapping().get(str(value).strip()[:3], 'unknown')


@lru_cache(maxsize=1)
def _center_mapping():
    import json
    from pathlib import Path
    return json.loads((Path(__file__).resolve().parents[2] /
                       'configs/definitions/sample_statistics.json').read_text())['centers']


def point_handles(cohort, centers, *, circall_only=False, label=None):
    from matplotlib.lines import Line2D
    if circall_only and cohort == 'circall':
        return [Line2D([], [], linestyle='', color=COHORT_COLORS[cohort],
                       marker=CENTER_MARKERS.get(center, 'o'),
                       label=f'CIRCALL · {center if center != "unknown" else "Unknown center"}')
                for center in sorted(set(centers))]
    return [Line2D([], [], linestyle='', color=COHORT_COLORS[cohort],
                   marker=COHORT_MARKERS[cohort], label=label or COHORT_LABELS[cohort])]


def scatter_points(ax, x, y, cohort, centers, *, circall_only=False, **kwargs):
    """Split display markers only; keep original point order and coordinates."""
    import numpy as np
    x, y = np.asarray(x), np.asarray(y)
    centers = np.asarray(list(centers))
    if circall_only and cohort == 'circall':
        kwargs.pop('label', None)
        for center in sorted(set(centers)):
            selected = centers == center
            ax.scatter(x[selected], y[selected], marker=CENTER_MARKERS.get(center, 'o'),
                       color=COHORT_COLORS[cohort],
                       label=f'CIRCALL · {center if center != "unknown" else "Unknown center"}', **kwargs)
    else:
        ax.scatter(x, y, marker=COHORT_MARKERS[cohort], color=COHORT_COLORS[cohort], **kwargs)
