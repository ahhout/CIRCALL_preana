"""Read-only, unnormalized source cells shared by harmonized sample workflows."""
from dataclasses import dataclass
from pathlib import Path
import warnings

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter


@dataclass(frozen=True)
class SourceCell:
    coordinate: str
    row: int
    column: int
    raw: object
    value: object
    data_type: str
    cached_type: str
    number_format: str
    formula: str | None


@dataclass
class SourceSheet:
    name: str
    headers: list
    rows: list


class SourceReadError(ValueError):
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def read_sheet(path, sheet):
    """Retain ordered columns (including duplicates), formulas and cached types.

    Library exception text is deliberately not propagated: it can contain data.
    Formula-only rows remain inspectable; formatting-only rows are ignored.
    """
    path = Path(path)
    if not path.is_file():
        raise SourceReadError('file_unavailable')
    raw = cached = None
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', UserWarning)
            raw = load_workbook(path, read_only=True, data_only=False)
            cached = load_workbook(path, read_only=True, data_only=True)
            if sheet not in raw.sheetnames:
                raise SourceReadError('sheet_missing')
            result = []
            headers = []
            for row_number, (r, c) in enumerate(zip(raw[sheet].iter_rows(), cached[sheet].iter_rows()), 1):
                cells = [SourceCell(f'{get_column_letter(i)}{row_number}', row_number, i,
                                    a.value, b.value, a.data_type, b.data_type,
                                    a.number_format, a.value if a.data_type == 'f' else None)
                         for i, (a, b) in enumerate(zip(r, c), 1)]
                if row_number == 1:
                    headers = cells
                elif any(a.raw is not None for a in cells):
                    result.append(cells)
            return SourceSheet(sheet, headers, result)
    except SourceReadError:
        raise
    except Exception:
        raise SourceReadError('file_unreadable') from None
    finally:
        for book in (raw, cached):
            if book is not None:
                book.close()
