"""Privacy edits preserve scientific cells, grouping and saved formula caches."""
from io import BytesIO
from pathlib import Path
import re
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from openpyxl import Workbook, load_workbook
from openpyxl.comments import Comment
import pytest

from analysis.deidentification_package import group_values, scan_names, signatures, transform
from analysis.provenance import digest


def fixture(path):
    book = Workbook()
    book.properties.creator = 'SYNTHETIC AUTHOR PRIVATE'
    sheet = book.active
    sheet.title = 'blast'
    sheet.append(['lastname', 'firstname', 'dob', 'a2g_id', 'day', 'count', 'source_note', 'calculated'])
    for name in ['SYNTHETIC_SURNAME', ' SYNTHETIC_SURNAME ', 'synthetic_surname']:
        sheet.append([name, 'SYNTHETIC_FIRST', 'SYNTHETIC_DOB', 'SYNTHETIC_LINK', 1, 8, 'SYNTHETIC_NOTE', '=F2*2'])
    sheet['F2'].comment = Comment('SYNTHETIC_COMMENT_PRIVATE', 'SYNTHETIC_AUTHOR_PRIVATE')
    sheet['F2'].number_format = '0.000'
    sheet['J3'].number_format = '@'  # Self-closing last cell before the next row.
    stream = BytesIO()
    book.save(stream)
    book.close()
    with ZipFile(stream) as source, ZipFile(path, 'w') as target:
        for item in source.infolist():
            raw = source.read(item.filename)
            if item.filename == 'xl/worksheets/sheet1.xml':
                raw, count = re.subn(rb'<f>F2\*2</f><v\s*(?:/>|></v>)', b'<f>F2*2</f><v>16</v>', raw)
                assert count == 3
                raw = raw.replace(b'<worksheet ', b'<worksheet xmlns:xr="http://schemas.microsoft.com/office/spreadsheetml/2014/revision" ', 1)
                raw = raw.replace(b'<f>', b'<f xr:uid="SYNTHETIC-FORMULA-REVISION">')
            target.writestr(item, raw)


def test_privacy_clear_group_partition_and_formula_cache_preservation(tmp_path):
    source, target = tmp_path/'source.xlsx', tmp_path/'copy.xlsx'
    fixture(source)
    before = digest(source)
    groups = {'SYNTHETIC_SURNAME': 'RETRO-GROUP-1', 'synthetic_surname': 'RETRO-GROUP-2'}
    assert group_values(source, {'na', ''}) == set(groups)
    report, names = transform(source, target, 'retrospective-blasts', groups, {'na', ''})
    assert digest(source) == before
    assert report['preserved_formula_cells'] == 3
    assert report['formula_caches'] == 'byte-identical'
    assert scan_names(target, names) == {}
    book = load_workbook(target, read_only=True, data_only=True)
    try:
        rows = list(book.active.values)
        assert [r[0] for r in rows[1:]] == ['RETRO-GROUP-1', 'RETRO-GROUP-1', 'RETRO-GROUP-2']
        assert all(r[1:4] == (None, None, None) and r[6] is None for r in rows[1:])
        assert all(r[4:6] == (1, 8) and r[7] == 16 for r in rows[1:])
    finally:
        book.close()
    with ZipFile(source) as original, ZipFile(target) as copied:
        assert copied.read('xl/styles.xml') == original.read('xl/styles.xml')
        assert not any(n.startswith('docProps/') or 'comments' in n.lower() or n.endswith('.vml') for n in copied.namelist())
        for token in (b'SYNTHETIC_FIRST', b'SYNTHETIC_DOB', b'SYNTHETIC_LINK', b'SYNTHETIC_NOTE', b'SYNTHETIC_AUTHOR_PRIVATE'):
            assert not any(token in copied.read(n) for n in copied.namelist())
    with pytest.raises(FileExistsError):
        transform(source, target, 'retrospective-blasts', groups, {'na', ''})


