"""Local integration checks against source cells; never prints patient records."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
import warnings
from datetime import datetime, timezone

import numpy as np
import pandas as pd
from openpyxl import load_workbook

ROOT=Path(__file__).resolve().parents[2]



def source_path(path):
    """Resolve source paths from before the folder reorganisation."""
    path = Path(path)
    relative = path.relative_to(ROOT) if path.is_absolute() and path.is_relative_to(ROOT) else path
    relocated = {
        Path('cfDNA_inventaire_retrospective.xlsx'): 'input/cfDNA_inventaire_retrospective.xlsx',
        Path('inventaire_CIRCALL_15092026.xlsx'): 'input/inventaire_CIRCALL_15092026.xlsx',
        Path('data/retrospective/cfDNA_donors.xlsx'): 'input/cfDNA_donors.xlsx',
        Path('data/retrospective/cfDNA_inventaire_2025.xlsx'): 'archive/input/retrospective/cfDNA_inventaire_2025.xlsx',
        Path('data/circall/inventaire_CIRCALL_ano_07092026.xlsx'): 'archive/input/circall/inventaire_CIRCALL_ano_07092026.xlsx',
    }
    return ROOT / relocated.get(relative, relative)


def number(value):
    try:
        x=float(str(value).strip().replace(',','.'))
        return x if math.isfinite(x) else None
    except (TypeError,ValueError):return None


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate_run(base, baseline=None):
    """Reusable source-cell invariants; historical expectations are explicitly opt-in."""
    from analysis.outputs import engine_directory
    base = engine_directory(base, 'canonical')
    manifest = json.loads((base / 'run_manifest.json').read_text())
    require(manifest['status'] == 'complete', 'Run is not complete')
    for source in manifest['inputs'].values():
        path = source_path(source['path'])
        require(path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == source['sha256'],
                'A run source is unavailable or has changed')
    frame=pd.read_csv(base/'prepared/inventory.csv',keep_default_na=False)
    metric='dna_ng_per_mL_plasma'
    # Numerical comparisons use nullable values, while identifiers retain literal text.
    for field in [metric,'volume_ml','dna_total_ng','dna_concentration_ng_per_uL','elution_volume_uL']:
        frame[field]=pd.to_numeric(frame[field],errors='coerce')
    primary_rows=frame.loc[frame.compartment.eq('plasma')]
    sources={}
    for path in primary_rows.source_file.unique():
        with warnings.catch_warnings():
            warnings.filterwarnings('ignore',message='Data Validation extension is not supported')
            book=load_workbook(source_path(path),read_only=True,data_only=True)
            formula_book=load_workbook(source_path(path),read_only=True,data_only=False)
            for name in book.sheetnames:
                if name not in set(primary_rows.source_sheet):continue
                ws=book[name];fw=formula_book[name]
                headers=[str(c.value).strip() if c.value is not None else '' for c in next(ws.iter_rows())]
                sources[(path,name)]={i:(dict(zip(headers,[c.value for c in row])),dict(zip(headers,[c.value for c in fr])))
                    for i,(row,fr) in enumerate(zip(ws.iter_rows(min_row=2),fw.iter_rows(min_row=2)),2)}
            book.close();formula_book.close()
    compared=0
    for row in primary_rows.itertuples():
        cells,formulas=sources[(row.source_file,row.source_sheet)][row.source_row]
        if row.source=='existing_controls':
            expected=number(cells['Conc ng/mL  plasma'])
        else:
            total=number(cells.get('dna_total_ng'));volume=number(cells.get('volume_ml'))
            if total==0 and str(formulas.get('dna_total_ng','')).startswith('='):
                if number(cells.get('dna_concentration_ng_per_uL')) is None or number(cells.get('elution_volume_uL')) is None:total=None
            expected=total/volume if total is not None and volume is not None and volume>0 else None
        actual=getattr(row,metric)
        require(pd.isna(actual) if expected is None else math.isclose(actual,expected,rel_tol=1e-9,abs_tol=1e-12),
                'Primary endpoint differs from independent source calculation')
        compared+=1
    missing=primary_rows.loc[primary_rows.cohort.eq('circall') & primary_rows.sample_state.eq('present') & primary_rows.dna_total_ng_status.eq('formula_zero_missing_inputs')]
    require(missing[metric].isna().all(), 'Formula-zero missingness did not propagate')
    pellet=frame.loc[frame.source.eq('retrospective') & frame.record_id.str.endswith(':MNC')]
    require(pellet.volume_ml.isna().all() and pellet[metric].isna().all(), 'Plasma volume leaked into retrospective MNC records')
    controls=pd.read_csv(base/'prepared/pooled_controls.csv')
    require(not {'lastname','firstname','dob'} & set(frame.columns), 'Prepared schema exposes name/identity components')
    for cohort in ('retrospective','circall'):
        path = base/f'longitudinal/{cohort}/mixed_contrasts.csv'
        if path.is_file():
            mixed=pd.read_csv(path)
            require(set(mixed.cohort)=={cohort} and np.isfinite(mixed.p_adj).all(), 'Invalid cohort model results')
            counts=pd.read_csv(base/f'longitudinal/{cohort}/timepoint_counts.csv')
            positive_controls = pd.to_numeric(controls[metric], errors='coerce').gt(0).sum()
            require(counts.loc[counts.timepoint.eq('Control'),'n_observations'].item()==positive_controls,
                    'Model control count differs from prepared positive controls')
    result={'schema_version': 1, 'source_endpoints_checked':compared,
            'excluded_formula_zero_samples':len(missing), 'pooled_controls':len(controls),
            'pellet_records_without_plasma_volume':len(pellet), 'source_files_unchanged':True, 'passed':True}
    if baseline is not None:
        check_baseline(manifest, result, json.loads(Path(baseline).read_text()))
        result['baseline_expectations_checked'] = True
    return result


def check_baseline(manifest, result, expectations):
    require(expectations.get('schema_version') == 1, 'Unsupported baseline schema')
    hashes = {key: value['sha256'] for key, value in manifest['inputs'].items()}
    require(hashes == expectations.get('input_sha256'), 'Unfamiliar source revision: baseline expectations require review')
    for key, expected in expectations.get('counts', {}).items():
        require(key in result and result[key] == expected, 'Historical baseline count changed')


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir',type=Path,required=True)
    parser.add_argument('--baseline-expectations', type=Path, help='Reviewed local baseline JSON pinned to exact run input hashes')
    parser.add_argument('--output', type=Path, help='Fresh report path; existing reports are never overwritten')
    args=parser.parse_args(argv)
    output = args.output or ROOT/'output'/datetime.now(timezone.utc).strftime('canonical_validation_%Y%m%dT%H%M%S.%fZ.json')
    try:
        if output.exists():
            raise ValueError('Validation report already exists; choose a fresh path')
        result = validate_run(args.run_dir, args.baseline_expectations)
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open('x') as stream:
            stream.write(json.dumps(result, indent=2) + '\n')
        print(json.dumps(result, indent=2))
        return 0
    except (ValueError, OSError, KeyError):
        print('Validation failed: inspect source integrity, source-cell invariants and reviewed baseline expectations; raw values omitted', file=sys.stderr)
        return 1


if __name__=='__main__':raise SystemExit(main())
