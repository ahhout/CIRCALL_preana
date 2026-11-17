"""Harmonized diagnosis preparation; source identifiers stay in memory only."""
from collections import Counter, defaultdict
from datetime import time
import hashlib
import json
from pathlib import Path
import re
import random

import numpy as np
import pandas as pd

from analysis.configuration import unique_object
from analysis.data_integrity.step_01_inspect import number
from analysis.utils.sample_io import read_sheet
from analysis.provenance import ROOT
from .schema import comparison_shape, observation_columns, predictors


def load_definitions(path):
    try:
        definitions = json.loads(Path(path).read_text(), object_pairs_hook=unique_object)
        expected = json.loads((ROOT/'configs/definitions/advanced_analysis.json').read_text(), object_pairs_hook=unique_object)
        # A custom --definitions file may change switches, but not scientific rules.
        if ({**definitions, 'comparisons': comparison_shape(definitions)}
                != {**expected, 'comparisons': comparison_shape(expected)}):
            raise ValueError()
        return definitions
    except (ValueError, OSError, TypeError, KeyError, AttributeError):
        raise ValueError('Unsupported Layer 3 definitions: comparison switches must be JSON true/false; '
                         'other scientific settings must match the versioned definition') from None


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


def empty_unreceived_row(source, config, d):
    """Ignore unassigned template visits, never an orphaned clinical record."""
    identity = source.get(config['identity'])
    if identity is not None and (identity.formula or identity.data_type == 'e'
                                 or token(identity.value) not in d['missing_tokens'] + d['unknown_tokens']):
        return False
    fields = {'sample_id', 'dna_id', d['outcome'],
              'dna_total_ng', 'dna_ng_per_ml_plasma', 'cfdna_total_ng', 'cfdna_fraction',
              'dna_concentration_ng_per_ul', 'cfdna_concentration_ng_per_ul',
              'extraction_input_volume_ml', 'elution_volume_ul', 'cfdna_avg_size_bp',
              'sampling_date', 'sampling_time', 'extraction_date', 'corticoide_pre_tt',
              'diag_blood_wbc_max_x10*9/L', 'diag_blood_blast_pct', 'diag_bm_blast_pct'}
    fields.update(field for sources in config['sources'].values() for field in sources)
    for field in fields:
        cell = source.get(field)
        if cell is None:
            continue
        if (cell.data_type == 'e' or cell.cached_type == 'e'
                or field in ('sample_id', 'dna_id') and cell.formula
                or token(cell.value) not in d['missing_tokens'] + d['unknown_tokens']):
            return False
    return True


