"""Stream saved statistics cells against the report records, without rendering another book."""
from datetime import date, time, timedelta
from itertools import zip_longest
from numbers import Real

from openpyxl import load_workbook
from openpyxl.compat.strings import safe_string
from openpyxl.utils.datetime import from_excel, to_excel

from . import workbook_french as french
from .workbook_sections import worksheet_sections, cell_value, status_text


def serialized_value(value, epoch):
    """Compare against values as the locked Excel writer encodes them."""
    if isinstance(value, bool):
        return value
    if isinstance(value, Real):
        encoded = safe_string(value)
        if not encoded:
            return None
        return float(encoded) if any(c in encoded for c in '.eE') else int(encoded)
    if isinstance(value, (date, time, timedelta)):
        return from_excel(float(safe_string(to_excel(value, epoch))), epoch,
                          timedelta=isinstance(value, timedelta))
    if isinstance(value, str):
        return value[:32767] or None
    return value


def expected_rows(name, note, sections, result, translated):
    if name == 'Reference':
        yield from [()] * 4
    else:
        title = f'{result["scope"].upper()} · {name}'
        status = status_text(result)
        if translated:
            title = 'CIRCALL · ' + french.SHEETS[name]
            status = french.translate_status(status)
            note = french.NOTES[name]
        yield (title,)
        yield (status,)
        yield (note,)
        yield ()
    for index, section in enumerate(sections):
        if index:
            yield ()
            yield ()
        if section.title:
            yield (french.translate_label(section.title) if translated else section.title,)
        headers = section.headers()
        yield tuple(french.HEADERS.get(h, h) if translated else h for h in headers)
        for record in section.rows():
            values = []
            for h in headers:
                value = cell_value(record.get(h))
                if translated and isinstance(value, str) and h not in ('Patient', 'Source worksheet', 'Source row'):
                    value = french.translate_label(value)
                values.append(value)
            yield values


def validate_workbook(path, result, d):
    book = load_workbook(path, read_only=True)
    missing = object()
    try:
        sheets = worksheet_sections(result, d)
        for spec, actual in zip_longest(sheets, book, fillvalue=missing):
            if spec is missing or actual is missing:
                raise ValueError('Statistics workbook sheet count differs')
            name, note, sections = spec
            translated = result['scope'] == 'circall' and name in french.SHEETS
            expected_name = french.SHEETS[name] if translated else name
            visibility = 'hidden' if name == 'Reference' else 'visible'
            if actual.title != expected_name or actual.sheet_state != visibility:
                raise ValueError('Statistics workbook sheet metadata differs')
            width = max(len(section.headers()) for section in sections)
            rows = expected_rows(name, note, sections, result, translated)
            for row, saved in zip_longest(rows, actual.iter_rows(), fillvalue=missing):
                if row is missing or saved is missing:
                    raise ValueError('Statistics workbook row count differs')
                cells = tuple(serialized_value(v, book.epoch) for v in row)
                if any(cell.data_type == 'f' for cell in saved):
                    raise ValueError('Unexpected formula in statistics workbook')
                if cells + (None,)*(width-len(cells)) != tuple(cell.value for cell in saved):
                    raise ValueError('Statistics workbook does not reconcile with audit tables')
    finally:
        book.close()
