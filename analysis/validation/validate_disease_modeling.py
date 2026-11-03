"""Compare named Layer 4 reports, including deliberately blocked cohort outcomes."""
import argparse
import json
from pathlib import Path
import sys

import numpy as np
from openpyxl import load_workbook
from PIL import Image

from analysis.validation.artifact_checks import checked_index, matching_figures, scope_states, workflow_files
from analysis.disease_modeling.runner import validate_results
from analysis.outputs import engine_directory
from analysis.provenance import ROOT, digest, utc_now, write_json
from analysis.sample_io import read_sheet


def text_values(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        if {'subject_hash', 'patient_key', 'measured_fraction', 'upper_bound_fraction', 'reported_sensitivity_fraction', 'source_dates'} & value.keys():
            raise ValueError('Clinical observation fields in exported aggregate evidence')
        for v in value.values():
            yield from text_values(v)
    elif isinstance(value, list):
        for v in value:
            yield from text_values(v)


def private_values(record):
    result = set()
    settings = record['resolved_settings']['arguments']
    chosen = [c for c in ('retrospective', 'circall') if settings['cohort'] in ('all', c)]
    for cohort in chosen:
        config = record['resolved_settings']['disease_definition']
        roles = [(cohort, [config['mrd'][cohort]['sheet']])]
        if cohort == 'circall' and settings['include_controls']:
            roles[0][1].append('cohorte_control')
        if settings['analysis'] != 'mrd':
            roles.append((cohort+'_counts', list(config['counts'][cohort]['sheets'])))
        if cohort == 'retrospective' and settings['include_controls'] and settings.get('donors'):
            roles.append(('retrospective_controls', ['Feuil1']))
        for role, sheets in roles:
            source = record['source_states'][role]
            if source['availability'] != 'readable':
                continue
            for sheet in sheets:
                data = read_sheet(source['path'], sheet)
                headers = [str(h.value).strip() if h.value is not None else None for h in data.headers]
                for row in data.rows:
                    for field, cell in zip(headers, row):
                        if field in ('lastname', 'firstname', 'dob', 'patient_id', 'circall_id', 'sample_id', 'Donor') and cell.value is not None:
                            value = str(cell.value).strip()
                            if len(value) >= 3 and value.casefold() not in ('none', 'nan', 'n/a'):
                                result.add(value)
    return result


def inspect_run(root):
    native = engine_directory(root, 'disease_modeling')
    record = json.loads((native/'run_manifest.json').read_text())
    validate_results(native, record)
    if any(digest(ROOT/p) != hashed for p, hashed in record['code_sha256'].items()):
        raise ValueError('Executed retained code differs from current files')
    if digest(ROOT/record['scientific_contract']['path']) != record['scientific_contract']['sha256']:
        raise ValueError('Scientific contract changed after execution')
    if digest(ROOT/'environments/conda-linux-64.lock') != record['environment_lock_sha256']:
        raise ValueError('Environment lock changed after execution')
    index = checked_index(root)
    for a in index['artifacts']:
        if digest(root/a['path']) != a['sha256']:
            raise ValueError('Indexed disease artifact mismatch')
    for a in index['publications']:
        if digest(root/a['path']) != digest(root/a['source']) or digest(root/a['path']) != a['sha256']:
            raise ValueError('Disease publication mismatch')
    forbidden = private_values(record)
    checked = 0
    for path in workflow_files(root, 'disease_modeling', index):
        if not path.is_file() or '.cache' in path.parts:
            continue
        values = []
        if path.suffix == '.json':
            values = list(text_values(json.loads(path.read_text())))
        elif path.suffix == '.xlsx':
            book = load_workbook(path, read_only=True, data_only=False)
            try:
                values = [c.value for sheet in book for row in sheet for c in row if isinstance(c.value, str)]
            finally:
                book.close()
        elif path.suffix == '.log':
            if any(v in path.read_text() for v in forbidden):
                raise ValueError('Identifying value in disease execution log')
        elif path.suffix == '.csv':
            raise ValueError('Unexpected disease row/table CSV export')
        else:
            continue
        if any(v.strip() in forbidden for v in values):
            raise ValueError('Identifying value in aggregate workbook or metadata')
        checked += 1
    return record, dict(artifact_hashes=len(index['artifacts']), publications=len(index['publications']),
                        privacy_checked_exports=checked, privacy='passed', source_reconciliation='passed',
                        code_hashes=len(record['code_sha256']), quality_status=record['quality_status'])


def compare(left, right):
    records, checks = [], []
    for path in (left, right):
        r, check = inspect_run(path)
        records.append(r)
        checks.append(check)
    if records[0]['inputs'] != records[1]['inputs'] or records[0]['resolved_settings'] != records[1]['resolved_settings']:
        raise ValueError('Disease source/settings differ between runs')
    native = [engine_directory(p, 'disease_modeling') for p in (left, right)]
    states = scope_states(records[0], 'disease_status')
    if states != scope_states(records[1], 'disease_status'):
        raise ValueError('Disease report scopes or completion states differ')
    scopes = [scope for scope, (report, _) in states.items() if report == 'complete']
    evidence = png_n = 0
    reports = {}
    for scope in scopes:
        for name in ('disease_modeling.json', 'integrity_findings.json'):
            paths = [p/scope/name for p in native]
            if any(p.exists() for p in paths):
                if not all(p.exists() for p in paths) or json.loads(paths[0].read_text()) != json.loads(paths[1].read_text()):
                    raise ValueError('Disease aggregate evidence differs')
                evidence += 1
        books = [load_workbook(p/scope/'disease_modeling.xlsx', read_only=True, data_only=False) for p in native]
        try:
            if books[0].sheetnames != books[1].sheetnames or any(list(books[0][s].values) != list(books[1][s].values) for s in books[0].sheetnames):
                raise ValueError('Disease workbook content differs')
        finally:
            for book in books:
                book.close()
        r = json.loads((native[0]/scope/'disease_modeling.json').read_text())
        reports[scope] = dict(status=r['status'], summary=r['summary'], blocking=r['blocking'], mrd=r['tables']['MRD'], counts=r['tables']['Counts'])
    for relative in matching_figures(*native):
        path, other = native[0]/relative, native[1]/relative
        with Image.open(path) as a, Image.open(other) as b:
            if not np.array_equal(np.asarray(a), np.asarray(b)):
                raise ValueError('Disease PNG pixels differ')
        png_n += 1
    return dict(schema_version=1, status='passed', finished_utc=utc_now(), checks=checks,
                identical_workbooks=len(scopes), identical_evidence_files=evidence, identical_pngs=png_n,
                reports=reports, limitations=['Excel/LibreOffice rendering unavailable', 'PDF structure checked; full rendering unavailable',
                                             'Clinical source failures remain explicitly blocked; numerical verification does not establish scientific validity'])


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    p.add_argument('--baseline', '--standalone', dest='standalone', type=Path, required=True)
    p.add_argument('--candidate', '--master', dest='master', type=Path, required=True)
    p.add_argument('--report', type=Path, required=True)
    a = p.parse_args(argv)
    if a.report.exists() or any(v.is_symlink() for v in (a.report, *a.report.parents)):
        p.error('Fresh validation report required')
    try:
        result = compare(a.standalone, a.master)
        a.report.parent.mkdir(parents=True, exist_ok=True)
        write_json(a.report, result)
        print(f"Layer 4 verification passed: {result['identical_workbooks']} workbooks, {result['identical_pngs']} PNGs")
        return 0
    except Exception as error:
        print(f'Layer 4 verification failed ({type(error).__name__}); clinical values omitted', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
