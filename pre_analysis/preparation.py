"""Explicit Excel ingestion, numeric conversion, and measurement-level QC."""
from dataclasses import dataclass
import hashlib
import math
from pathlib import Path
import re
import warnings

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

RTOL = 1e-9
ATOL = 1e-12
MISSING = {'', 'na', 'n/a', 'nan', 'none', '-', 'sk'}
MEASUREMENTS = (
    'volume_ml', 'elution_volume_uL', 'dna_concentration_ng_per_uL',
    'dna_total_ng', 'dna_ng_per_mL_plasma', 'cfDNA_fraction',
    'cfDNA_total_ng', 'cfDNA_ng_per_mL_plasma', 'cfDNA_concentration_ng_per_uL',
    'cfDNA_avg_size_bp', 'blood_volume_ml', 'mnc_tube_count_million',
    'mnc_aliquot_count_million', 'mnc_vario_ng_per_uL', 'mnc_vario_total_ng',
    'mnc_albumin_ng_per_uL', 'mnc_DIN',
)


def text(value):
    if value is None:
        return ''
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).replace('\u00a0', ' ').strip()


def numeric(value):
    """CIRCALL semantics: decimal commas accepted; no stripping units/qualifiers."""
    if isinstance(value, bool) or text(value).casefold() in MISSING:
        return None
    try:
        result = float(text(value).replace(',', '.'))
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def present(value):
    return text(value).casefold() not in MISSING


def subject_key(source, value):
    if not present(value):
        return None
    # Keeps legacy within-cohort grouping without emitting names.
    digest = hashlib.sha256(text(value).lower().encode()).hexdigest()[:24]
    return f'{source}:{digest}'


@dataclass
class Cell:
    value: object = None
    formula: str | None = None
    coordinate: str = ''
    number_format: str = 'General'


@dataclass
class SourceRow:
    number: int
    cells: dict

    def value(self, column):
        return self.cells.get(column, Cell()).value


def read_sheet(path, sheet, required):
    """Read values plus formulas. Source workbooks are never recalculated/saved."""
    path = Path(path)
    if not path.is_file():
        raise ValueError(f'Workbook not found: {path}')
    with warnings.catch_warnings():
        warnings.filterwarnings('ignore', message='Data Validation extension is not supported')
        values = load_workbook(path, read_only=True, data_only=True)
        try:
            formulas = load_workbook(path, read_only=True, data_only=False)
            try:
                selected = sheet or values.sheetnames[0]
                if selected not in values.sheetnames:
                    raise ValueError(f'Missing required sheet {selected} in {path.name}')
                ws, fs = values[selected], formulas[selected]
                headers = [text(c.value) for c in next(ws.iter_rows(), [])]
                nonempty = [h for h in headers if h]
                if len(nonempty) != len(set(nonempty)):
                    raise ValueError(f'Duplicate column headers in {path.name}/{selected}')
                missing = set(required) - set(headers)
                if missing:
                    raise ValueError(f'Missing columns in {path.name}/{selected}: {", ".join(sorted(missing))}')
                result = []
                for row_number, (cached, raw) in enumerate(zip(ws.iter_rows(min_row=2), fs.iter_rows(min_row=2)), 2):
                    cells = {
                        h: Cell(c.value, f.value if f.data_type == 'f' else None, f"{get_column_letter(index)}{row_number}", c.number_format)
                        for index, (h, c, f) in enumerate(zip(headers, cached, raw), 1) if h
                    }
                    if any(c.value is not None or c.formula for c in cells.values()):
                        result.append(SourceRow(row_number, cells))
                return selected, result, headers
            finally:
                formulas.close()
        finally:
            values.close()


def mapped_measurements(row, mapping):
    """Return numeric values, missingness reasons and safe source-cell provenance."""
    values, reasons, raw = {}, {}, {}
    for target, source in mapping.items():
        cell = row.cells.get(source, Cell())
        value = numeric(cell.value)
        reasons[target] = '' if value is not None else (
            'field_unavailable' if source not in row.cells else
            'excel_error' if text(cell.value).startswith('#') else
            'missing' if text(cell.value).casefold() in MISSING else 'nonnumeric'
        )
        values[target] = value
        raw[target] = {'column': source, 'cell': cell.coordinate, 'value': cell.value,
                       'formula': cell.formula, 'number_format': cell.number_format}
    return values, reasons, raw


def validate_measurements(values, reasons, raw, *, compartment, supplied_endpoint=False):
    values, reasons = dict(values), dict(reasons)
    issues = []
    # Follow missingness through known derived quantities. A literal measured zero
    # is not discarded just because a validation component is unavailable.
    for output, operands in (
        ('dna_total_ng', ('dna_concentration_ng_per_uL', 'elution_volume_uL')),
        ('cfDNA_total_ng', ('dna_total_ng', 'cfDNA_fraction')),
        ('cfDNA_concentration_ng_per_uL', ('dna_concentration_ng_per_uL', 'cfDNA_fraction')),
    ):
        if values.get(output) == 0 and raw.get(output, {}).get('formula') and any(values.get(k) is None for k in operands):
            values[output] = None
            reasons[output] = 'formula_zero_missing_inputs'
    total = values.get('dna_total_ng')
    conc = values.get('dna_concentration_ng_per_uL')
    elution = values.get('elution_volume_uL')
    volume = values.get('volume_ml')
    recorded_endpoint = values.get('dna_ng_per_mL_plasma')
    if total is not None and conc is not None and elution is not None:
        expected = conc * elution
        if not math.isclose(total, expected, rel_tol=RTOL, abs_tol=ATOL):
            issues.append({'field': 'dna_total_ng', 'recorded': total, 'calculated': expected,
                           'reason': 'total_vs_concentration_times_elution'})
    if not supplied_endpoint:
        endpoint = total / volume if compartment == 'plasma' and total is not None and volume is not None and volume > 0 else None
        if endpoint is not None and recorded_endpoint is not None and not math.isclose(recorded_endpoint, endpoint, rel_tol=RTOL, abs_tol=ATOL):
            issues.append({'field': 'dna_ng_per_mL_plasma', 'recorded': recorded_endpoint,
                           'calculated': endpoint, 'reason': 'endpoint_vs_total_divided_volume'})
        values['dna_ng_per_mL_plasma'] = endpoint
        reasons['dna_ng_per_mL_plasma'] = '' if endpoint is not None else (
            'not_plasma' if compartment != 'plasma' else 'missing_total_or_positive_volume')
    for output, operands in (
        ('cfDNA_ng_per_mL_plasma', ('cfDNA_total_ng', 'volume_ml')),
    ):
        if values.get(output) == 0 and raw.get(output, {}).get('formula') and any(values.get(k) is None for k in operands):
            values[output] = None
            reasons[output] = 'formula_zero_missing_inputs'
    return values, reasons, issues


def retrospective_timepoint(value):
    import unicodedata
    value = unicodedata.normalize('NFKD', text(value)).lower()
    value = ''.join(c for c in value if not unicodedata.combining(c))
    value = re.sub(r'\s+', ' ', value)
    if 'diag' in value:
        return 'diag'
    if 'rechute' in value:
        return 'rechute'
    if 'inotuzumab' in value:
        return 'après inotuzumab'
    match = re.search(r'\btp\s*([0-9]+(?:[.,][0-9])?)\b', value)
    return 'tp' + match.group(1).replace('.', ',') if match else None
