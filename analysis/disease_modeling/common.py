"""Versioned definitions and source-cell interpretation for Layer 4 only."""
from datetime import date, datetime
import hashlib
import json
import math
from pathlib import Path
import re

import numpy as np

from analysis.provenance import ROOT
from analysis.sample_io import read_sheet


def load_definitions(path):
    def unique(pairs):
        obj = {}
        for key, value in pairs:
            if key in obj:
                raise ValueError('Duplicate definition key')
            obj[key] = value
        return obj
    try:
        d = json.loads(Path(path).read_text(), object_pairs_hook=unique)
        expected = json.loads((ROOT/'configs/definitions/disease_modeling.json').read_text())
        if d != expected:
            raise ValueError()
        return d
    except (ValueError, OSError, TypeError):
        raise ValueError('Unsupported disease-tracking definitions') from None


def token(value):
    return '' if value is None else str(value).strip().casefold()


def cell_state(cell, d):
    if cell is None:
        return 'field_unavailable'
    if cell.data_type == 'e' or cell.cached_type == 'e':
        return 'invalid'
    if cell.formula and cell.value is None:
        return 'intentional_empty' if cell.cached_type == 'str' else 'cache_unavailable'
    if token(cell.value) in d['unknown_tokens']:
        return 'unknown'
    if token(cell.value) in d['missing_tokens']:
        return 'missing'
    return 'available'


def identity(cell, cohort, family, d):
    if cell_state(cell, d) != 'available' or cell.formula or isinstance(cell.value, (bool, date, datetime)):
        return None
    value = str(cell.value).strip()
    if cohort == 'circall' and not re.fullmatch(r'\d{3}-\d{4}-[A-Za-z]-[A-Za-z]', value):
        return None
    return hashlib.sha256((family+'\0'+cohort+'\0'+value).encode()).hexdigest()


class ClinicalError(ValueError):
    """Safe issue locations, never raw source values or identity strings."""
    def __init__(self, reason, **location):
        self.finding = dict(reason=reason, **location)
        super().__init__(reason)


def source_rows(path, sheet, required):
    data = read_sheet(path, sheet)
    headers = [c.value for c in data.headers]
    if any(headers.count(h) > 1 for h in headers if h is not None):
        raise ClinicalError('duplicate_header', sheet=sheet)
    for field in required:
        if headers.count(field) != 1:
            raise ClinicalError('missing_header', sheet=sheet, field=field)
    return [{h: c for h, c in zip(headers, cells) if h is not None} for cells in data.rows]


def clean(value):
    if isinstance(value, dict):
        return {k: clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value
