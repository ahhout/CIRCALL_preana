"""Prepare the ordered rows for statistics workbooks."""
from collections import Counter
from .labels import MEASUREMENT_LABELS


def inventory_records(tables, *, include_specimen_totals=False):
    """Pivot existing counts, including separately identified center totals."""
    records = []
    groups = [(summary, tables) for summary in tables.get('summary', [])]
    detail = tables.get('audit_detail', {})
    if include_specimen_totals:
        existing = {row.get('specimen') for row in tables.get('summary', []) if row.get('view') == 'specimen'}
        groups.extend((row, detail) for row in detail.get('summary', [])
                      if row.get('view') == 'specimen' and row.get('specimen') not in existing)
        center_tissues = {(row['specimen'], row['center']): row
                          for row in detail.get('summary', []) if row.get('view') == 'center_specimen'}
        if center_tissues:
            for specimen in sorted({row['specimen'] for row, _ in groups if row.get('view') == 'specimen'}):
                for center in ('RDB', 'TRS', *(['unknown'] if (specimen, 'unknown') in center_tissues else [])):
                    summary = center_tissues.get((specimen, center), dict(
                        view='center_specimen', specimen=specimen, center=center,
                        samples=0, patients=0, received_samples=0, received_patients=0))
                    groups.append((summary, detail))
    centers = {row['center']:row for row in detail.get('summary', [])
               if row.get('view')=='center' and row.get('center') in ('RDB','TRS','unknown')}
    if any(row.get('view')=='overall' for row in tables.get('summary', [])):
        for center in ('RDB','TRS', *(['unknown'] if 'unknown' in centers else [])):
            summary = centers.get(center, dict(view='center',center=center,samples=0,patients=0,
                                               received_samples=0,received_patients=0))
            groups.append((summary, detail))
    for summary, source in groups:
        same = lambda row: all(row.get(k) == summary.get(k) for k in ('view', 'center', 'specimen', 'visit'))
        receipt = [row for row in source.get('receipt', []) if same(row)]
        status = Counter()
        for row in receipt:
            status[row['status']] += row['samples']
        deadline = [row for row in receipt if row['basis'] == 'deadline']
        denominators = {row['classified_denominator'] for row in deadline if row['classified_denominator'] is not None}
        if len(denominators) > 1:
            raise ValueError('Receipt denominators disagree within a report group')
        denominator = next(iter(denominators), 0)
        due_received = sum(row['classified_samples'] or 0 for row in deadline if row['status'] == 'received')
        extraction = [row for row in source.get('availability', []) if same(row) and row['field'] == 'extraction_status']
        records.append({
            'Specimen': summary.get('specimen', 'All specimens'),
            'Center': {'unknown':'Unknown'}.get(summary.get('center'), summary.get('center', 'All centers')),
            'Timepoint': summary.get('visit', 'All timepoints'),
            'Patients': summary['patients'], 'Inventory samples': summary['samples'],
            'Received': summary['received_samples'],
            'Marked missing': status['marked_missing'] if receipt else None,
            'Unassessed': status['unassessed'] if receipt else None,
            'Overdue': sum(row['overdue_samples'] for row in receipt) if receipt else None,
            'Extracted': sum(row['count'] for row in extraction if row['state'] == 'yes') if any(row['state'] in ('yes', 'no') for row in extraction) else None,
            'Receipt rate': due_received / denominator if denominator else None,
            'Due received': due_received if denominator else None,
            'Timed denominator': denominator or None,
        })
    return records

def measurement_records(tables):
    return [{
        'Specimen': row['specimen'], 'Timepoint': row.get('visit', 'All timepoints'),
        'Measurement': MEASUREMENT_LABELS.get(row['field'], row['field']),
        'DNA label': None if row.get('assay') in ('specimen volume', 'plasma DNA', 'cfDNA size') else row.get('assay', '').replace('not_recorded', 'Not recorded'),
        'Unit': {'mL available specimen': 'mL', 'ng/mL recorded available plasma': 'ng/mL plasma'}.get(row['unit'], row['unit']), 'Measured samples': row['n'],
        'Missing samples': row['unavailable_samples'], 'Median': row['median'],
        'Q1': row['q1'], 'Q3': row['q3'],
        'Mean': row['mean'], 'SD': row['sd'], 'Minimum': row['minimum'],
        'Maximum': row['maximum'], 'Total': row['total'],
        'Available patients': row['available_patients'], 'Received samples': row['received_samples'],
    } for row in tables.get('measurements', [])]

def display_order(records, d):
    specimens = {name: i for i, name in enumerate(('plasma', 'CSF', 'blood pellet', 'bone marrow'))}
    visits = {'All timepoints': -1, **{name: i for i, name in enumerate(d['visits'] + ['control', 'unclassified'])}}
    ordered = sorted(records, key=lambda row: (
        0 if row.get('Specimen') == 'All specimens' else 1,
        specimens.get(row.get('Specimen'), 99),
        0 if row.get('Timepoint') == 'All timepoints' else 1,
        {'All centers':0,'RDB':1,'TRS':2,'Unknown':3}.get(row.get('Center'), 0),
        visits.get(row.get('Timepoint'), 99),
        row.get('Measurement', ''), row.get('DNA label', '')))
    return [{**row, 'Timepoint': display_timepoint(row.get('Timepoint', ''))}
            for row in ordered]

def display_timepoint(value):
    return {'diag':'Diagnosis', 'control':'Control', 'All timepoints':'All timepoints'}.get(value,str(value).upper())
