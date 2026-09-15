"""Source-specific field mappings; analytical calculations live in preparation."""
import json
from pathlib import Path

import pandas as pd

from .preparation import (MEASUREMENTS, mapped_measurements, present, read_sheet,
                          retrospective_timepoint, subject_key, text, validate_measurements)

CORE = {name: name for name in (
    'volume_ml', 'elution_volume_uL', 'dna_concentration_ng_per_uL', 'dna_total_ng',
    'dna_ng_per_mL_plasma', 'cfDNA_fraction', 'cfDNA_total_ng', 'cfDNA_ng_per_mL_plasma',
    'cfDNA_avg_size_bp',
)}
MNC = {
    'mnc_tube_count_million': 'MNC_tube_count_million',
    'mnc_aliquot_count_million': 'MNC_aliquot_count_million',
    'mnc_vario_ng_per_uL': 'MNC_vario_ng_per_uL',
    'mnc_vario_total_ng': 'MNC_vario_total_ng',
    'mnc_albumin_ng_per_uL': 'MNC_albumin_ng_per_uL', 'mnc_DIN': 'MNC_DIN',
}
REQUIRED_CORE = {'volume_ml', 'elution_volume_uL', 'dna_concentration_ng_per_uL',
                 'dna_total_ng', 'dna_ng_per_mL_plasma'}
SOURCE_MAPPINGS = {
    'retrospective': {**CORE, 'blood_volume_ml': 'blood_volume_mL', **MNC},
    'circall': {**CORE, 'cfDNA_concentration_ng_per_uL': 'cfDNA_ng/µl'},
    'pediatric_controls': {**CORE, 'cfDNA_concentration_ng_per_uL': 'cfDNA_ng/µl'},
    'existing_controls': {'dna_ng_per_mL_plasma': 'Conc ng/mL  plasma'},
}


def sample_state(value):
    if text(value).casefold() == 'na':
        return 'explicit_missing'
    return 'present' if present(value) else 'blank'


def make_record(row, path, sheet, source, compartment, mapping, *, patient_identity,
                patient_id, timepoint, source_timepoint, source_tissue, is_control=False):
    sample = text(row.value('sample_id')) if source != 'existing_controls' else f'donor_row_{row.number}'
    key = subject_key(source, patient_identity)
    if is_control and key:
        key = 'Control_' + key
    state = sample_state(sample)
    values, reasons, raw = mapped_measurements(row, mapping)
    values, reasons, issues = validate_measurements(values, reasons, raw, compartment=compartment,
                                                   supplied_endpoint=source == 'existing_controls')
    record_id = f'{source}:{sheet}:{row.number}:{compartment}'
    record = {
        'record_id': record_id, 'source': source,
        'cohort': 'control' if is_control else source, 'is_control': is_control,
        'control_source': source if is_control else '',
        'patient_key': key, 'patient_id': text(patient_id) if present(patient_id) else '',
        'sample_id': sample if state == 'present' else '', 'sample_state': state,
        'sample_key': f'{source}:{compartment}:{sample}' if state == 'present' else None,
        'source_file': str(Path(path).resolve()), 'source_sheet': sheet, 'source_row': row.number,
        'source_tube_key': f'{source}:{sheet}:{row.number}',
        'source_tissue': text(source_tissue), 'compartment': compartment,
        'source_timepoint': text(source_timepoint), 'timepoint': timepoint,
        'extraction_type': text(row.value('nucleic_acid')),
        'extraction_method': text(row.value('extraction_method')),
        'tube': text(row.value('tube')), 'genetic_subtype': text(row.value('genetic_subtype')),
        'hospital': ({'001': 'RDB', '002': 'TRS'}.get(text(patient_id)[:3], 'unknown')
                     if source == 'circall' else 'unavailable'),
        'mrd_raw': text(row.value('MRD_IgTCR')) if source == 'retrospective' else '',
        'mrd_status': '', 'qc_hold': bool(issues),
        'raw_measurements': json.dumps(raw, default=str, ensure_ascii=False),
    }
    for name in MEASUREMENTS:
        record[name] = values.get(name)
        record[name + '_status'] = reasons.get(name, 'field_unavailable')
    return record, [dict(record_id=record_id, source=source, source_sheet=sheet,
                         source_row=row.number, sample_id=record['sample_id'], **issue) for issue in issues]


