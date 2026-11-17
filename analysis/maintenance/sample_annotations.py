"""Standardize approved sample annotations with byte-preserving XLSX patches."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
from pathlib import Path
import posixpath
import shutil
import sys
import tempfile
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from openpyxl.utils.cell import coordinate_to_tuple

from analysis.configuration import unique_object
from analysis.maintenance.xlsx_patch import CELL, ROW, cell_xml
from analysis.provenance import ROOT, digest, envelope, write_json
from analysis.utils.sample_definitions import extraction_state
from analysis.utils.sample_io import read_sheet
from analysis.maintenance.workbook_cleanup import NS, REL


def plan(path, selected, config):
    """Never infer measurements, modify formulas, or expose source values."""
    changes = {}
    markers = set(config['replace_tokens'])
    for name in selected:
        sheet = read_sheet(path, name)
        headers = [c.value for c in sheet.headers]
        named = [h for h in headers if h is not None]
        if len(named) != len(set(named)):
            raise ValueError('Resolve duplicate headers before annotation migration')
        edits = {}
        dna_field = config['extraction']['identity']
        status_field = config['extraction']['status']
        if dna_field in headers and status_field not in headers:
            raise ValueError('DNA-ID sheet requires an existing extraction-status column')
        for row in sheet.rows:
            # Do not turn template/numbering-only rows into extracted samples.
            anchors = ('sample_id', dna_field, 'specimen_type', 'timepoint')
            is_sample = any(row[headers.index(h)].raw is not None for h in anchors if h in headers)
            for header, cell in zip(headers, row):
                if header in config['protected_fields'] or cell.formula or not isinstance(cell.value, str):
                    continue
                if cell.value.strip().casefold() in markers and cell.value != config['canonical_missing_token']:
                    field = header if header in ('sample_id', dna_field, status_field) else 'column_'+str(cell.column)
                    edits[cell.coordinate] = {'field': field, 'value': config['canonical_missing_token'], 'operation': 'canonical_missing_marker'}
            if is_sample and dna_field in headers:
                dna = row[headers.index(dna_field)]
                status = row[headers.index(status_field)]
                derived = extraction_state(dna, markers)
                if status.formula or derived == 'unavailable':
                    raise ValueError('Formula/error identity or status requires review before migration')
                if status.value != derived:
                    edits[status.coordinate] = {'field': status_field, 'value': derived, 'operation': 'derive_extraction_from_dna_id'}
        changes[name] = edits
    return changes


def patch(source, destination, changes):
    """Verify that reversing exactly the planned edits reproduces every ZIP member."""
    patched, reverse = {}, {}
    with ZipFile(source) as zin:
        targets = {r.attrib['Id']: r.attrib['Target'] for r in ET.fromstring(zin.read('xl/_rels/workbook.xml.rels'))}
        sheets = ET.fromstring(zin.read('xl/workbook.xml')).find('m:sheets', NS)
        for sheet in sheets:
            edits = changes.get(sheet.attrib['name'], {})
            if not edits:
                continue
            target = targets[sheet.attrib[REL]]
            member = target.lstrip('/') if target.startswith('/') else posixpath.normpath('xl/'+target)
            original = zin.read(member)
            seen, old_cells = set(), {}
            by_row = {}
            for coord in edits:
                by_row.setdefault(coordinate_to_tuple(coord)[0], []).append(coord)

            def replace_row(match):
                number, body = int(match[2]), match[3]

                def replace_cell(cell):
                    coord = cell[1].decode()
                    if coord not in edits:
                        return cell[0]
                    if b'<f' in cell[0] or b'<r>' in cell[0] or b'<r ' in cell[0]:
                        raise ValueError('Formula or rich-text edit refused')
                    seen.add(coord)
                    old_cells[coord] = cell[0]
                    return cell_xml(coord, edits[coord]['value'], cell[0])

                body = CELL.sub(replace_cell, body)
                for coord in by_row.get(number, []):
                    if coord in seen:
                        continue
                    column = coordinate_to_tuple(coord)[1]
                    following = next((c for c in CELL.finditer(body) if coordinate_to_tuple(c[1].decode())[1] > column), None)
                    where = following.start() if following else len(body)
                    body = body[:where]+cell_xml(coord, edits[coord]['value'])+body[where:]
                    seen.add(coord)
                    old_cells[coord] = b''
                return match[1]+body+match[4]

            modified = ROW.sub(replace_row, original)
            if seen != set(edits):
                raise ValueError('Could not locate every planned annotation cell')
            ET.fromstring(modified)
            if CELL.sub(lambda m: old_cells.get(m[1].decode(), m[0]), modified) != original:
                raise ValueError('Unexpected worksheet change')
            patched[member], reverse[member] = modified, old_cells
        with destination.open('xb') as stream, ZipFile(stream, 'w') as zout:
            zout.comment = zin.comment
            for info in zin.infolist():
                zout.writestr(info, patched.get(info.filename, zin.read(info.filename)))
    with ZipFile(source) as before, ZipFile(destination) as after:
        if before.namelist() != after.namelist() or after.testzip() is not None:
            raise ValueError('Workbook package verification failed')
        for member in before.namelist():
            data = after.read(member)
            if member in reverse:
                data = CELL.sub(lambda m: reverse[member].get(m[1].decode(), m[0]), data)
            if data != before.read(member):
                raise ValueError('Unplanned workbook package change')
    for name, edits in changes.items():
        reopened = read_sheet(destination, name)
        values = {c.coordinate: c.value for row in reopened.rows for c in row}
        if any(values.get(coord) != item['value'] for coord, item in edits.items()):
            raise ValueError('Reopened annotations differ from the plan')


def migrate(source, destination, selected, config):
    before = digest(source)
    changes = plan(source, selected, config)
    patch(source, destination, changes)
    if digest(source) != before:
        raise ValueError('Source changed during annotation migration')
    events = [{'sheet': name, 'cell': coord, 'field': item['field'], 'operation': item['operation']}
              for name, edits in changes.items() for coord, item in edits.items()]
    return {'source': str(source), 'source_sha256': before, 'output': str(destination),
            'output_sha256': digest(destination), 'changes': events,
            'operation_counts': dict(Counter(item['operation'] for item in events)),
            'verified': 'Reverse patches reproduce original ZIP members; reopened values agree; formulas, caches, numbers and actual IDs preserved.'}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    for name in ('retrospective', 'circall', 'donors'):
        parser.add_argument('--'+name, type=Path, required=True)
    parser.add_argument('--config', type=Path, default=ROOT/'configs/maintenance/sample_annotations.json')
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--adopt', action='store_true', help='Back up originals and adopt verified copies at the explicit source paths')
    args = parser.parse_args(argv)
    config = json.loads(args.config.read_text(), object_pairs_hook=unique_object)
    if config != json.loads((ROOT/'configs/maintenance/sample_annotations.json').read_text()):
        parser.error('Unsupported annotation settings')
    sources = {name: getattr(args, name).resolve() for name in config['selected_sheets']}
    if args.output_dir.exists() or any(p.is_symlink() for p in (args.output_dir, *args.output_dir.parents)):
        parser.error('Output directory must be fresh and not a symlink')
    if len(set(sources.values())) != len(sources):
        parser.error('Selected sources must be distinct')
    for name, source in sources.items():
        if source.with_name('~$'+source.name).exists():
            parser.error('Save and close the selected workbooks before migration')
        plan(source, config['selected_sheets'][name], config)
    args.output_dir.mkdir(parents=True)
    record = envelope('sample_annotations', config, {**sources, 'definitions': args.config},
                      [Path(__file__), ROOT/'analysis/utils/sample_definitions.py', Path(__file__).with_name('xlsx_patch.py'),
                       ROOT/'analysis/utils/sample_io.py', Path(__file__).with_name('workbook_cleanup.py'), ROOT/'analysis/provenance.py',
                       ROOT/'analysis/configuration.py'], ROOT/'environments/conda-linux-64.lock',
                      command=[sys.executable, '-m', 'analysis.maintenance.sample_annotations', *(argv if argv is not None else sys.argv[1:])])
    record.update(adopted=[], workbooks=[])
    for name, source in sources.items():
        backup = args.output_dir/name/'original.xlsx'
        backup.parent.mkdir()
        before = digest(source)
        shutil.copyfile(source, backup)
        if digest(backup) != before:
            raise ValueError('Source changed while backing up')
        result = migrate(source, backup.parent/source.name, config['selected_sheets'][name], config)
        result['backup'] = str(backup)
        record['workbooks'].append(result)
    write_json(args.output_dir/'annotation_report.json', record)
    # Prepare and verify all copies before adopting any of them.
    if args.adopt:
        for result in record['workbooks']:
            source = Path(result['source'])
            if source.with_name('~$'+source.name).exists() or digest(source) != result['source_sha256']:
                raise ValueError('Source reopened or changed; verified copies retained without adoption')
        for result in record['workbooks']:
            source = Path(result['source'])
            with tempfile.NamedTemporaryFile(dir=source.parent, prefix='.sample_annotations_', suffix='.xlsx', delete=False) as stream:
                staged = Path(stream.name)
            try:
                shutil.copyfile(result['output'], staged)
                if digest(staged) != result['output_sha256'] or digest(source) != result['source_sha256'] or source.with_name('~$'+source.name).exists():
                    raise ValueError('Source or staged copy changed; adoption stopped')
                staged.replace(source)
                if digest(source) != result['output_sha256']:
                    raise ValueError('Adopted source verification failed')
                record['adopted'].append(str(source))
                write_json(args.output_dir/'annotation_report.json', record)
            finally:
                staged.unlink(missing_ok=True)
    record['finished_utc'] = datetime.now(timezone.utc).isoformat()
    record['status'] = 'complete'
    write_json(args.output_dir/'annotation_report.json', record)
    print(json.dumps({'adopted_workbooks': len(record['adopted']), 'operation_counts': [r['operation_counts'] for r in record['workbooks']], 'report': str(args.output_dir/'annotation_report.json')}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
