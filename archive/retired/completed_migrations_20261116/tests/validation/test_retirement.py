"""Acceptance comparison must detect scientific and presentation drift."""
import json
from unittest.mock import patch

from openpyxl import Workbook
from PIL import Image
import pytest

from archive.retired.completed_migrations_20261116.analysis.validation import validate_retirement as validator


def runs(tmp_path):
    before, after = tmp_path/'before', tmp_path/'after'
    before.mkdir()
    after.mkdir()
    records = [dict(resolved_settings={'sample-selection-seed':123}, publications=[]),
               dict(resolved_settings={'sample-selection-seed':123}, publications=[])]
    return before, after, records


def compare(before, after, records):
    with patch.object(validator, 'verify_run', side_effect=[(r,{}) for r in records]):
        return validator.compare(before, after, before)


def test_metadata_changes_allowed_but_populations_and_numerical_values_checked(tmp_path):
    before, after, records = runs(tmp_path)
    for root, stamp in [(before,'2026-10-08T12:00:00+00:00'),(after,'2026-10-08T13:00:00+00:00')]:
        (root/'evidence.json').write_text(json.dumps(dict(started_utc=stamp,output_dir=str(root),population_n=10,coefficient=.25)))
    assert compare(before,after,records)['status']=='passed'
    for field, value in [('population_n',9),('coefficient',.26)]:
        payload=json.loads((before/'evidence.json').read_text())
        payload[field]=value
        (after/'evidence.json').write_text(json.dumps(payload))
        result=compare(before,after,records)
        assert result['status']=='failed' and result['failures']==['evidence.json']


def test_resolved_scientific_settings_cannot_change(tmp_path):
    before, after, records = runs(tmp_path)
    records[1]['resolved_settings']['sample-selection-seed']=42
    with pytest.raises(ValueError,match='settings/populations differ'):
        compare(before,after,records)


def test_rendered_pixel_change_is_detected(tmp_path):
    before, after, records = runs(tmp_path)
    for root,color in [(before,'white'),(after,'black')]:
        Image.new('RGB',(3,3),color).save(root/'figure.png')
    assert compare(before,after,records)['failures']==['figure.png']


def test_workbook_cell_change_is_detected(tmp_path):
    before, after, records = runs(tmp_path)
    for root,number in [(before,1.5),(after,1.6)]:
        book=Workbook()
        book.active.append(['coefficient',number])
        book.save(root/'report.xlsx')
        book.close()
    assert compare(before,after,records)['failures']==['report.xlsx']
