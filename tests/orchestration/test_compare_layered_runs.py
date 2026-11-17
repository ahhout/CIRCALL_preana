from pathlib import Path

from openpyxl import Workbook

from analysis.validation.compare_layered_runs import same_artifact


def test_comparison_detects_hidden_sheet_and_number_format_changes(tmp_path):
    book = Workbook()
    sheet = book.create_sheet('Evidence')
    sheet.sheet_state = 'hidden'
    sheet['A1'] = 0.25
    baseline = tmp_path/'baseline.xlsx'
    candidate = tmp_path/'candidate.xlsx'
    book.save(baseline)
    book.save(candidate)
    assert same_artifact(baseline, candidate)
    sheet['A1'].number_format = '0.0%'
    book.save(candidate)
    assert not same_artifact(baseline, candidate)
    sheet['A1'].number_format = 'General'
    sheet.sheet_state = 'visible'
    book.save(candidate)
    assert not same_artifact(baseline, candidate)
