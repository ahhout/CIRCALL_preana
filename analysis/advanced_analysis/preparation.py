"""Harmonized diagnosis preparation; source identifiers stay in memory only."""
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re

import numpy as np
import pandas as pd

from analysis.configuration import unique_object
from analysis.data_integrity.checks import number
from analysis.sample_io import read_sheet
from analysis.provenance import ROOT
from analysis import association_methods as engine


def load_definitions(path):
    try:
        definitions = json.loads(Path(path).read_text(), object_pairs_hook=unique_object)
        expected = json.loads((ROOT/'configs/definitions/advanced_analysis.json').read_text())
        if definitions != expected:
            raise ValueError()
        return definitions
    except (ValueError, OSError, TypeError):
        raise ValueError('Unsupported Layer 3 definitions; scientific revisions require a versioned implementation') from None


def token(value):
    return '' if value is None else str(value).strip().casefold()


def present(cell, d):
    return (cell is not None and not cell.formula and cell.data_type != 'e'
            and token(cell.value) not in d['missing_tokens'] + d['unknown_tokens'])


def measurement(cell, d, *, maximum=None):
    if cell is None:
        return None, 'field_unavailable'
    if cell.data_type == 'e' or cell.cached_type == 'e':
        return None, 'invalid'
    if cell.formula and cell.value is None:
        return None, 'intentional_empty' if cell.cached_type == 'str' else 'cache_unavailable'
    value, state = number(cell.value, d['missing_tokens'], d['unknown_tokens'])
    if value is None:
        return None, 'qualified_text' if state == 'annotation' else state
    if value < 0 or (maximum is not None and value > maximum):
        return None, 'invalid'
    return value, 'zero' if value == 0 else ('numeric_text' if state == 'text' else 'numeric')


