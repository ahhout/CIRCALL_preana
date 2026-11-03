"""Unassigned template visits cannot block real samples or dilute receipt counts."""
from datetime import datetime

from openpyxl import Workbook
import pytest

from analysis.sample_statistics.core import prepare, assessment
from tests.fixtures.sample_statistics import D, ASOF


def source(path, changes):
    row = dict(circall_id=None, sample_id=None, dna_id=None, timepoint='diag', specimen_type='plasma',
               tube='Roche', extraction_method='pre-entered', sampling_plan=datetime(2026,10,1))
    row.update(changes)
    book = Workbook()
    sheet = book.active
    sheet.title = 'cohorte_lal'
    sheet.append(list(row))
    sheet.append(list(row.values()))
    book.save(path)
    book.close()


def test_unassigned_template_is_counted_and_skipped(tmp_path):
    path = tmp_path/'source.xlsx'
    source(path, {})
    rows, issues, skipped = prepare(path, 'circall', False, assessment(ASOF), D)
    assert not rows and not issues and skipped == 1


def test_identified_planned_visit_keeps_receipt_classification(tmp_path):
    path = tmp_path/'source.xlsx'
    source(path, dict(circall_id='001-9999-X-Z', sample_id='na'))
    rows, issues, skipped = prepare(path, 'circall', False, assessment(ASOF), D)
    assert len(rows) == 1 and not issues and skipped == 0
    assert rows[0]['receipt'] == 'marked_missing' and rows[0]['overdue']


@pytest.mark.parametrize('evidence', [dict(sample_id='SYNTHETIC'), dict(dna_id='SYNTHETIC'),
    dict(dna_total_ng=0), dict(sampling_time='10:00'), dict(genetic_subtype='A'),
    dict(circall_id='malformed'), dict(sample_id='=1+1'), dict(dna_total_ng='#VALUE!')])
def test_actual_orphaned_records_still_block(tmp_path, evidence):
    path = tmp_path/'source.xlsx'
    source(path, evidence)
    rows, issues, skipped = prepare(path, 'circall', False, assessment(ASOF), D)
    assert not rows and skipped == 0
    assert issues[0]['reason'] == 'patient_identity_unavailable'
