"""Aggregate Excel reports and compatibility imports for disease figures."""
import json

import numpy as np
from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill

from .figures import save, mrd_figure, mrd_status_figure, count_figure, figures

TABS = ('Summary', 'Coverage', 'MRD', 'Counts', 'Models', 'Diagnostics', 'Definitions')


def report_tables(result, d, settings):
    return dict(Summary=[dict(metric='scope', value=result['scope']), dict(metric='status', value=result['status']),
                         *[dict(metric=k, value=v) for k, v in result['summary'].items()],
                         *[dict(metric='blocking_reason', value=b['reason'], analysis=b.get('analysis'),
                                sheet=b.get('sheet'), cell=b.get('cell'), visit=b.get('visit'),
                                occurrences=b.get('occurrences', len(b.get('cells', [])) or None),
                                cell_references=', '.join(b.get('cells', [])) if len(b.get('cells', [])) < 10 else None)
                           for b in result['blocking']]],
                **result['tables'], Definitions=[dict(section='definition', field=k, value=v) for k, v in d.items()]
                + [dict(section='resolved setting', field=k, value=v) for k, v in settings.items()
                   if k not in ('inventory', 'circall', 'donors', 'blood_counts', 'retrospective_blasts', 'rules', 'definitions', 'workflow')])


def workbook(path, result, d, settings):
    book = Workbook()
    book.remove(book.active)
    for name, rows in report_tables(result, d, settings).items():
        sheet = book.create_sheet(name)
        headers = list(dict.fromkeys(k for row in rows for k in row)) or ['status', 'reason']
        sheet.append(headers)
        for row in rows:
            sheet.append([json.dumps(row.get(h), ensure_ascii=False, sort_keys=True) if isinstance(row.get(h), (list, dict)) else row.get(h) for h in headers])
        for row in sheet:
            for cell in row:
                if isinstance(cell.value, str):
                    cell.data_type = 's'
                if isinstance(cell.value, float):
                    cell.number_format = '0.000000E+00' if 0 < abs(cell.value) < 1e-4 else '0.######'
                cell.alignment = Alignment(wrap_text=True, vertical='top')
        for cell in sheet[1]:
            cell.font = Font(bold=True, color='FFFFFF')
            cell.fill = PatternFill('solid', fgColor='24576E')
        for column in sheet.columns:
            sheet.column_dimensions[column[0].column_letter].width = min(70, max(16, max(len(str(c.value or '')) for c in column)+2))
        for i in range(2, sheet.max_row+1):
            if name == 'Definitions':
                lines = max((len(str(c.value or ''))//max(1, int(sheet.column_dimensions[c.column_letter].width)-3)+1 for c in sheet[i]), default=1)
                sheet.row_dimensions[i].height = min(409, max(34, lines*15))
            else:
                sheet.row_dimensions[i].height = 34
        sheet.freeze_panes = 'A2'
        sheet.auto_filter.ref = sheet.dimensions
        sheet.sheet_view.showGridLines = False
        sheet.page_setup.orientation = 'landscape'
        sheet.page_setup.paperSize = sheet.PAPERSIZE_A3
        sheet.page_setup.fitToWidth = 1
        sheet.page_setup.fitToHeight = 0
        sheet.print_title_rows = '1:1'
    book.save(path)


def validate_workbook(path, result, d, settings):
    book = load_workbook(path, read_only=True, data_only=False)
    try:
        if book.sheetnames != list(TABS):
            raise ValueError('Disease workbook tabs differ')
        for name, rows in report_tables(result, d, settings).items():
            actual = list(book[name].values)
            headers = actual[0]
            if len(actual)-1 != len(rows):
                raise ValueError('Disease workbook row counts differ')
            for exported, row in zip(actual[1:], rows, strict=True):
                for value, h in zip(exported, headers, strict=True):
                    expected = row.get(h)
                    if isinstance(expected, (list, dict)):
                        expected = json.dumps(expected, ensure_ascii=False, sort_keys=True)
                    if isinstance(expected, float) and value is not None:
                        if not np.isclose(value, expected, rtol=1e-12, atol=1e-14):
                            raise ValueError('Disease workbook numeric mismatch')
                    elif (None if value == '' else value) != (None if expected == '' else expected):
                        raise ValueError('Disease workbook value mismatch')
            if any(c.data_type == 'f' for row in book[name] for c in row):
                raise ValueError('Unexpected formula in aggregate workbook')
    finally:
        book.close()
