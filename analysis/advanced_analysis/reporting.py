"""Aggregate Excel reports and original-unit semilog clinical figures."""
from analysis.figure_layout import remove_plot_text
import json
from pathlib import Path
import textwrap

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.cbook import boxplot_stats
from matplotlib.ticker import FuncFormatter
import numpy as np
import pandas as pd
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill

from analysis.figure_layout import legends_below
from analysis.plot_style import COHORT_COLORS, COHORT_MARKERS, COHORT_LABELS, BOX_STYLE, INK, style_axes, save_figure
from .statistics import pairs
from .schema import outcome_frame, predictors

COLORS = COHORT_COLORS
SHEETS = ['Summary', 'Coverage', 'Associations', 'Descriptions', 'Diagnostics', 'Definitions']


def report_tables(result, definitions):
    summary = [dict(metric='scope', value=result['scope']), dict(metric='status', value=result['status']),
               dict(metric='population', value='Diagnosis patients; controls integrity only'),
               dict(metric='interpretation', value='Observational; no covariate adjustment or causal interpretation')]
    summary += [dict(metric=k, value=v) for k, v in result['summary'].items()]
    summary += [dict(metric='blocking_reason', value=b['reason']) for b in result['blocking']]
    config = definitions['cohorts']
    scopes = list(config) if result['scope'] == 'pooled' else [result['scope']]
    rules = [dict(section='version', field='definition_version', definition=definitions['definition_version'])]
    rules += [dict(section='rules', field=k, definition=v) for k, v in definitions['rules'].items()]
    rules += [dict(section='outcome', field=k, definition=v['label'], unit=v['unit'], transform=v['transform'])
              for k, v in definitions['outcomes'].items()]
    for scope in scopes:
        for outcome, switches in definitions['comparisons'][scope].items():
            rules.extend(dict(section=scope, field=f'{outcome} vs {variable}', enabled=enabled)
                         for variable, enabled in switches.items())
        for variable, sources in config[scope]['sources'].items():
            rules.append(dict(section=scope, field=variable, definition=', '.join(sources) or 'Unavailable',
                              aggregation=config[scope]['aggregation'][variable], unit=definitions['units'][variable]))
    return {'Summary': summary, **result['tables'], 'Definitions': rules}


def workbook(path, result, definitions):
    book = Workbook()
    book.remove(book.active)
    for name, rows in report_tables(result, definitions).items():
        sheet = book.create_sheet(name)
        headers = list(dict.fromkeys(k for row in rows for k in row)) or ['status', 'reason']
        sheet.append(headers)
        for row in rows:
            sheet.append([json.dumps(row.get(h), ensure_ascii=False) if isinstance(row.get(h), (list, dict)) else row.get(h) for h in headers])
        # Literal source category labels must never become Excel formulas.
        for row in sheet.iter_rows():
            for cell in row:
                if isinstance(cell.value, str):
                    cell.data_type = 's'
                cell.alignment = Alignment(vertical='top', wrap_text=True)
                if isinstance(cell.value, float):
                    cell.number_format = '0.0000' if 'p_value' in str(headers[cell.column-1]) or 'p_adj' in str(headers[cell.column-1]) else '0.###'
        for cell in sheet[1]:
            cell.font = Font(bold=True, color='FFFFFF')
            cell.fill = PatternFill('solid', fgColor='24576E')
        sheet.freeze_panes = 'A2'
        sheet.auto_filter.ref = sheet.dimensions
        sheet.sheet_view.showGridLines = False
        for column in sheet.columns:
            sheet.column_dimensions[column[0].column_letter].width = min(65, max(16, max(len(str(c.value or '')) for c in column)+2))
        for i in range(2, sheet.max_row+1):
            sheet.row_dimensions[i].height = 45 if name in ('Summary', 'Definitions', 'Diagnostics') else 32
        sheet.sheet_properties.pageSetUpPr.fitToPage = True
        sheet.page_setup.orientation = 'landscape'
        sheet.page_setup.paperSize = sheet.PAPERSIZE_A3
        sheet.page_setup.fitToWidth = 1
        sheet.page_setup.fitToHeight = 0
        sheet.print_title_rows = '1:1'
    book.save(path)


