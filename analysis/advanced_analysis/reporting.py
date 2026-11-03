"""Aggregate Excel reports and coordination of internal association figures."""
import json
from pathlib import Path

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill

from analysis.plot_style import COHORT_COLORS, save_figure
from .figures import figure
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
