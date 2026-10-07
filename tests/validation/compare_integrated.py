"""Compare standalone and integrated results without printing source rows."""
import argparse
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]

from analysis.provenance import digest
from analysis.outputs import DIRECTORIES, engine_directory, manifest_path

IDENTITY_COLUMNS = {'record_id', 'sample_id', 'patient_id', 'circall_id', 'patient_key', 'sample_key',
                    'timepoint', 'bin_a', 'bin_b', 'timepoint_a', 'timepoint_b', 'term', 'sex', 'genetic_subtype'}


def compare_tables(left, right, rtol, atol):
    a = pd.read_csv(left, keep_default_na=False, dtype={key: str for key in IDENTITY_COLUMNS})
    b = pd.read_csv(right, keep_default_na=False, dtype={key: str for key in IDENTITY_COLUMNS})
    for key in set(a.columns) & set(b.columns) - IDENTITY_COLUMNS:
        if not pd.api.types.is_numeric_dtype(a[key]) or not pd.api.types.is_numeric_dtype(b[key]):
            ca, cb = pd.to_numeric(a[key], errors='coerce'), pd.to_numeric(b[key], errors='coerce')
            if ((a[key].eq('') | ca.notna()).all() and (b[key].eq('') | cb.notna()).all()):
                a[key], b[key] = ca, cb
    pd.testing.assert_frame_equal(a, b, check_exact=False, rtol=rtol, atol=atol)


def scientific_settings(record):
    settings = json.loads(json.dumps(record['resolved_settings']))
    if 'arguments' in settings:
        settings['arguments'].pop('output_dir', None)
        # Older canonical manifests included unused legacy-only CLI fields.
        if record['workflow'] == 'canonical':
            for key in ('stage', 'retrospective_workbook'):
                if settings['arguments'].get(key) is None:
                    settings['arguments'].pop(key, None)
    if record['workflow'] == 'blast_kinetics':
        settings['output'].pop('root', None)
    # Relocated configuration/source paths are identified by their retained hashes.
    sources = {str(value['path']): '<input:' + value['sha256'] + '>'
               for key, value in record['inputs'].items() if key != 'profile'}
    def normalize(value):
        if isinstance(value, dict):
            return {k: normalize(v) for k, v in value.items()}
        if isinstance(value, list):
            return [normalize(v) for v in value]
        return sources.get(value, value) if isinstance(value, str) else value
    return normalize(settings)


def workflow_directory(root, name):
    native = engine_directory(root, name)
    if native != root:
        return native
    if (root / name).is_dir():
        return engine_directory(root / name, name)
    if (root / DIRECTORIES[name]).is_dir():
        return engine_directory(root / DIRECTORIES[name], name)
    return root


def normalized_workbook(path):
    sheets = pd.read_excel(path, sheet_name=None)
    # Saved locations differ by definition; no scientific cell is normalized.
    for data in sheets.values():
        if {'item', 'description'}.issubset(data.columns):
            data.loc[data['item'].eq('Source run'), 'description'] = '<run-directory>'
    return sheets


