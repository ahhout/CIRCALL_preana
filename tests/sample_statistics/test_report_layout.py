"""Presentation checks against independent saved aggregates, without refitting."""

from tests.fixtures.sample_statistics import saved_result
from copy import deepcopy
import json

import pytest
from openpyxl import load_workbook

from analysis.provenance import ROOT
from analysis.sample_statistics.step_01_prepare import load_definitions
from analysis.sample_statistics.step_04_report import inventory_records, workbook, validate_workbook




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
        assert book.sheetnames == ['Inventaire', 'Mesures', 'Témoins', 'Retards', 'Reference']
        assert book['Reference'].sheet_state == 'hidden'
        assert book.active.title == 'Inventaire'
        inventory = rows(book['Inventaire'])[0]
        assert inventory['Taux de réception'] == pytest.approx(5 / 7)
        assert book['Inventaire']['K6'].number_format == '0.0%'
        assert book['Inventaire']['K6'].comment is None
        assert inventory['Reçus éligibles au taux'] == 5 and inventory['Dénominateur planifié'] == 7
        assert all(cell.comment is None for row in book['Inventaire'] for cell in row)
        measurement = rows(book['Mesures'])[0]
        assert measurement['Médiane'] == 4 and measurement['Échantillons mesurés'] == 5
        assert measurement['Mesure indisponible'] == 2 and measurement['Timepoint'] == 'Diagnostic'
        assert book['Mesures'].column_dimensions['K'].hidden
        assert rows(book['Retards'])[0]['Patient'] == '=SYNTHETIC_PSEUDONYM'
        assert book['Retards']['A6'].data_type == 's'
        assert book['Retards'].column_dimensions['F'].hidden
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
    assert rows(book['Inventaire'])[0]['Motif'] == 'Valeur invalide'
    assert rows(book['Mesures'])[0]['Statut'].startswith('Bloqué :')
    assert rows(book['Retards'])[0]['Statut'].startswith('Bloqué :')
    book.close()


def test_mismatched_denominators_are_rejected():
    result = saved_result()
    result['tables']['receipt'][1]['classified_denominator'] = 8
    with pytest.raises(ValueError, match='denominators disagree'):
        inventory_records(result['tables'])


def test_centers_and_late_checklist_reconcile_without_changing_receipt_rates(tmp_path):
    from datetime import date
    from analysis.sample_statistics.step_01_prepare import receipt, aggregate, assessment
    from analysis.sample_statistics.step_04_report import display_order
    d=load_definitions(ROOT/'configs/definitions/sample_statistics.json')
    observations=[]
    for i,(center,pid,sample) in enumerate([('RDB','P1','RECEIVED'),('RDB','P1','na'),
                                          ('RDB','P1',None),('TRS','P2','RECEIVED'),('TRS','P3','?')]):
        observations.append(dict(center=center,subject_key=pid,patient_id=pid,visit='tp1',
                                 specimen='plasma',control=False,extraction_status='no',measurements={},
                                 sheet='synthetic',row=i+2,
                                 **receipt(sample,'tp1',date(2026,10,1),'circall',
                                           assessment('2026-10-05T12:00:00+02:00'),d)))
    tables=aggregate(observations,{**d,'metrics':{}})
    inventory=display_order(inventory_records(tables),d)
    assert [r['Center'] for r in inventory[:3]]==['All centers','RDB','TRS']
    assert all(r['Specimen']=='All specimens' and r['Timepoint']=='All timepoints' for r in inventory[:3])
    assert [r['Inventory samples'] for r in inventory[:3]]==[5,3,2]
    assert [r['Patients'] for r in inventory[:3]]==[3,1,2]
    assert [r['Overdue'] for r in inventory[:3]]==[3,2,1]
    assert [r['Marked missing'] for r in inventory[:3]]==[1,1,0]
    assert [r['Receipt rate'] for r in inventory[:3]]==[pytest.approx(2/3),.5,1.]
    result=saved_result()
    result.update(tables=tables,include_controls=False)
    path=tmp_path/'late.xlsx'
    workbook(path,result,d)
    validate_workbook(path,result,d)
    book=load_workbook(path)
    try:
        checklist=rows(book['Retards'])
        assert [r['Statut'] for r in checklist]==['En retard','En retard','Signalé manquant']
        assert 'Motif' not in checklist[0] and 'Visit' not in checklist[0]
        assert all(r['Timepoint']=='TP1' for r in checklist)
        for sheet in book:
            if sheet.sheet_state=='visible':
                import re
                assert not any(re.search(r'\bvisits?\b',v,re.I) for row in sheet.values for v in row if isinstance(v,str))
        assert book['Inventaire']['K6'].number_format=='0.0%'
        assert book['Inventaire']['K6'].comment is None
        assert all(cell.comment is None for row in book['Inventaire'] for cell in row)
    finally:
        book.close()


