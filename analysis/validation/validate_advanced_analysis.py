"""Aggregate acceptance checks for explicitly named Layer 3 standalone/master runs."""
import argparse
import csv
import io
import json
from pathlib import Path
import sys

import numpy as np
from openpyxl import load_workbook
from PIL import Image

from analysis.validation.artifact_checks import checked_index, matching_figures, scope_states, workflow_files
from analysis.steps.step_03_advanced_analysis import validate_results
from analysis.outputs import engine_directory
from analysis.provenance import ROOT, digest, utc_now, write_json
from analysis.utils.sample_io import read_sheet


def identifying_values(record):
    """Hold identifiers in memory; only counts ever leave the validator."""
    values = set()
    for cohort in record['cohorts']:
        scope = cohort['cohort']
        if scope not in ('retrospective', 'circall'):
            continue
        path = record['source_states'][scope]['path']
        config = record['resolved_settings']['association_definition']['cohorts'][scope]
        sheets = [config['sheet']]
        if scope == 'circall' and record['resolved_settings']['include_controls']:
            sheets.append('cohorte_control')
        for name in sheets:
            sheet = read_sheet(path, name)
            headers = [c.value for c in sheet.headers]
            for row in sheet.rows:
                for field, cell in zip(headers, row):
                    if field in ('patient_id', 'circall_id', 'sample_id', 'lastname', 'firstname', 'dob', 'private_note') and cell.value is not None:
                        value = str(cell.value).strip()
                        if len(value) >= 3 and value.casefold() not in ('none', 'nan', 'n/a'):
                            values.add(value)
    if 'retrospective_controls' in record['inputs']:
        sheet = read_sheet(record['inputs']['retrospective_controls']['path'], 'Feuil1')
        headers = [str(c.value).strip() if c.value is not None else None for c in sheet.headers]
        for row in sheet.rows:
            cell = row[headers.index('Donor')]
            if cell.value is not None:
                values.add(str(cell.value).strip())
    return values


def strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for item in value.values():
            yield from strings(item)
    elif isinstance(value, list):
        for item in value:
            yield from strings(item)


def validate_run(root):
    native = engine_directory(root, 'advanced_analysis')
    record = json.loads((native/'run_manifest.json').read_text())
    validate_results(native, record)
    for relative, expected in record['code_sha256'].items():
        if digest(ROOT/relative) != expected:
            raise ValueError('Executed code differs from current implementation')
    if digest(ROOT/record['scientific_contract']['path']) != record['scientific_contract']['sha256']:
        raise ValueError('Scientific contract changed after execution')
    if digest(ROOT/'environments/conda-linux-64.lock') != record['environment_lock_sha256']:
        raise ValueError('Environment lock changed after execution')
    index = checked_index(root)
    for artifact in index['artifacts']:
        if digest(root/artifact['path']) != artifact['sha256']:
            raise ValueError('Indexed artifact mismatch')
    for artifact in index['publications']:
        if digest(root/artifact['source']) != artifact['sha256'] or digest(root/artifact['path']) != artifact['sha256']:
            raise ValueError('Publication checksum mismatch')
        if not artifact['path'].endswith(('.xlsx', '.png', '.pdf')):
            raise ValueError('Unexpected Layer 3 publication')
    forbidden = identifying_values(record)
    checked = 0
    for path in workflow_files(root, 'advanced_analysis', index):
        if not path.is_file() or '.cache' in path.parts:
            continue
        exported = []
        if path.suffix == '.xlsx':
            b = load_workbook(path, read_only=True, data_only=False)
            try:
                exported = [c.value for sheet in b for row in sheet for c in row if isinstance(c.value, str)]
            finally:
                b.close()
        elif path.suffix == '.json':
            exported = list(strings(json.loads(path.read_text())))
        elif path.suffix == '.csv':
            exported = [v for row in csv.reader(io.StringIO(path.read_text())) for v in row]
        elif path.suffix == '.log':
            content = path.read_text()
            # Logs contain fixed messages and paths; match whole source tokens.
            if any(value in content for value in forbidden):
                raise ValueError('Identifying value in execution log')
        else:
            continue
        if any(value.strip() in forbidden for value in exported):
            raise ValueError('Identifying value in workbook or text export')
        checked += 1
    return record, dict(artifact_hashes=len(index['artifacts']), publication_hashes=len(index['publications']),
                        privacy_checked_exports=checked, privacy='passed', code_hashes=len(record['code_sha256']),
                        sources_unchanged=True, status=record['quality_status'])


def compare(standalone, master):
    left, right = Path(standalone), Path(master)
    a, checks_a = validate_run(left)
    b, checks_b = validate_run(right)
    if a['inputs'] != b['inputs'] or a['resolved_settings'] != b['resolved_settings']:
        raise ValueError('Sources/settings differ across named runs')
    roots = [engine_directory(p, 'advanced_analysis') for p in (left, right)]
    states = scope_states(a, 'association_status')
    if states != scope_states(b, 'association_status'):
        raise ValueError('Report scopes or completion states differ')
    scopes = [scope for scope, (report, _) in states.items() if report == 'complete']
    numerical = workbooks = pngs = 0
    for scope in scopes:
        for name in ('associations.json', 'observations.json', 'source_observations.json', 'model_diagnostics.json', 'integrity_findings.json'):
            paths = [p/scope/name for p in roots]
            if any(p.exists() for p in paths):
                if not all(p.exists() for p in paths) or json.loads(paths[0].read_text()) != json.loads(paths[1].read_text()):
                    raise ValueError('Native numerical evidence differs')
                numerical += 1
        paths = [p/scope/'associations.xlsx' for p in roots]
        books = [load_workbook(p, read_only=True, data_only=False) for p in paths]
        try:
            if books[0].sheetnames != books[1].sheetnames or any(list(books[0][s].values) != list(books[1][s].values) for s in books[0].sheetnames):
                raise ValueError('Workbook content differs')
        finally:
            for book in books:
                book.close()
        workbooks += 1
    for relative in matching_figures(*roots):
        path, other = roots[0]/relative, roots[1]/relative
        with Image.open(path) as x, Image.open(other) as y:
            if not np.array_equal(np.asarray(x), np.asarray(y)):
                raise ValueError('PNG pixels differ')
        pngs += 1
    coverage = {scope: json.loads((roots[0]/scope/'associations.json').read_text())['tables']['Coverage'] for scope in scopes}
    return dict(schema_version=1, status='passed', finished_utc=utc_now(), standalone=checks_a, master=checks_b,
                identical_numerical_files=numerical, identical_workbooks=workbooks, identical_pngs=pngs, coverage=coverage,
                limitations=['No Excel/LibreOffice rendering available', 'PDF structure checked; full PDF rendering unavailable',
                             'Implementation verification does not establish scientific validity or equivalence to older clinical outputs'])


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    p.add_argument('--baseline', '--standalone', dest='standalone', type=Path, required=True)
    p.add_argument('--candidate', '--master', dest='master', type=Path, required=True)
    p.add_argument('--report', type=Path, required=True)
    args = p.parse_args(argv)
    if args.report.exists() or any(v.is_symlink() for v in (args.report, *args.report.parents)):
        p.error('Fresh report destination required')
    try:
        result = compare(args.standalone, args.master)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        write_json(args.report, result)
        print(f"Layer 3 validation passed: {result['identical_workbooks']} workbooks, {result['identical_pngs']} PNGs")
        return 0
    except Exception as error:
        print(f'Layer 3 validation failed ({type(error).__name__}); clinical values omitted', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