def test_shared_strings_are_inlined_and_unused_identifiers_removed(tmp_path):
    source, target = tmp_path/'shared.xlsx', tmp_path/'clean.xlsx'
    fixture(source)
    with ZipFile(source) as archive:
        parts = {n: archive.read(n) for n in archive.namelist()}
    original = b'<c r="F2" s="1" t="n"><v>8</v></c>'
    assert original in parts['xl/worksheets/sheet1.xml']
    parts['xl/worksheets/sheet1.xml'] = parts['xl/worksheets/sheet1.xml'].replace(
        original, b'<c r="F2" s="1" t="s"><v>0</v></c>')
    # A retained text value and an unused identifying string in the shared table.
    parts['xl/sharedStrings.xml'] = b'<sst xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><si><t>8</t></si><si><t>SYNTHETIC_UNUSED_PRIVATE</t></si></sst>'
    with ZipFile(source, 'w') as archive:
        for n, raw in parts.items(): archive.writestr(n, raw)
    transform(source, target, 'retrospective-blasts',
              {'SYNTHETIC_SURNAME':'RETRO-GROUP-1', 'synthetic_surname':'RETRO-GROUP-2'}, {'na', ''})
    with ZipFile(target) as archive:
        assert not list(ET.fromstring(archive.read('xl/sharedStrings.xml')))
        assert not any(b'SYNTHETIC_UNUSED_PRIVATE' in archive.read(n) for n in archive.namelist())


def test_formula_dependency_on_removed_field_requires_review(tmp_path):
    source = tmp_path/'dependency.xlsx'
    fixture(source)
    with ZipFile(source) as archive: parts = {n: archive.read(n) for n in archive.namelist()}
    parts['xl/worksheets/sheet1.xml'] = parts['xl/worksheets/sheet1.xml'].replace(b'>F2*2</f>', b'>C2+1</f>')
    with ZipFile(source, 'w') as archive:
        for n, raw in parts.items(): archive.writestr(n, raw)
    with pytest.raises(ValueError, match='dependency review'):
        transform(source, tmp_path/'must_not_exist.xlsx', 'inventory', {}, {'na', ''})
    assert not (tmp_path/'must_not_exist.xlsx').exists()


def test_prefixed_worksheet_namespaces_preserve_caches(tmp_path):
    source, target = tmp_path/'prefixed.xlsx', tmp_path/'copy.xlsx'
    fixture(source)
    with ZipFile(source) as archive: parts = {n: archive.read(n) for n in archive.namelist()}
    main = b'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
    raw = parts['xl/worksheets/sheet1.xml'].replace(b'xmlns="'+main+b'"', b'xmlns:ns0="'+main+b'"')
    raw = re.sub(rb'<(/?)([A-Za-z][A-Za-z0-9]*)(?=[ />])', rb'<\1ns0:\2', raw)
    parts['xl/worksheets/sheet1.xml'] = raw
    with ZipFile(source, 'w') as archive:
        for n, value in parts.items(): archive.writestr(n, value)
    report, _ = transform(source, target, 'retrospective-blasts',
                          {'SYNTHETIC_SURNAME':'RETRO-GROUP-1', 'synthetic_surname':'RETRO-GROUP-2'}, {'na', ''})
    assert report['preserved_formula_cells'] == 3
    book = load_workbook(target, read_only=True, data_only=True)
    try: assert book.active['H2'].value == 16
    finally: book.close()


def test_unapproved_measurement_change_is_rejected_before_publication(tmp_path, monkeypatch):
    import analysis.deidentification_package as package
    source, target = tmp_path/'source.xlsx', tmp_path/'must_not_exist.xlsx'
    fixture(source)
    original = package.patch_sheet
    def corrupt(raw, strings, edits):
        return original(raw, strings, edits).replace(b'<v>8</v>', b'<v>9</v>')
    monkeypatch.setattr(package, 'patch_sheet', corrupt)
    with pytest.raises(ValueError, match='Unapproved cell change'):
        transform(source, target, 'retrospective-blasts',
                  {'SYNTHETIC_SURNAME':'RETRO-GROUP-1', 'synthetic_surname':'RETRO-GROUP-2'}, {'na', ''})
    assert not target.exists()