def prepare(path, cohort, d, *, sample_selection_seed=None):
    seed = d['rules']['sample_selection_seed'] if sample_selection_seed is None else sample_selection_seed
    if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
        raise ValueError('Sample selection seed must be a nonnegative integer')
    config = d['cohorts'][cohort]
    sheet = read_sheet(path, config['sheet'])
    headers = [c.value for c in sheet.headers]
    issues, evidence = [], []
    counts = Counter(input_rows=len(sheet.rows), diagnosis_rows=0, eligible_plasma_samples=0,
                     excluded_empty_unreceived_diagnosis_rows=0,
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
    columns = observation_columns(d)
    cohort_predictors = [p for p in predictors(d) if p.variable in config['sources']]
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
        if cohort == 'retrospective' and token(value('specimen_type')) != 'plasma':
            counts['excluded_outcome_specimen_or_tube'] += 1
            continue
        if empty_unreceived_row(source, config, d):
            counts['excluded_empty_unreceived_diagnosis_rows'] += 1
            continue
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
        from analysis.utils.plot_style import center_from_id
        row = dict(subject_hash=hashed, cohort=cohort, center=center_from_id(key, cohort),
                   sheet=sheet.name, row=cells[0].row,
                   eligible_outcome=eligible, measurements={})
        # Only the hash enters local evidence; source sample IDs stay in memory.
        row['sample_hash'] = hashlib.sha256((cohort+'\0'+key+'\0'+str(value('sample_id')).strip()).encode()).hexdigest()
        row['selected_sample'] = False

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

        row['outcomes'] = {field: numeric(field, maximum=1 if field == 'cfdna_fraction' else None)
                           if eligible else None for field in d['outcomes']}
        row['outcome'] = row['outcomes'][d['outcome']]
        if eligible:
            counts['outcome_'+row['measurements'][d['outcome']]['state']] += 1
        for p in cohort_predictors:
            fields = config['sources'][p.variable]
            applicable = eligible or (cohort == 'circall' and p.variable in
                                      ('genetic_subtype', 'gb_per_l', 'peripheral_blast_percent', 'tumor_fraction_percent'))
            val = None
            if fields and applicable:
                if p.variable == 'sampling_time':
                    cell = source.get(fields[0])
                    if cell and token(cell.value) not in d['missing_tokens'] + d['unknown_tokens']:
                        if isinstance(cell.value, time) and cell.value.tzinfo is None:
                            val = 'Morning' if cell.value < time(d['rules']['sampling_time_cutoff_hour']) else 'Afternoon'
                        else:
                            issues.append(dict(reason='invalid_sampling_time', field=fields[0], sheet=sheet.name, row=cells[0].row))
                    row['measurements'][fields[0]] = dict(value=val, state='recorded' if val else 'unavailable',
                                                         cell=cell.coordinate if cell else None)
                elif p.kind == 'categorical':
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
            for p in cohort_predictors:
                if p.variable not in ('genetic_subtype', 'gb_per_l', 'peripheral_blast_percent', 'tumor_fraction_percent'):
                    continue  # Handling metadata belong to the selected sample.
                if len({r[p.variable] for r in rows if r[p.variable] is not None}) > 1:
                    issues.append(dict(reason='conflicting_diagnosis_metadata', field=p.variable, sheet=sheet.name,
                                       rows=[r['row'] for r in rows]))
        plasma = [r for r in rows if r['eligible_outcome']]
        if not plasma:
            continue
        candidates = [r for r in plasma if r['outcome'] is not None]
        # A separate RNG per patient avoids changes when unrelated patients are
        # added. Hash order is invariant to worksheet order for distinct samples;
        # repeated identical sample IDs use source row as the explicit tie-break.
        ordered = sorted(candidates or plasma, key=lambda r: (r['sample_hash'], r['row']))
        rng = random.Random(f'{seed}\0{cohort}\0{hashed}')
        selected = rng.choice(ordered)
        selected['selected_sample'] = True
        record = dict(subject_hash=hashed, cohort=cohort, center=selected['center'],
                      cfdna_ng_per_ml=float(selected['outcome']) if candidates else np.nan,
                      outcome_sample_n=int(bool(candidates)), eligible_sample_n=len(plasma),
                      available_outcome_sample_n=len(candidates))
        record.update({field: selected['outcomes'][field] if selected['outcomes'][field] is not None else np.nan
                       for field in d['outcomes']})
        for p in predictors(d):
            if p.variable not in config['sources']:
                record[p.variable] = np.nan
                record[p.variable+'_sample_n'] = 0
                continue
            values = [r[p.variable] for r in rows if r[p.variable] is not None]
            if ((cohort == 'retrospective' and p.variable != 'genetic_subtype')
                    or p.variable in ('corticoide_pre_tt', 'sampling_time', 'elution_volume_ul',
                                      'extraction_input_volume_ml', 'dna_concentration_ng_per_ul')):
                value = selected[p.variable]
                record[p.variable] = value if value is not None else np.nan
                record[p.variable+'_sample_n'] = int(value is not None)
            else:
                record[p.variable+'_sample_n'] = len(values)
                record[p.variable] = (values[0] if p.kind == 'categorical' or cohort == 'circall' else float(np.median(values))) if values else np.nan
            if cohort == 'retrospective' and p.variable in ('sex', 'genetic_subtype') and len(set(values)) > 1:
                counts['discordant_'+p.variable+'_patients'] += 1
        records.append(record)
    frame = pd.DataFrame(records, columns=columns)
    counts.update(eligible_patients=len(frame), patients_with_numeric_outcome=int(frame.cfdna_ng_per_ml.notna().sum()),
                  patients_with_missing_outcome=int(frame.cfdna_ng_per_ml.isna().sum()),
                  patients_with_nonpositive_outcome=int(frame.cfdna_ng_per_ml.le(0).sum()),
                  patients_with_positive_outcome=int(frame.cfdna_ng_per_ml.gt(0).sum()),
                  selected_numeric_outcome_samples=int(frame.outcome_sample_n.sum()),
                  unselected_numeric_outcome_samples=int((frame.available_outcome_sample_n-frame.outcome_sample_n).sum()),
                  patients_with_repeated_eligible_samples=int(frame.eligible_sample_n.gt(1).sum()))
    return frame, dict(counts), evidence, issues
