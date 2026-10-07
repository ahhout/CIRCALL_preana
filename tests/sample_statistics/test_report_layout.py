"""Presentation checks against independent saved aggregates, without refitting."""
from copy import deepcopy
import json

import pytest
from openpyxl import load_workbook

from analysis.provenance import ROOT
from analysis.sample_statistics.core import load_definitions
from analysis.sample_statistics.reporting import inventory_records, workbook, validate_workbook


def saved_result():
    summary = dict(view='overall', samples=10, patients=3, received_samples=7, received_patients=3)
    receipt = [dict(view='overall', basis='deadline', status=status, samples=count, patients=3,
                    overdue_samples=2 if status == 'marked_missing' else 0,
                    classified_samples=classified, classified_denominator=7,
                    classified_percentage=classified / 7 if classified else None)
               for status, count, classified in [('received', 5, 5), ('marked_missing', 2, 2), ('unassessed', 1, 0)]]
    receipt.append(dict(view='overall', basis='manual', status='received', samples=2, patients=1,
                        overdue_samples=0, classified_samples=None, classified_denominator=None,
                        classified_percentage=None))
    measurement = dict(view='visit', field='dna_total_ng', unit='ng', specimen='plasma', assay='plasma DNA',
                       visit='diag', received_samples=7, available_patients=3, unavailable_samples=2,
                       n=5, mean=4., sd=1.5811388300841898, median=4., q1=3., q3=5., minimum=2., maximum=6., total=20.)
    return dict(scope='circall', status='complete', include_controls=True, blocking=[],
                metadata=dict(cohort='circall', assessment_time='2026-10-07T12:00:00+00:00'),
                tables=dict(summary=[summary], receipt=receipt, measurements=[measurement],
                            availability=[dict(view='overall', field='extraction_status', state='yes', count=6),
                                          dict(view='overall', field='extraction_status', state='no', count=4)],
                            missed=[dict(patient_id='=SYNTHETIC_PSEUDONYM', center='RDB', visit='diag',
                                         specimen='plasma', sheet='synthetic', row=2, receipt_reason='Overdue')],
                            audit_detail={'summary': [{'center': 'AUDIT_ONLY_CENTER'}]}),
                controls=dict(summary=[dict(summary, samples=2, patients=2, received_samples=2)],
                              measurements=[dict(measurement, n=2)], receipt=[], availability=[]))


def rows(sheet, header=5):
    values = list(sheet.values)
    return [dict(zip(values[header - 1], row)) for row in values[header:]]


def test_inventory_pivot_does_not_double_count_denominator_or_overlapping_views():
    result = saved_result()
    original = deepcopy(result)
    inventory = inventory_records(result['tables'])
    assert inventory[0]['Inventory samples'] == 10
    assert inventory[0]['Received'] == 7
    assert inventory[0]['Marked missing'] == inventory[0]['Overdue'] == 2
    assert inventory[0]['Due received'] == 5
    assert inventory[0]['Timed denominator'] == 7
    assert inventory[0]['Receipt rate'] == pytest.approx(5 / 7)
    assert inventory[0]['Extracted'] == 6
    assert result == original


def test_layout_saved_values_hidden_details_and_identifier_safety(tmp_path):
    result = saved_result()
    original = deepcopy(result)
    definitions = load_definitions(ROOT/'configs/definitions/sample_statistics.json')
    path = tmp_path/'statistics.xlsx'
    workbook(path, result, definitions)
    validate_workbook(path, result, definitions)
    assert result == original
    book = load_workbook(path)
    try:
        assert book.sheetnames == ['Inventory', 'Measurements', 'Controls', 'Overdue', 'Reference']
        assert book['Reference'].sheet_state == 'hidden'
        assert book.active.title == 'Inventory'
        inventory = rows(book['Inventory'])[0]
        assert inventory['Receipt rate'] == pytest.approx(5 / 7)
        assert book['Inventory']['J6'].number_format == '0.0%'
        assert '5 due received / 7 assessed samples' in book['Inventory']['J6'].comment.text
        measurement = rows(book['Measurements'])[0]
        assert measurement['Median'] == 4 and measurement['Measured samples'] == 5
        assert measurement['Missing samples'] == 2 and measurement['Visit'] == 'Diagnosis'
        assert book['Measurements'].column_dimensions['K'].hidden
        assert rows(book['Overdue'])[0]['Patient'] == '=SYNTHETIC_PSEUDONYM'
        assert book['Overdue']['A6'].data_type == 's'
        assert book['Overdue'].column_dimensions['F'].hidden
        reference = rows(book['Reference'])
        for section in ('summary', 'receipt', 'measurements', 'availability'):
            expected = result['tables'][section]
            actual = [row for row in reference if row['section'] == section]
            assert len(actual) == len(expected)
            for source, rendered in zip(expected, actual):
                for key, value in source.items():
                    if isinstance(value, float):
                        assert rendered[key] == pytest.approx(value)
                    else:
                        assert rendered[key] == value
        assert not any('AUDIT_ONLY_CENTER' in str(cell.value) for sheet in book for row in sheet for cell in row)
        assert not any(cell.data_type == 'f' for sheet in book for row in sheet for cell in row)
    finally:
        book.close()


@pytest.mark.parametrize('scope, controls, expected', [
    ('retrospective', False, ['Inventory', 'Measurements', 'Reference']),
    ('retrospective', True, ['Inventory', 'Measurements', 'Controls', 'Reference']),
    ('pooled', True, ['Inventory', 'Measurements', 'Reference']),
])
def test_scope_tabs_and_unassessed_pooled_rates(tmp_path, scope, controls, expected):
    result = saved_result()
    result.update(scope=scope, include_controls=controls)
    if scope == 'pooled':
        result['tables']['receipt'] = []
    definitions = load_definitions(ROOT/'configs/definitions/sample_statistics.json')
    path = tmp_path/'scope.xlsx'
    workbook(path, result, definitions)
    book = load_workbook(path)
    assert book.sheetnames == expected
    if scope == 'pooled':
        assert rows(book['Inventory'])[0]['Receipt rate'] is None
        assert rows(book['Inventory'])[0]['Marked missing'] is None
    book.close()


def test_blocked_report_never_presents_saved_numbers_as_valid_results(tmp_path):
    result = saved_result()
    result.update(status='blocked', blocking=[dict(field='synthetic', issue='Invalid value', occurrences=2)])
    definitions = load_definitions(ROOT/'configs/definitions/sample_statistics.json')
    path = tmp_path/'blocked.xlsx'
    workbook(path, result, definitions)
    book = load_workbook(path)
    assert rows(book['Inventory'])[0]['Reason'] == 'Invalid value'
    assert rows(book['Measurements'])[0]['Status'].startswith('Blocked:')
    assert rows(book['Overdue'])[0]['Status'].startswith('Blocked:')
    book.close()


def test_mismatched_denominators_are_rejected():
    result = saved_result()
    result['tables']['receipt'][1]['classified_denominator'] = 8
    with pytest.raises(ValueError, match='denominators disagree'):
        inventory_records(result['tables'])
