"""Calendar-date collection-volume descriptions; no fitting, pooling or imputation."""
from collections import Counter
from datetime import date, datetime


FIELD = 'extraction_input_volume_ml'


def collection_date(cell, definitions):
    """Use typed workbook dates/caches only; never infer dates from text or numbers."""
    if cell is None:
        return dict(value=None, state='field_unavailable')
    if cell.data_type == 'e' or cell.cached_type == 'e':
        return dict(value=None, state='excel_error')
    if cell.formula and cell.value is None:
        return dict(value=None, state='intentional_empty' if cell.cached_type == 'str' else 'cache_unavailable')
    value = cell.value
    if isinstance(value, datetime):
        if value.tzinfo is not None:
            return dict(value=None, state='timezone_unresolved')
        value = value.date()
    if isinstance(value, date):
        return dict(value=value.isoformat(), state='cached_date' if cell.formula else 'recorded_date')
    token = '' if value is None else str(value).strip().casefold()
    if token in definitions['unknown_tokens']:
        state = 'unknown'
    elif token in definitions['missing_tokens']:
        state = 'missing'
    else:
        state = 'not_a_recorded_date'
    return dict(value=None, state=state)


def calendar_groups(rows, definitions):
    """Keep established received-sample and specimen rules, without visit restriction."""
    metric = definitions['metrics'].get(FIELD, {})
    calendar = metric.get('calendar_plot')
    if not calendar:
        return {}
    groups = {}
    for row in rows:
        if (row.get('control', False) or row['cohort'] not in calendar['cohorts']
                or row['specimen'] not in metric['specimens']
                or row['receipt'] not in ('received', 'received_early')):
            continue
        groups.setdefault((row['cohort'], row['specimen']), []).append(row)
    return groups


def calendar_points(rows):
    points = []
    for row in rows:
        volume = row['measurements'][FIELD]['value']
        recorded = row.get('collection_date', {}).get('value')
        if volume is not None and recorded is not None:
            points.append((date.fromisoformat(recorded), volume, row['subject_key']))
    return sorted(points)


def calendar_coverage(rows, definitions):
    result = []
    for (cohort, specimen), group in sorted(calendar_groups(rows, definitions).items()):
        numeric = [row for row in group if row['measurements'][FIELD]['value'] is not None]
        points = calendar_points(group)
        states = Counter(row.get('collection_date', {}).get('state', 'field_unavailable') for row in numeric)
        result.append(dict(cohort=cohort, specimen=specimen,
                           date_field=definitions['metrics'][FIELD]['calendar_plot']['date_field'],
                           unit='mL available specimen', received_samples=len(group),
                           numeric_volume_samples=len(numeric), unavailable_volume_samples=len(group)-len(numeric),
                           numeric_volume_without_date=len(numeric)-len(points), plotted_samples=len(points),
                           plotted_participants=len({point[2] for point in points}),
                           collection_date_states=dict(sorted(states.items()))))
    return result


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


def validate_calendar_dates(rows, definitions, source):
    """Reconcile plotted/local date metadata against the selected source in memory."""
    from analysis.sample_io import read_sheet
    metric = definitions['metrics'].get(FIELD, {})
    config = metric.get('calendar_plot')
    if not config:
        return
    selected = [row for row in rows if not row.get('control', False)
                and row['cohort'] in config['cohorts'] and row['specimen'] in metric['specimens']]
    for name in sorted({row['sheet'] for row in selected}):
        sheet = read_sheet(source, name)
        headers = [cell.value for cell in sheet.headers]
        expected = {}
        for cells in sheet.rows:
            fields = {header: cell for header, cell in zip(headers, cells) if header is not None}
            expected[cells[0].row] = collection_date(fields.get(config['date_field']), definitions)
        if any(row.get('collection_date') != expected.get(row['row']) for row in selected if row['sheet'] == name):
            raise ValueError('Calendar collection dates do not reconcile with selected source')
