"""Reformat the retrospective source, preserving values, formulas and formula caches."""
import argparse
from copy import copy, deepcopy
import hashlib
from io import BytesIO
import json
from pathlib import Path
import re
from xml.etree import ElementTree as ET
from zipfile import ZipFile, ZIP_DEFLATED

from openpyxl import Workbook, load_workbook
from openpyxl.formula import Tokenizer
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

COLUMNS = [('lastname', 'lastname'), ('D1 date', 'tt_d1_date'),
           ('sample_date', 'num_date'), ('day', 'day'),
           ('num_blast', 'blast_count_x10*9/L'), ('percent_blast', 'percent_blast'),
           ('firstname', 'firstname'), ('subtype', 'subtype'),
           ('induction', 'induction'), ('consolidation', 'consolidation'),
           ('num_log', 'num_log'), (None, 'source_note')]
SHEETS = {'cleandata': 'blast', 'test': 'source_test'}
NS = {'s': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
CELL = re.compile(r'(\$?)([A-Z]+)(\$?\d+)')


def remap_formula(formula, columns):
    parts = []
    for token in Tokenizer(formula).items:
        if token.type == 'OPERAND' and token.subtype == 'RANGE':
            match = CELL.fullmatch(token.value)
            if match is None or match[2] not in columns:
                raise ValueError('Unsupported formula reference; review without printing source values')
            parts.append(match[1] + columns[match[2]] + match[3])
        else:
            parts.append(token.value)
    return '=' + ''.join(parts)


def migrate(source, output):
    source, output = Path(source), Path(output)
    if output.exists() or output.is_symlink():
        raise ValueError('Destination exists; choose a new input filename')
    original = source.read_bytes()
    source_hash = hashlib.sha256(original).hexdigest()
    book = load_workbook(BytesIO(original), data_only=False)
    cached = load_workbook(BytesIO(original), data_only=True)
    new = Workbook()
    new.remove(new.active)
    mappings, stats = {}, {}
    try:
        if set(book.sheetnames) != set(SHEETS):
            raise ValueError('Unexpected source sheets; review before migration')
        for old_name, new_name in SHEETS.items():
            old = book[old_name]
            headers = [c.value for c in old[1]]
            populated = [h for h in headers if h is not None]
            if len(populated) != len(set(populated)) or set(populated) != {h for h, _ in COLUMNS if h is not None}:
                raise ValueError('Unexpected source headers; no columns may be silently dropped')
            if headers.count(None) > 1:
                raise ValueError('Multiple unheaded columns require explicit review')
            indexes = {h: headers.index(h)+1 for h, _ in COLUMNS if h in headers}
            cols = {get_column_letter(indexes[h]): get_column_letter(i)
                    for i, (h, _) in enumerate(COLUMNS, 1) if h in indexes}
            sheet = new.create_sheet(new_name)
            sheet.append([h for _, h in COLUMNS])
            mappings[old_name] = (new_name, cols)
            formula_count = 0
            for row in old.iter_rows(min_row=2):
                for col, (old_header, _) in enumerate(COLUMNS, 1):
                    if old_header not in indexes:
                        continue
                    cell = row[indexes[old_header]-1]
                    dest = sheet.cell(cell.row, col)
                    dest.value = remap_formula(cell.value, cols) if cell.data_type == 'f' else cell.value
                    dest.number_format = 'yyyy-mm-dd' if col in (2,3) else cell.number_format
                    dest.font = Font(color='000000' if cell.data_type == 'f' else '008000')
                    if cell.comment is not None:
                        dest.comment = copy(cell.comment)
                    if cell.data_type == 'f':
                        formula_count += 1
                        if cached[old_name][cell.coordinate].value is None:
                            raise ValueError('Source contains an uncached formula; recalculate original before migration')
            sheet.freeze_panes = 'B2'
            sheet.auto_filter.ref = sheet.dimensions
            sheet.sheet_view.showGridLines = False
            sheet.row_dimensions[1].height = 34
            for cell in sheet[1]:
                cell.fill = PatternFill('solid', fgColor='17365D')
                cell.font = Font(color='FFFFFF', bold=True)
                cell.alignment = Alignment(wrap_text=True, vertical='center')
                sheet.column_dimensions[cell.column_letter].width = 28 if cell.column in (5,12) else 21
            stats[new_name] = {'rows': old.max_row-1, 'formula_cells': formula_count}
        notes = new.create_sheet('README')
        for row in [
            ('Field', 'Description'), ('Cohort', 'Retrospective'),
            ('Active worksheet', 'blast; source_test is retained evidence and is not analyzed'),
            ('Source file', source.name), ('Source SHA-256', source_hash),
            ('Unit', 'blast_count_x10*9/L: x10^9/L, confirmed by investigator on 2026-10-01; no conversion'),
            ('Identity', 'lastname retained; trimmed case-sensitive grouping preserved; no new patient IDs'),
            ('Dates', 'D1 date renamed tt_d1_date; sample_date renamed num_date; recorded dates unchanged'),
            ('day', 'Original formula and cached value retained; references mapped to reordered columns'),
            ('percent_blast', 'Original percentages retained; not converted to a 0-1 fraction'),
            ('num_log', 'Original log formula and cached value retained; unused in descriptive kinetics'),
            ('source_note', 'Original unheaded source column, including any notes'),
            ('WBC', 'Not supplied; no WBC worksheet or inferred counts created'),
            ('Preservation', 'All source rows and fields retained; original workbook archived byte-for-byte'),
        ]:
            notes.append(row)
        notes.column_dimensions['A'].width = 25
        notes.column_dimensions['B'].width = 105
        notes.freeze_panes = 'A2'
        for cell in notes[1]:
            cell.font = Font(bold=True, color='FFFFFF')
            cell.fill = PatternFill('solid', fgColor='17365D')
        for row in notes.iter_rows(min_row=2):
            row[1].alignment = Alignment(wrap_text=True, vertical='top')
            notes.row_dimensions[row[0].row].height = 32
        buffer = BytesIO()
        new.save(buffer)
        # Restore cached results and raw numeric XML verbatim: openpyxl removes
        # formula caches and can round floating-point values during serialization.
        patched = {}
        with ZipFile(BytesIO(original)) as srczip, ZipFile(buffer) as destzip:
            for old_name, (new_name, cols) in mappings.items():
                old_xml = ET.fromstring(srczip.read(f'xl/worksheets/sheet{book.sheetnames.index(old_name)+1}.xml'))
                path = f'xl/worksheets/sheet{new.sheetnames.index(new_name)+1}.xml'
                tree = ET.fromstring(destzip.read(path))
                cells = {c.attrib['r']: c for c in tree.findall('.//s:sheetData/s:row/s:c', NS)}
                for cell in old_xml.findall('.//s:sheetData/s:row/s:c', NS):
                    match = CELL.fullmatch(cell.attrib['r'])
                    if match[3] == '1' or match[2] not in cols or cell.attrib.get('t') in ('s','inlineStr'):
                        continue
                    value = cell.find('s:v', NS)
                    if value is None:
                        continue
                    dest = cells[cols[match[2]]+match[3]]
                    previous = dest.find('s:v', NS)
                    if previous is not None:
                        dest.remove(previous)
                    dest.append(deepcopy(value))
                    dest.set('t', cell.attrib.get('t','n'))
                patched[path] = ET.tostring(tree, encoding='utf-8', xml_declaration=True)
            final = BytesIO()
            with ZipFile(final,'w',ZIP_DEFLATED) as outzip:
                for item in destzip.infolist():
                    outzip.writestr(item, patched.get(item.filename, destzip.read(item.filename)))
        result = final.getvalue()
        checked = 0
        for data_only in (True,False):
            target = load_workbook(BytesIO(result), data_only=data_only)
            try:
                reference = cached if data_only else book
                for old_name, (new_name, cols) in mappings.items():
                    for row in reference[old_name].iter_rows(min_row=2):
                        for cell in row:
                            if cell.column_letter not in cols:
                                continue
                            expected = cell.value
                            if not data_only and cell.data_type == 'f':
                                expected = remap_formula(expected,cols)
                            if target[new_name][cols[cell.column_letter]+str(cell.row)].value != expected:
                                raise ValueError('Mapped workbook cell failed exact equivalence check')
                            checked += 1
            finally:
                target.close()
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open('xb') as stream:
            stream.write(result)
        return {'source':str(source), 'source_sha256':source_hash, 'output':str(output),
                'output_sha256':hashlib.sha256(result).hexdigest(), 'sheets':stats,
                'mapped_value_and_formula_checks':checked, 'status':'passed',
                'column_mapping':[{'source':a,'destination':b} for a,b in COLUMNS]}
    finally:
        book.close()
        cached.close()
        new.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--report',type=Path,required=True)
    args = parser.parse_args(argv)
    if args.report.exists():
        parser.error('Report exists; choose a new report path')
    report = migrate(args.source,args.output)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    with args.report.open('x') as stream:
        json.dump(report,stream,indent=2)
    print(json.dumps({'status':report['status'],'sheets':report['sheets'],
                      'mapped_checks':report['mapped_value_and_formula_checks']}))


if __name__ == '__main__':
    main()