def retrospective(path):
    required = REQUIRED_CORE | {'lastname', 'sample_id', 'treatment_phase', 'tissue', 'nucleic_acid'}
    sheet, rows, headers = read_sheet(path, 'Inventaire', required)
    records, issues, mrds = [], [], {}
    for row in rows:
        # A formatting/formula-only row is not a recorded tube.
        if not any(present(row.value(k)) for k in ('lastname', 'sample_id', 'treatment_phase', 'nucleic_acid')):
            continue
        identity = row.value('lastname')
        tp_raw = row.value('treatment_phase')
        tp = retrospective_timepoint(tp_raw)
        tissue = text(row.value('tissue'))
        acid = text(row.value('nucleic_acid'))
        if tissue.casefold() != 'lcr' and tp and present(identity):
            raw = text(row.value('MRD_IgTCR')).casefold()
            if raw not in ('', 'nan', 'none'):
                mrds.setdefault((subject_key('retrospective', identity), tp), []).append(raw)
        common = dict(patient_identity=identity, patient_id=row.value('inclusion_id'),
                      timepoint=tp, source_timepoint=tp_raw, source_tissue=tissue)
        mapping = {**CORE, 'blood_volume_ml': 'blood_volume_mL'}
        plasma_evidence = 'cfdna' in acid.casefold() or any(
            present(row.value(k)) for k in ('dna_concentration_ng_per_uL', 'dna_total_ng', 'volume_ml'))
        if plasma_evidence:
            compartment = {'sang': 'plasma', 'lcr': 'CSF', 'moelle': 'bone marrow'}.get(tissue.casefold(), 'unknown')
            rec, qc = make_record(row, path, sheet, 'retrospective', compartment, mapping, **common)
            records.append(rec); issues.extend(qc)
        pellet_evidence = 'mnc' in acid.casefold() or any(present(row.value(k)) for k in MNC.values())
        if pellet_evidence:
            compartment = 'blood pellet' if tissue.casefold() == 'sang' else 'bone marrow' if tissue.casefold() == 'moelle' else 'cell pellet'
            rec, qc = make_record(row, path, sheet, 'retrospective', compartment, MNC, **common)
            # Do not duplicate record IDs if a non-blood source contains both fractions.
            rec['record_id'] += ':MNC'
            rec['extraction_type'] = 'MNC celDNA'
            records.append(rec); issues.extend(qc)
        if not plasma_evidence and not pellet_evidence:
            # Preserve an inventory entry, without inventing a measured compartment.
            rec, qc = make_record(row, path, sheet, 'retrospective', 'unknown', {}, **common)
            records.append(rec); issues.extend(qc)
    for rec in records:
        values = mrds.get((rec['patient_key'], rec['timepoint']), [])
        rec['mrd_status'] = ('neg' if all(v in {'na', 'negative', 'neg', 'n/a'} for v in values) else 'pos') if values else ''
    return records, issues, headers


def circall(path, controls=False):
    source = 'pediatric_controls' if controls else 'circall'
    requested = 'cohorte_control' if controls else 'cohorte_lal'
    required = REQUIRED_CORE | {'circall_id', 'sample_id', 'compartment'} | (set() if controls else {'timepoint'})
    sheet, rows, headers = read_sheet(path, requested, required)
    records, issues = [], []
    for row in rows:
        # Keep scheduled rows for known patients, but not empty template people.
        if not present(row.value('circall_id')) and not present(row.value('sample_id')):
            continue
        compartment = text(row.value('compartment')).casefold()
        compartment = 'CSF' if compartment == 'csf' else compartment or 'unknown'
        tp_raw = row.value('timepoint')
        rec, qc = make_record(row, path, sheet, source, compartment, SOURCE_MAPPINGS[source],
                             patient_identity=row.value('circall_id'), patient_id=row.value('circall_id'),
                             timepoint='Control' if controls else text(tp_raw).casefold() or None,
                             source_timepoint=tp_raw, source_tissue=compartment, is_control=controls)
        records.append(rec); issues.extend(qc)
    return records, issues, headers


def donors(path):
    sheet, rows, headers = read_sheet(path, None, {'Donor', 'Conc ng/mL  plasma'})
    records, issues = [], []
    for row in rows:
        if not present(row.value('Donor')):
            continue
        rec, qc = make_record(row, path, sheet, 'existing_controls', 'plasma', SOURCE_MAPPINGS['existing_controls'],
                             patient_identity=row.value('Donor'), patient_id='', timepoint='Control',
                             source_timepoint='Control', source_tissue='plasma', is_control=True)
        records.append(rec); issues.extend(qc)
    return records, issues, headers


def prepare(inventory, circall_file, donor_file, cohorts=('retrospective', 'circall')):
    records, issues, schemas = [], [], {}
    loaders = []
    if 'retrospective' in cohorts:
        loaders.append(('retrospective', retrospective, inventory))
    if 'circall' in cohorts:
        loaders.append(('circall', circall, circall_file))
    loaders.extend([('pediatric_controls', lambda path: circall(path, controls=True), circall_file),
                    ('existing_controls', donors, donor_file)])
    for source, loader, path in loaders:
        rows, qc, schema = loader(path)
        records.extend(rows); issues.extend(qc); schemas[source] = schema
    frame = pd.DataFrame(records)
    if frame.empty:
        raise ValueError('No inventory records found')
    for field in MEASUREMENTS:
        frame[field] = pd.to_numeric(frame[field], errors='coerce')
    if frame.record_id.duplicated().any():
        raise ValueError('Duplicate prepared source record identifiers')
    return frame, pd.DataFrame(issues, columns=['record_id', 'source', 'source_sheet', 'source_row', 'sample_id', 'field', 'recorded', 'calculated', 'reason']), schemas
