"""Trim approved label fields into new XLSX copies; report ambiguous cells.

Usage: conda run -n pre_analysis python -m analysis.workbook_cleanup
    --input input/one.xlsx input/two.xlsx --output-dir output/<fresh-folder>

Identifiers, measurements, dates and formulas are never rewritten. Worksheet XML
is patched at individual text cells so Excel extensions and formula caches survive.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
from html import escape
import json
import math
from pathlib import Path
import posixpath
import re
import sys
import warnings
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from openpyxl import load_workbook

NS = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
REL = '{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id'
FIELDS = frozenset({'tissue', 'compartment', 'nucleic_acid', 'tube', 'lineage',
                    'genetic_subtype', 'gene_fusion', 'karyotype', 'cns_status',
                    'extraction_method', 'treatment_phase', 'timepoint', 'sampling_plan'})
MEASUREMENTS = frozenset({'volume_ml', 'blood_volume_ml', 'elution_volume_uL',
    'dna_concentration_ng_per_uL', 'dna_total_ng', 'dna_ng_per_mL_plasma',
    'cfDNA_fraction', 'cfDNA_ng/µl', 'cfDNA_total_ng', 'cfDNA_ng_per_mL_plasma',
    'cfDNA_avg_size_bp'})
DATES = frozenset({'sampling_date', 'extraction_date', 'tt_d1_date', 'diag_wbc_date'})
MISSING = {'', 'na', 'n/a', 'none', 'nan', '-', 'sk'}
CELL = re.compile(rb'<c\b[^>]*\br="([A-Z]+[0-9]+)"[^>]*(?:/>|>.*?</c>)', re.S)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def numeric(value):
    if isinstance(value, bool):
        return False
    try:
        return math.isfinite(float(str(value).strip().replace(',', '.')))
    except (ValueError, TypeError):
        return False


def inspect(path, selected):
    changes, reviews = {}, []
    with warnings.catch_warnings():
        warnings.simplefilter('ignore', UserWarning)
        book = load_workbook(path, read_only=True, data_only=False)
        try:
            for name in selected:
                if name not in book.sheetnames:
                    continue
                rows = book[name].iter_rows()
                headers = [str(c.value).strip() if c.value is not None else '' for c in next(rows, [])]
                nonempty = [h for h in headers if h]
                if len(nonempty) != len(set(nonempty)):
                    raise ValueError('Duplicate headers: resolve them before cleanup')
                changes[name] = {}
                for row in rows:
                    for header, cell in zip(headers, row):
                        value = cell.value
                        if cell.data_type == 'f' or value is None:
                            continue
                        if header in FIELDS and isinstance(value, str) and value != value.strip():
                            if not value.strip():
                                reviews.append({'sheet':name,'cell':cell.coordinate,'field':header,
                                                'reason':'whitespace_only_value_requires_missingness_decision'})
                            else:
                                changes[name][cell.coordinate] = (header, value.strip())
                        if isinstance(value, str) and value.strip().casefold() not in MISSING:
                            reason = ('date_text_requires_review' if header in DATES else
                                      'nonnumeric_measurement_requires_review' if header in MEASUREMENTS and not numeric(value) else None)
                            if reason:
                                reviews.append({'sheet':name,'cell':cell.coordinate,'field':header,'reason':reason})
        finally:
            book.close()
    if not changes:
        raise ValueError('None of the selected sheets exists in a workbook')
    return changes, reviews


def clean(path, dest, selected, *, text_changes=None):
    """Patch validated text replacements, or inspect for label trimming by default."""
    before_hash = digest(path)
    changes, reviews = inspect(path, selected) if text_changes is None else (text_changes, [])
    edits, patched = {}, {}
    with ZipFile(path) as zin:
        shared = (list(ET.fromstring(zin.read('xl/sharedStrings.xml')))
                  if 'xl/sharedStrings.xml' in zin.namelist() else [])
        rels = ET.fromstring(zin.read('xl/_rels/workbook.xml.rels'))
        targets = {r.attrib['Id']:r.attrib['Target'] for r in rels}
        sheets = ET.fromstring(zin.read('xl/workbook.xml')).find('m:sheets', NS)
        for sheet in sheets:
            name = sheet.attrib['name']
            wanted = changes.get(name, {})
            if not wanted:
                continue
            target = targets[sheet.attrib[REL]]
            member = target.lstrip('/') if target.startswith('/') else posixpath.normpath('xl/'+target)
            original = zin.read(member)
            replacements = {}
            def replace(match):
                coordinate = match.group(1).decode('ascii')
                if coordinate not in wanted:
                    return match.group(0)
                raw_cell = match.group(0)
                cell = ET.fromstring(raw_cell)
                if any(child.tag.split('}')[-1] == 'f' for child in cell):
                    raise ValueError('Refusing to modify a formula cell')
                # Rich text cells require a separate formatting-aware decision.
                if b'<r>' in raw_cell or b'<r ' in raw_cell:
                    raise ValueError('Rich text in a selected cell; manual review required')
                if cell.attrib.get('t') == 's':
                    entry = shared[int(cell.find('v').text)]
                    if entry.find('m:r', NS) is not None:
                        raise ValueError('Shared rich text requires manual formatting review')
                opening = raw_cell[:raw_cell.index(b'>')+1]
                opening = re.sub(rb'\s+t="[^"]*"', b'', opening)
                opening = opening[:-1]+b' t="inlineStr">'
                text = escape(wanted[coordinate][1], quote=False).encode('utf-8')
                updated = opening+b'<is><t xml:space="preserve">'+text+b'</t></is></c>'
                replacements[coordinate] = (raw_cell, updated)
                return updated
            modified = CELL.sub(replace, original)
            if set(replacements) != set(wanted):
                raise ValueError('Worksheet cell encoding not supported; no output published')
            ET.fromstring(modified)
            restored = CELL.sub(lambda m: replacements[m.group(1).decode()][0]
                                if m.group(1).decode() in replacements else m.group(0), modified)
            if restored != original:
                raise ValueError('Unexpected worksheet change')
            edits[member], patched[member] = replacements, modified
        with dest.open('xb') as stream, ZipFile(stream, 'w') as zout:
            zout.comment = zin.comment
            for info in zin.infolist():
                zout.writestr(info, patched.get(info.filename, zin.read(info.filename)))
    with ZipFile(path) as original, ZipFile(dest) as copied:
        if original.namelist() != copied.namelist() or copied.testzip() is not None:
            raise ValueError('Workbook archive verification failed')
        for name in original.namelist():
            data = copied.read(name)
            if name in edits:
                replacements = edits[name]
                data = CELL.sub(lambda m: replacements[m.group(1).decode()][0]
                                if m.group(1).decode() in replacements else m.group(0), data)
            if data != original.read(name):
                raise ValueError('Unapproved workbook content changed')
    remaining, _ = inspect(dest, selected) if text_changes is None else ({}, [])
    if any(remaining.values()) or digest(path) != before_hash:
        raise ValueError('Cleanup or source preservation verification failed')
    changed = [{'sheet':sheet,'cell':cell,'field':entry[0],
                'operation':'trim_outer_whitespace' if text_changes is None else 'replace_approved_text'}
               for sheet, cells in changes.items() for cell,entry in cells.items()]
    return {'source':str(path),'source_sha256':before_hash,'output':str(dest),
            'output_sha256':digest(dest),'changed_cells':changed,
            'change_counts':dict(Counter(c['field'] for c in changed)),
            'review_cells':reviews,'review_counts':dict(Counter(c['reason'] for c in reviews)),
            'verified':'All package contents unchanged except listed text-cell edits; source hash unchanged; output reopened; formulas and caches preserved.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, nargs='+', required=True)
    parser.add_argument('--sheets', nargs='+', default=['Inventaire','cohorte_lal','cohorte_control'])
    parser.add_argument('--output-dir', type=Path, required=True)
    args = parser.parse_args()
    if len({p.name for p in args.input}) != len(args.input):
        parser.error('Input basenames must be unique')
    if any(not p.is_file() or p.suffix.lower() != '.xlsx' for p in args.input):
        parser.error('Every input must be an existing XLSX file')
    if args.output_dir.exists():
        parser.error('Output directory must not exist')
    started = datetime.now(timezone.utc).isoformat()
    args.output_dir.mkdir(parents=True)
    report = {'started_utc':started,'command':[sys.executable,*sys.argv],
              'script_sha256':digest(Path(__file__)), 'trim_fields':sorted(FIELDS),
              'scope':'Trim labels only; dates/measurements reviewed without conversion; identifiers excluded',
              'workbooks':[]}
    for source in args.input:
        result = clean(source,args.output_dir/(source.stem+'_cleaned.xlsx'),args.sheets)
        report['workbooks'].append(result)
        print(json.dumps({'file':source.name,'trimmed_cells':len(result['changed_cells']),
                          'review_counts':result['review_counts']}))
    report['finished_utc'] = datetime.now(timezone.utc).isoformat()
    with (args.output_dir/'cleanup_report.json').open('x') as f:
        json.dump(report,f,indent=2,ensure_ascii=False)
        f.write('\n')


if __name__ == '__main__':
    main()