def prepare(path, cohort, d):
    config = d['cohorts'][cohort]
    sheet = read_sheet(path, config['sheet'])
    headers = [c.value for c in sheet.headers]
    issues, evidence = [], []
    counts = Counter(input_rows=len(sheet.rows), diagnosis_rows=0, eligible_plasma_samples=0,
                     excluded_not_diagnosis=0, excluded_invalid_participant_id=0,
                     excluded_outcome_specimen_or_tube=0, excluded_outcome_missing_sample_id=0)
    for state in ('numeric', 'numeric_text', 'zero', 'missing', 'unknown', 'cache_unavailable',
                  'intentional_empty', 'qualified_text', 'invalid'):
        counts['outcome_'+state] = 0
    if cohort == 'retrospective':
        counts.update(discordant_sex_patients=0, discordant_genetic_subtype_patients=0)
    for field in dict.fromkeys(h for h in headers if h is not None):
        if headers.count(field) > 1:
            issues.append(dict(reason='duplicate_header', field=field, sheet=sheet.name))
    for field in config['required']:
        if field not in headers:
            issues.append(dict(reason='missing_header', field=field, sheet=sheet.name))
    columns = ['subject_hash', 'cohort', 'cfdna_ng_per_ml', 'outcome_sample_n', 'eligible_sample_n',
               *[p.variable for p in engine.PREDICTORS], *[p.variable+'_sample_n' for p in engine.PREDICTORS]]
    if issues:
        return pd.DataFrame(columns=columns), dict(counts), evidence, issues
    patients = defaultdict(list)
    for cells in sheet.rows:
        source = {h: c for h, c in zip(headers, cells) if h is not None}
        value = lambda f: source[f].value if f in source else None
        if not any(token(value(f)) for f in ('sample_id', 'timepoint', 'specimen_type', config['identity'])):
            counts['numbering_only_rows'] += 1
            continue
        if token(value('timepoint')) != d['timepoint']:
            counts['excluded_not_diagnosis'] += 1
            continue
        counts['diagnosis_rows'] += 1
        identity = source.get(config['identity'])
        if not present(identity, d) or (cohort == 'circall' and not re.fullmatch(r'\d{3}-\d{4}-[A-Za-z]-[A-Za-z]', str(identity.value).strip())):
            counts['excluded_invalid_participant_id'] += 1
            issues.append(dict(reason='invalid_participant_id', field=config['identity'], sheet=sheet.name, row=cells[0].row))
            continue
        key = str(identity.value).strip()  # no case folding or name fallback
        hashed = hashlib.sha256((cohort+'\0'+key).encode()).hexdigest()
        filters = all(token(value(field)) == token(wanted) for field, wanted in config['outcome_filters'].items())
        received = present(source.get('sample_id'), d)
        eligible = filters and received
        counts['eligible_plasma_samples'] += int(eligible)
        if not filters:
            counts['excluded_outcome_specimen_or_tube'] += 1
        elif not received:
            counts['excluded_outcome_missing_sample_id'] += 1
        marrow = token(value('specimen_type')) == 'bone marrow'
        row = dict(subject_hash=hashed, cohort=cohort, sheet=sheet.name, row=cells[0].row,
                   eligible_outcome=eligible, marrow=marrow, measurements={})

        def numeric(field, *, maximum=None, clinical=False):
            val, state = measurement(source.get(field), d, maximum=maximum)
            cell = source.get(field)
            row['measurements'][field] = dict(value=val, state=state, cell=cell.coordinate if cell else None)
            if state == 'invalid' or (clinical and state == 'qualified_text'):
                issues.append(dict(reason='invalid_clinical_value' if clinical else 'invalid_outcome',
                                   sheet=sheet.name, row=cells[0].row, field=field, cell=cell.coordinate if cell else None))
            return val

        def category(field):
            cell = source.get(field)
            val = str(cell.value).strip() if present(cell, d) else None
            row['measurements'][field] = dict(value=val, state='recorded' if val is not None else 'unavailable',
                                            cell=cell.coordinate if cell else None)
            return val

        row['outcome'] = numeric(d['outcome']) if eligible else None
        if eligible:
            counts['outcome_'+row['measurements'][d['outcome']]['state']] += 1
        for p in engine.PREDICTORS:
            fields = config['sources'][p.variable]
            applicable = cohort == 'circall' or (eligible if p.variable in ('sex', 'age_diag', 'peripheral_blast_percent')
                                                else marrow if p.variable == 'tumor_fraction_percent' else True)
            val = None
            if fields and applicable:
                if p.kind == 'categorical':
                    val = category(fields[0])
                else:
                    # The fallback is consulted only when cytology is unavailable.
                    # An unused qualified cytospin entry cannot invalidate a valid
                    # primary measurement; malformed selected entries still block.
                    for field in fields:
                        val = numeric(field, maximum=1 if p.variable.endswith('_percent') else None, clinical=True)
                        if val is not None:
                            break
                    if val is not None and p.variable.endswith('_percent'):
                        val *= 100
            row[p.variable] = val
        patients[hashed].append(row)
        evidence.append(row)
    records = []
    for hashed, rows in sorted(patients.items()):
        if cohort == 'circall':
            for p in engine.PREDICTORS:
                if len({r[p.variable] for r in rows if r[p.variable] is not None}) > 1:
                    issues.append(dict(reason='conflicting_diagnosis_metadata', field=p.variable, sheet=sheet.name,
                                       rows=[r['row'] for r in rows]))
        plasma = [r for r in rows if r['eligible_outcome']]
        if not plasma:
            continue
        outcomes = [r['outcome'] for r in plasma if r['outcome'] is not None]
        record = dict(subject_hash=hashed, cohort=cohort, cfdna_ng_per_ml=float(np.median(outcomes)) if outcomes else np.nan,
                      outcome_sample_n=len(outcomes), eligible_sample_n=len(plasma))
        for p in engine.PREDICTORS:
            values = [r[p.variable] for r in rows if r[p.variable] is not None]
            record[p.variable+'_sample_n'] = len(values)
            record[p.variable] = (values[0] if p.kind == 'categorical' or cohort == 'circall' else float(np.median(values))) if values else np.nan
            if cohort == 'retrospective' and p.kind == 'categorical' and len(set(values)) > 1:
                counts['discordant_'+p.variable+'_patients'] += 1
        records.append(record)
    frame = pd.DataFrame(records, columns=columns)
    counts.update(eligible_patients=len(frame), patients_with_numeric_outcome=int(frame.cfdna_ng_per_ml.notna().sum()),
                  patients_with_missing_outcome=int(frame.cfdna_ng_per_ml.isna().sum()),
                  patients_with_nonpositive_median=int(frame.cfdna_ng_per_ml.le(0).sum()),
                  patients_with_positive_median=int(frame.cfdna_ng_per_ml.gt(0).sum()),
                  patients_with_repeated_eligible_samples=int(frame.eligible_sample_n.gt(1).sum()))
    return frame, dict(counts), evidence, issues