def validate_workbook(path, result, definitions):
    book = load_workbook(path, read_only=True, data_only=False)
    try:
        if book.sheetnames != SHEETS:
            raise ValueError('Layer 3 workbook tabs differ')
        for name, rows in report_tables(result, definitions).items():
            actual = list(book[name].values)
            headers = list(actual[0])
            expected = [tuple(json.dumps(row.get(h), ensure_ascii=False) if isinstance(row.get(h), (list, dict)) else row.get(h) for h in headers) for row in rows]
            if len(actual)-1 != len(expected):
                raise ValueError('Layer 3 workbook row counts differ')
            for a, b in zip(actual[1:], expected, strict=True):
                for x, y in zip(a, b, strict=True):
                    if isinstance(y, float) and x is not None:
                        if not np.isclose(x, y, rtol=1e-12, atol=1e-14):
                            raise ValueError('Layer 3 workbook numbers differ')
                    elif (None if x == '' else x) != (None if y == '' else y):
                        raise ValueError('Layer 3 workbook values differ')
            if any(c.data_type == 'f' for row in book[name] for c in row):
                raise ValueError('Published workbook must contain literal aggregate results')
    finally:
        book.close()


def figure(frame, predictor, model, coverage, association, scope, args, definitions, *, outcome='cfdna_ng_per_ml_plasma'):
    from analysis.plot_style import scatter_points, point_handles
    data = pairs(frame, predictor)
    centers = lambda part: part['center'].fillna('unknown') if 'center' in part else ['unknown']*len(part)
    if not len(data) or coverage['status'] != 'available':
        return None
    log_x = predictor.variable in definitions['rules']['log_x_predictors']
    displayed = data.loc[data[predictor.variable].gt(0)] if log_x else data
    category_n = data[predictor.variable].nunique() if predictor.kind == 'categorical' else 0
    fig, ax = plt.subplots(figsize=(8.4 if predictor.kind == 'continuous' else max(10, category_n*1.1), 6))
    if predictor.kind == 'continuous':
        for cohort, group in data.groupby('cohort', sort=True):
            points = group.loc[group[predictor.variable].gt(0)] if log_x else group
            scatter_points(ax, points[predictor.variable], points.cfdna_ng_per_ml, cohort, centers(points),
                       circall_only=scope=='circall',
                       edgecolor='white', linewidths=.5, alpha=.8, s=38, zorder=3,
                       label=COHORT_LABELS[cohort] if scope == 'pooled' else f'{COHORT_LABELS[cohort]} patients (n={len(group)})')
        if displayed[predictor.variable].nunique() > 1:
            grid = (np.geomspace if log_x else np.linspace)(displayed[predictor.variable].min(), displayed[predictor.variable].max(), 200)
            if model is not None:
                inference = model.get_robustcov_results(cov_type='HC3') if predictor.robust_se else model
                prediction = inference.get_prediction(pd.DataFrame({predictor.variable: grid})).summary_frame(alpha=.05)
                with np.errstate(over='ignore'):
                    mean, low, high = [np.power(10., prediction[c].to_numpy()) for c in ('mean', 'mean_ci_lower', 'mean_ci_upper')]
                usable = np.isfinite(low) & np.isfinite(high) & (low > 0)
                ax.plot(grid, mean, color=INK, linewidth=2, label='Fitted single-predictor association')
                if usable.any():
                    ax.fill_between(grid, low, high, where=usable, color='#8795A1', alpha=.18, label='Ordinary 95% confidence interval')
            elif len(data) >= 2:
                slope, intercept = np.polyfit(data[predictor.variable], data.log10_cfDNA, 1)
                ax.plot(grid, np.power(10., intercept+slope*grid), color=INK, linewidth=2, label='Descriptive linear trend on log10 scale')
    else:
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
    if scope == 'circall' and predictor.kind == 'categorical':
        ax.get_legend().set_title(f'CIRCALL patients (n={len(data)})')
    if scope == 'pooled' and predictor.kind == 'continuous':
        ax.text(.02, .98, f'n={len(data)}', transform=ax.transAxes, ha='left', va='top')
    label = predictor.label
    if predictor.variable == 'gb_per_l':
        label = 'Maximum diagnosis blood WBC (×10⁹/L)' if coverage['unit'] == 'x10^9/L' else 'Maximum diagnosis blood WBC (source units unconfirmed)'
    spec = definitions['outcomes'][outcome]
    ax.set(xlabel=label, ylabel=f"{spec['label']} ({spec['unit']})", yscale='log')
    if log_x:
        ax.set_xscale('log')
        ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f'{v:g}'))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f'{v:g}'))
    title = f"{spec['label']} versus {label}"
    subtitle = f'Plasma · Diagnosis patient samples · {scope.capitalize()} · Analysis patients n={len(data)}'
    fig.suptitle(textwrap.fill(title,85,break_long_words=False), fontsize=15, color=INK)
    ax.set_title(subtitle, fontsize=10, pad=12)
    notes = []
    if log_x and len(displayed) < len(data):
        display_label = {'gb_per_l': 'WBC', 'tumor_fraction_percent': 'marrow blast percentages'}.get(predictor.variable, predictor.label)
        notes.append(f'Nonpositive {display_label} omitted from log display: {len(data)-len(displayed)}; retained in tables/models; no pseudocount')
        if displayed.empty:
            ax.text(.5, .5, f'No positive {display_label} values for logarithmic display', transform=ax.transAxes, ha='center')
    if coverage['nonpositive_pairs']:
        notes.append(f"Nonpositive selected sample outcomes excluded from log display/models: {coverage['nonpositive_pairs']}; no pseudocount")
    if association and association['status'] != 'fit':
        notes.append('Fit unavailable: '+association['reason'])
    if association and association['status'] == 'fit':
        notes.append(f"Unadjusted {'categorical omnibus' if predictor.kind == 'categorical' else 'regression'} p={association['p_value']:.3g}; no multiplicity correction")
    if association and association.get('spearman_status') == 'computed':
        notes.append(f"Secondary unadjusted Spearman: ρ={association['spearman_rho']:.3f}, p={association['spearman_p_value']:.3g}")
    if predictor.kind == 'categorical':
        notes.append('Boxes calculated on log10(outcome), back-transformed for display')
    if predictor.variable == 'elution_volume_ul' and outcome != 'cfdna_fraction':
        notes.append('Elution volume enters the outcome calculation; association includes arithmetic dependence')
    if scope == 'pooled':
        notes.append('Descriptive only; no pooled inference')
    if notes:
        fig.text(.5, -.01, '\n'.join(textwrap.fill(note,110,break_long_words=False) for note in notes), ha='center', va='top', fontsize=9,color='#52616B')
    style_axes(ax)
    if predictor.kind == 'continuous':
        handles, labels = ax.get_legend_handles_labels()
        unique = dict(zip(labels, handles))
        ax.legend(unique.values(), unique.keys(), frameon=False,
                  title=f'CIRCALL patients (n={len(data)})' if scope=='circall' else None)
    remove_plot_text(fig)
    fig.tight_layout()
    legends_below(fig)
    return fig


def figures(destination, frame, result, models, args, definitions):
    available = {p.variable: p for p in predictors(definitions)}
    for coverage in result['tables']['Coverage']:
        outcome = coverage['outcome']
        p = available[coverage['predictor']]
        association = next((r for r in result['tables']['Associations']
                            if r['predictor'] == p.variable and r['outcome'] == outcome), None)
        data = outcome_frame(frame, outcome)
        fig = figure(data, p, models.get(f'{outcome}/{p.variable}'), coverage, association,
                     result['scope'], args, definitions, outcome=outcome)
        if fig is None:
            continue
        folder = Path(destination)/outcome/p.output_name
        folder.mkdir(parents=True)
        try:
            for ext in (('png', 'pdf') if getattr(args, 'pdf_output', True) else ('png',)):
                save_figure(fig,folder/f'{outcome}_vs_{p.variable}.{ext}')
        finally:
            plt.close(fig)
