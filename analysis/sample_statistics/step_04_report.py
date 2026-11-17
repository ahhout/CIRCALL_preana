"""Excel 2021 workbooks and compatibility imports for Layer 2 figures."""
from .report_records import inventory_records, display_order
from .workbook_sections import worksheet_sections, cell_value, status_text
from .workbook_validation import validate_workbook

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.table import Table, TableStyleInfo
from openpyxl.utils import get_column_letter
from .figures import grant_figure, figures


WRAPPED_TOP = Alignment(wrap_text=True, vertical='top')
HEADER_FONT = Font(bold=True, color='FFFFFF')
HEADER_FILL = PatternFill('solid', fgColor='174B59')
HEADER_ALIGNMENT = Alignment(wrap_text=True, vertical='center')


def report_sheet(book, name, result, note):
    ws = book.create_sheet(name)
    ws.cell(1, 1, f'{result["scope"].upper()} · {name}')
    ws.cell(1, 1).font = Font(size=18, bold=True, color='174B59')
    ws.cell(2, 1, status_text(result))
    ws.cell(3, 1, note)
    ws.cell(3, 1).alignment = WRAPPED_TOP
    ws.row_dimensions[3].height = 32
    ws.freeze_panes = 'C6'
    ws.sheet_view.showGridLines = True
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_setup.orientation = 'landscape'
    ws.page_setup.paperSize = ws.PAPERSIZE_A3
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.print_title_rows = '1:5'
    return ws


def section(ws, block, start):
    title, hidden = block.title, block.hidden
    if title:
        ws.cell(start, 1, title).font = Font(size=13, bold=True, color='174B59')
        start += 1
    records = block.rows()
    headers = block.headers()
    for column, header in enumerate(headers, 1):
        cell = ws.cell(start, column, header)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = HEADER_ALIGNMENT
        letter = get_column_letter(column)
        ws.column_dimensions[letter].width = 32 if header in ('Measurement', 'Issue', 'Patient') else 60 if header in ('Reason', 'description', 'value') else 22 if header == 'Timepoint' else 20 if header in ('Specimen', 'DNA label', 'Unit') else 16
        if header in hidden:
            ws.column_dimensions[letter].hidden = True
    ws.row_dimensions[start].height = 30
    for row_index, record in enumerate(records, start + 1):
        for column, header in enumerate(headers, 1):
            value = cell_value(record.get(header))
            cell = ws.cell(row_index, column, value)
            if isinstance(value, str):
                cell.data_type = 's'
            cell.alignment = WRAPPED_TOP
            if isinstance(value, float):
                cell.number_format = '0.0%' if header == 'Receipt rate' else '0.###'
        ws.row_dimensions[row_index].height = 30
    table_name = f'{ws.title.replace(" ", "_")}_{len(ws.tables) + 1}'
    block = Table(displayName=table_name, ref=f'A{start}:{get_column_letter(len(headers))}{start + len(records)}')
    block.tableStyleInfo = TableStyleInfo(name='TableStyleMedium2', showRowStripes=True)
    ws.add_table(block)
    ws.print_area = f'A1:{get_column_letter(len(headers))}{start + len(records)}'
    return start + len(records) + 3


def build_workbook(result, d):
    book = Workbook()
    book.remove(book.active)
    for name, note, sections in worksheet_sections(result, d):
        if name == 'Reference':
            ws = book.create_sheet(name)
            ws.sheet_state = 'hidden'
            ws.sheet_view.showGridLines = True
        else:
            ws = report_sheet(book, name, result, note)
        start = 5
        for block in sections:
            start = section(ws, block, start)
        records = sections[0].records
        if name == 'Inventory' and result['status'] == 'complete' and records:
            rate_column = list(records[0]).index('Receipt rate') + 1
            for i, record in enumerate(records, 6):
                if record['Receipt rate'] is not None:
                    ws.cell(i, rate_column).number_format = '0.0%'
            for cell in ws[6]:
                cell.font = Font(bold=True, color='174B59')
        if name == 'Comparisons':
            for row in ws.iter_rows(min_row=6) if records else []:
                for index in (11,12):
                    row[index-1].number_format='0.00E+00'
    for sheet in book:
        if sheet.title == 'Reference':
            continue
        last_visible = max(column for column in range(1, sheet.max_column + 1)
                           if not sheet.column_dimensions[get_column_letter(column)].hidden)
        for row in (1, 2, 3):
            if last_visible > 1:
                sheet.merge_cells(start_row=row, start_column=1, end_row=row, end_column=last_visible)
        sheet.row_dimensions[1].height = 30
        sheet.row_dimensions[2].height = 24
        sheet.row_dimensions[3].height = 42
        sheet.print_area = f'A1:{get_column_letter(last_visible)}{sheet.max_row}'
    if 'Controls' in book:
        book['Controls'].freeze_panes = 'C7'
    book.active = 0
    if result['scope'] == 'circall':
        from .workbook_french import localize_workbook
        localize_workbook(book)
    return book


def workbook(path, result, d):
    book = build_workbook(result, d)
    try:
        book.save(path)
    finally:
        book.close()