def compare(standalone, integrated):
    standalone, integrated = Path(standalone), Path(integrated)
    manifest = json.loads(manifest_path(integrated).read_text())
    if manifest.get('status') != 'complete':
        raise ValueError('Integrated run is not complete')
    results = {}
    for workflow in manifest.get('workflows', [{'name': manifest['workflow']}]):
        name = workflow['name']
        left, right = workflow_directory(standalone, name), workflow_directory(integrated, name)
        extensions = {'.csv', '.xlsx', '.png', '.jpeg', '.jpg', '.pdf', '.txt'}
        before = {p.relative_to(left): p for p in left.rglob('*') if p.suffix in extensions and not any(v.startswith('.') for v in p.relative_to(left).parts)}
        after = {p.relative_to(right): p for p in right.rglob('*') if p.suffix in extensions and not any(v.startswith('.') for v in p.relative_to(right).parts)}
        result = {'missing': sorted(map(str, before.keys() - after.keys())), 'extra': sorted(map(str, after.keys() - before.keys())),
                  'tables': 0, 'sheets': 0, 'images': 0, 'pdfs': 0, 'model_summaries': 0, 'failures': [],
                  'rtol': 1e-10 if name == 'cfdna_associations' else 1e-9, 'atol': 1e-12}
        metadata_name = 'run_metadata.json' if name == 'blast_kinetics' else 'run_manifest.json'
        before_metadata = json.loads((left / metadata_name).read_text())
        after_metadata = json.loads((right / metadata_name).read_text())
        # A moved YAML profile changes bytes only through paths; its resolved
        # scientific contents are compared below. Biological sources stay exact.
        result['input_hashes_match'] = ({k: v['sha256'] for k, v in before_metadata['inputs'].items() if k != 'profile'} ==
                                        {k: v['sha256'] for k, v in after_metadata['inputs'].items() if k != 'profile'})
        result['scientific_settings_match'] = scientific_settings(before_metadata) == scientific_settings(after_metadata)
        for relative in sorted(before.keys() & after.keys()):
            try:
                if relative.suffix == '.csv':
                    # Preserve literal na identifiers and blank cells; infer numeric columns
                    # only through pandas consistently on both sides.
                    compare_tables(before[relative], after[relative], result['rtol'], result['atol'])
                    result['tables'] += 1
                elif relative.suffix == '.xlsx':
                    a, b = normalized_workbook(before[relative]), normalized_workbook(after[relative])
                    if list(a) != list(b):
                        raise ValueError('Workbook sheets differ')
                    for sheet in a:
                        pd.testing.assert_frame_equal(a[sheet], b[sheet], check_exact=False, rtol=result['rtol'], atol=result['atol'])
                        result['sheets'] += 1
                    result['tables'] += 1
                elif relative.suffix == '.pdf':
                    if before[relative].stat().st_size == 0 or after[relative].stat().st_size == 0:
                        raise ValueError('Empty PDF')
                    result['pdfs'] += 1
                elif relative.suffix == '.txt':
                    if before[relative].read_text() != after[relative].read_text():
                        raise ValueError('Statistical model summary differs')
                    result['model_summaries'] += 1
                else:
                    with Image.open(before[relative]) as a, Image.open(after[relative]) as b:
                        if a.size != b.size or not np.array_equal(np.asarray(a), np.asarray(b)):
                            raise ValueError('Image differs')
                    result['images'] += 1
            except Exception:
                # Pandas/model errors may embed clinical values; retain artifact names only.
                result['failures'].append(str(relative))
        if name == 'blast_kinetics':
            a = json.loads((left / 'cohort_summary.json').read_text())
            b = json.loads((right / 'cohort_summary.json').read_text())
            result['cohort_counts_match'] = a == b
        result['passed'] = not (result['missing'] or result['extra'] or result['failures']) and result.get('cohort_counts_match', True) and result['input_hashes_match'] and result['scientific_settings_match']
        results[name] = result
    return {'schema_version': 1, 'comparison_code_sha256': digest(Path(__file__)),
            'passed': all(r['passed'] for r in results.values()), 'workflows': results}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--standalone-dir', type=Path, required=True)
    parser.add_argument('--integrated-run', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args(argv)
    if args.report.exists():
        parser.error('Report already exists; choose a fresh path')
    try:
        result = compare(args.standalone_dir, args.integrated_run)
        args.report.parent.mkdir(parents=True, exist_ok=True)
        with args.report.open('x') as stream:
            stream.write(json.dumps(result, indent=2) + '\n')
        print(json.dumps(result, indent=2))
        return 0 if result['passed'] else 1
    except (ValueError, OSError, KeyError):
        print('Comparison failed: inspect run completeness and artifact sets; source rows omitted', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
