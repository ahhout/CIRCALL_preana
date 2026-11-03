"""Exact-date sample-volume figures; no date jitter or fitted trajectories."""
from datetime import date

from ..calendar_volumes import FIELD, calendar_points


def calendar_figure(rows, coverage):
    """One exact-date sample point, including zero volume; no jitter or trend line."""
    import matplotlib.pyplot as plt
    from matplotlib.dates import AutoDateLocator, ConciseDateFormatter
    from matplotlib.lines import Line2D
    from analysis.plot_style import COHORT_COLORS, COHORT_MARKERS, COHORT_LABELS, style_axes

    from analysis.plot_style import scatter_points, point_handles
    fig, ax = plt.subplots(figsize=(10, 5.8))
    points = calendar_points(rows)
    cohort = coverage['cohort']
    color, marker = COHORT_COLORS[cohort], COHORT_MARKERS[cohort]
    if points:
        dated = sorted((row for row in rows if row['measurements'][FIELD]['value'] is not None
                        and row.get('collection_date', {}).get('value') is not None),
                       key=lambda row:(date.fromisoformat(row['collection_date']['value']),
                                       row['measurements'][FIELD]['value'], row['subject_key']))
        scatter_points(ax, [point[0] for point in points], [point[1] for point in points], cohort,
                   [row.get('center','unknown') for row in dated], circall_only=cohort=='circall',
                   s=35, alpha=.7, edgecolors='white',
                   linewidths=.4, zorder=3)
        locator = AutoDateLocator(minticks=3, maxticks=8, interval_multiples=True)
        ax.xaxis.set_major_locator(locator)
        ax.xaxis.set_major_formatter(ConciseDateFormatter(locator))
        ax.margins(x=.03)
        ax.set_ylim(0, max(point[1] for point in points)*1.1 if any(point[1] > 0 for point in points) else 1)
    else:
        ax.set_xticks([])
        ax.set_ylim(0, 1)
        ax.text(.5, .5, 'No dated, numeric volume measurements', transform=ax.transAxes, ha='center')
    specimen = coverage['specimen']
    ax.set_ylabel(f'Available {specimen} volume (mL)')
    ax.set_xlabel('Calendar collection date')
    style_axes(ax)
    label = f"{COHORT_LABELS[cohort]}: n={coverage['plotted_samples']} samples; P={coverage['plotted_participants']} participants"
    handle = Line2D([], [], linestyle='', color=color, marker=marker, label=label)
    missing = (f"Excluded: volume unavailable={coverage['unavailable_volume_samples']}; "
               f"numeric volume without collection date={coverage['numeric_volume_without_date']}")
    handles = point_handles(cohort, [r.get('center','unknown') for r in rows],
                            circall_only=cohort=='circall', label=label)
    from analysis.figure_layout import legend_footer
    legend = fig.legend(handles=handles, title=label if cohort=='circall' else None,
                        loc='lower center', frameon=False)
    legend_footer(fig, legend, missing)
    return fig

