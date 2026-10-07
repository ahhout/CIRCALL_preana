"""Aggregate Excel reports and original-unit semilog clinical figures."""
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

from analysis import association_methods as engine
from analysis.figure_layout import legends_below
from .statistics import pairs

COLORS = {'retrospective': '#4C78A8', 'circall': '#F58518'}
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
    for scope in scopes:
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


def figure(frame, predictor, model, coverage, association, scope, args, definitions):
    data = pairs(frame, predictor)
    if not len(data) or coverage['status'] != 'available':
        return None
    log_x = predictor.variable in ('gb_per_l', 'tumor_fraction_percent')
    displayed = data.loc[data[predictor.variable].gt(0)] if log_x else data
    category_n = data[predictor.variable].nunique() if predictor.kind == 'categorical' else 0
    fig, ax = plt.subplots(figsize=(8.4 if predictor.kind == 'continuous' else max(10, category_n*1.1), 6))
    if predictor.kind == 'continuous':
        for cohort, group in data.groupby('cohort', sort=True):
            points = group.loc[group[predictor.variable].gt(0)] if log_x else group
            ax.scatter(points[predictor.variable], points.cfdna_ng_per_ml, color=COLORS[cohort], edgecolor='white', alpha=.85,
                       label=f'{cohort.capitalize()} patients (n={len(group)})')
        if displayed[predictor.variable].nunique() > 1:
            grid = (np.geomspace if log_x else np.linspace)(displayed[predictor.variable].min(), displayed[predictor.variable].max(), 200)
            if model is not None:
                inference = model.get_robustcov_results(cov_type='HC3') if predictor.robust_se else model
                prediction = inference.get_prediction(pd.DataFrame({predictor.variable: grid})).summary_frame(alpha=.05)
                with np.errstate(over='ignore'):
                    mean, low, high = [np.power(10., prediction[c].to_numpy()) for c in ('mean', 'mean_ci_lower', 'mean_ci_upper')]
                usable = np.isfinite(low) & np.isfinite(high) & (low > 0)
                ax.plot(grid, mean, color='#b33b2e', label='Fitted single-predictor association')
                if usable.any():
                    ax.fill_between(grid, low, high, where=usable, color='#b33b2e', alpha=.15, label='Ordinary 95% confidence interval')
            elif len(data) >= 2:
                slope, intercept = np.polyfit(data[predictor.variable], data.log10_cfDNA, 1)
                ax.plot(grid, np.power(10., intercept+slope*grid), color='#b33b2e', label='Descriptive linear trend on log10 scale')
    else:
        rng = np.random.default_rng(definitions['rules']['jitter_seed'])
        categories = sorted(data[predictor.variable].astype(str).unique())
        for pos, category in enumerate(categories, 1):
            group = data.loc[data[predictor.variable].astype(str).eq(category)]
            # Compute the historical boxes on log10 values, then change coordinates.
            box = boxplot_stats(group.log10_cfDNA.to_numpy())[0]
            for key in ('mean', 'med', 'q1', 'q3', 'whislo', 'whishi', 'cilo', 'cihi', 'fliers'):
                box[key] = np.power(10., box[key])
            ax.bxp([box], positions=[pos], widths=.55, showfliers=False)
            for cohort, part in group.groupby('cohort', sort=True):
                ax.scatter(pos+rng.normal(0, .045, len(part)), part.cfdna_ng_per_ml, color=COLORS[cohort], edgecolor='white', alpha=.85)
        ax.set_xticks(range(1, len(categories)+1), ['\n'.join(textwrap.wrap(c, width=18, break_long_words=False))+f'\n(n={int(data[predictor.variable].astype(str).eq(c).sum())})' for c in categories])
        ax.tick_params(axis='x', labelsize=9, rotation=30)
        from matplotlib.lines import Line2D
        ax.legend(handles=[Line2D([], [], marker='o', linestyle='', color=COLORS[c], label=f'{c.capitalize()} patients (n={len(g)})') for c, g in data.groupby('cohort', sort=True)])
    label = predictor.label
    if predictor.variable == 'gb_per_l':
        label = 'Peripheral blood WBC count (×10⁹/L)' if coverage['unit'] == 'x10^9/L' else 'Peripheral blood WBC count (source units unconfirmed)'
    ax.set(xlabel=label, ylabel='cfDNA concentration (ng/mL plasma)', yscale='log')
    if log_x:
        ax.set_xscale('log')
        ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f'{v:g}'))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f'{v:g}'))
    title = f'cfDNA versus {label}'
    subtitle = f'Plasma · Diagnosis patient samples · {scope.capitalize()} · Analysis patients n={len(data)}'
    fig.suptitle(title, fontsize=13)
    ax.set_title(subtitle, fontsize=10, pad=12)
    notes = []
    if log_x and len(displayed) < len(data):
        display_label = 'WBC' if predictor.variable == 'gb_per_l' else 'marrow blast percentages'
        notes.append(f'Nonpositive {display_label} omitted from log display: {len(data)-len(displayed)}; retained in tables/models; no pseudocount')
        if displayed.empty:
            ax.text(.5, .5, f'No positive {display_label} values for logarithmic display', transform=ax.transAxes, ha='center')
    if coverage['nonpositive_pairs']:
        notes.append(f"Nonpositive patient medians excluded from log display/models: {coverage['nonpositive_pairs']}; no pseudocount")
    if association and association['status'] != 'fit':
        notes.append('Fit unavailable: '+association['reason'])
    if association and association['status'] == 'fit':
        notes.append(f"Primary regression p={association['p_value']:.3g}; BH p={association['p_adj_bh']:.3g}")
    if association and association.get('spearman_status') == 'computed':
        notes.append(f"Secondary unadjusted Spearman: ρ={association['spearman_rho']:.3f}, p={association['spearman_p_value']:.3g}")
    if predictor.kind == 'categorical':
        notes.append('Boxes calculated on log10(cfDNA), back-transformed for display')
    if scope == 'pooled':
        notes.append('Descriptive only; no pooled inference')
    if notes:
        fig.text(.5, -.01, '\n'.join(notes), ha='center', va='top', fontsize=9)
    ax.grid(alpha=.2)
    if predictor.kind == 'continuous':
        ax.legend(frameon=False)
    fig.tight_layout()
    legends_below(fig)
    return fig


def figures(destination, frame, result, models, args, definitions):
    for p in engine.PREDICTORS:
        coverage = next(r for r in result['tables']['Coverage'] if r['predictor'] == p.variable)
        association = next((r for r in result['tables']['Associations'] if r['predictor'] == p.variable), None)
        fig = figure(frame, p, models.get(p.variable), coverage, association, result['scope'], args, definitions)
        if fig is None:
            continue
        folder = Path(destination)/p.output_name
        folder.mkdir(parents=True)
        try:
            for ext in ('png', 'pdf'):
                fig.savefig(folder/f'cfDNA_ng_per_mL_vs_{p.variable}.{ext}', dpi=200, bbox_inches='tight')
        finally:
            plt.close(fig)