def test_unknown_center_is_retained_in_its_own_inventory_row():
    result=saved_result()
    detail=result['tables']['audit_detail']
    detail['summary'].append(dict(view='center',center='unknown',samples=1,patients=1,
                                  received_samples=0,received_patients=0))
    inventory=inventory_records(result['tables'])
    unknown=next(r for r in inventory if r['Center']=='Unknown')
    assert unknown['Inventory samples']==1 and unknown['Receipt rate'] is None


def test_french_tables_match_headers_and_preserve_native_evidence(tmp_path):
    result=saved_result()
    d=load_definitions(ROOT/'configs/definitions/sample_statistics.json')
    path=tmp_path/'francais.xlsx'
    workbook(path,result,d)
    book=load_workbook(path)
    for sheet in book:
        if sheet.sheet_state=='hidden':continue
        assert sheet['A1'].value.startswith('CIRCALL · ')
        assert sheet['A2'].value.startswith('Statut : terminé | Évaluation : ')
        for table in sheet.tables.values():
            from openpyxl.utils.cell import range_boundaries
            left,top,right,_=range_boundaries(table.ref)
            assert [column.name for column in table.tableColumns]==[
                sheet.cell(top,column).value for column in range(left,right+1)]
    assert book['Retards']['A6'].value=='=SYNTHETIC_PSEUDONYM'
    assert book['Retards']['A6'].data_type=='s'
    assert book['Reference'].sheet_state=='hidden'
    book.close()


def test_circall_inventory_adds_tissue_totals_without_summing_patient_counts(tmp_path):
    result=saved_result()
    tables=result['tables']
    tables['summary'] += [dict(view='specimen_visit',specimen='plasma',visit=visit,
                              samples=n,patients=2,received_samples=n,received_patients=2)
                          for visit,n in [('diag',2),('tp1',3)]]
    # A participant can occur at multiple timepoints; use the existing distinct total.
    tables['audit_detail']['summary'].append(dict(view='specimen',specimen='plasma',
                            samples=5,patients=2,received_samples=5,received_patients=2))
    d=load_definitions(ROOT/'configs/definitions/sample_statistics.json')
    path=tmp_path/'totaux.xlsx'
    workbook(path,result,d)
    book=load_workbook(path)
    tissue=[r for r in rows(book['Inventaire']) if r['tissue']=='plasma']
    assert [r['Timepoint'] for r in tissue]==['Tous les temps','Diagnostic','TP1']
    assert tissue[0]['Échantillons inventoriés']==5
    assert tissue[0]['Patients']==2
    assert tissue[0]['Reçus']==5
    book.close()


def test_tissue_subtotals_show_all_centers_rdb_and_trs_with_distinct_patients(tmp_path):
    from datetime import date
    from analysis.sample_statistics.step_01_prepare import receipt, aggregate, assessment
    d=load_definitions(ROOT/'configs/definitions/sample_statistics.json')
    observations=[]
    for center,pid,specimen,visit,sample in [
        ('RDB','P1','plasma','diag','RECEIVED'),('RDB','P1','plasma','tp1','na'),
        ('TRS','P2','plasma','diag','RECEIVED'),('TRS','P2','plasma','tp1',None),
        ('RDB','P1','CSF','diag','RECEIVED')]:
        observations.append(dict(center=center,subject_key=pid,patient_id=pid,visit=visit,
            specimen=specimen,control=False,extraction_status='no',measurements={},
            sheet='synthetic',row=len(observations)+2,
            **receipt(sample,visit,date(2026,10,1),'circall',
                      assessment('2026-10-05T12:00:00+02:00'),d)))
    result=saved_result()
    result.update(tables=aggregate(observations,{**d,'metrics':{}}),include_controls=False)
    path=tmp_path/'centres.xlsx'
    workbook(path,result,d)
    book=load_workbook(path)
    inventory=rows(book['Inventaire'])
    for tissue,expected in [('plasma',[(4,2),(2,1),(2,1)]),('LCR',[(1,1),(1,1),(0,0)])]:
        records=[r for r in inventory if r['tissue']==tissue]
        totals=records[:3]
        assert [r['Centre'] for r in totals]==['Tous les centres','RDB','TRS']
        assert all(r['Timepoint']=='Tous les temps' for r in totals)
        assert [(r['Échantillons inventoriés'],r['Patients']) for r in totals]==expected
    plasma=[r for r in inventory if r['tissue']=='plasma'][:3]
    assert [r['Taux de réception'] for r in plasma]==[pytest.approx(2/3),.5,1.]
    assert [r['Hors délai'] for r in plasma]==[2,1,1]
    book.close()


def test_formula_cannot_replace_literal_pseudonym(tmp_path):
    result = saved_result()
    definitions = load_definitions(ROOT/'configs/definitions/sample_statistics.json')
    path = tmp_path/'statistics.xlsx'
    workbook(path, result, definitions)
    book = load_workbook(path)
    cell = book['Retards']['A6']
    cell.data_type = 'f'
    book.save(path)
    book.close()
    with pytest.raises(ValueError, match='formula'):
        validate_workbook(path, result, definitions)
