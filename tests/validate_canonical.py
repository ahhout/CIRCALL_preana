"""Local integration checks against source cells; never prints patient records."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
import warnings

import numpy as np
import pandas as pd
from openpyxl import load_workbook

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def number(value):
    try:
        x=float(str(value).strip().replace(',','.'))
        return x if math.isfinite(x) else None
    except (TypeError,ValueError):return None


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir',type=Path,required=True)
    args=parser.parse_args();base=args.run_dir
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
            book=load_workbook(path,read_only=True,data_only=True)
            formula_book=load_workbook(path,read_only=True,data_only=False)
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
        assert (pd.isna(actual) if expected is None else math.isclose(actual,expected,rel_tol=1e-9,abs_tol=1e-12)), 'Primary endpoint differs from independent source calculation'
        compared+=1
    corrected={'30443_cf':12.,'33541_cf':66.5/2.25,'33532_cf':57/7,'33990_cf':2155/4,'6702608804':1.8}
    for sample,expected in corrected.items():
        rows=primary_rows.loc[primary_rows.sample_id.eq(sample)]
        assert len(rows)==1 and math.isclose(rows[metric].iloc[0],expected,rel_tol=1e-9), 'Corrected reference sample changed'
    missing=primary_rows.loc[primary_rows.cohort.eq('circall') & primary_rows.sample_state.eq('present') & primary_rows.dna_total_ng_status.eq('formula_zero_missing_inputs')]
    assert len(missing)==13 and missing[metric].isna().all()
    assert primary_rows.loc[primary_rows.cohort.eq('circall') & primary_rows.sample_state.eq('present'),metric].dropna().gt(0).all()
    pellet=frame.loc[frame.source.eq('retrospective') & frame.record_id.str.endswith(':MNC')]
    assert len(pellet)>0 and pellet.volume_ml.isna().all() and pellet[metric].isna().all()
    controls=pd.read_csv(base/'prepared/pooled_controls.csv')
    assert len(controls)==13 and controls.patient_key.nunique()==13
    assert controls.control_source.value_counts().to_dict()=={'existing_controls':9,'pediatric_controls':4}
    assert not {'lastname','firstname','dob'} & set(frame.columns)
    for cohort in ('retrospective','circall'):
        mixed=pd.read_csv(base/f'longitudinal/{cohort}/mixed_contrasts.csv')
        assert set(mixed.cohort)=={cohort} and np.isfinite(mixed.p_adj).all()
        counts=pd.read_csv(base/f'longitudinal/{cohort}/timepoint_counts.csv')
        assert counts.loc[counts.timepoint.eq('Control'),'n_observations'].item()==13
    corr=pd.read_csv(base/'yield/correlations.csv')
    assert set(corr.cohort)=={'retrospective','circall'}
    manifest=json.loads((base/'run_manifest.json').read_text())
    assert manifest['status']=='complete'
    hashes=json.loads((ROOT/'outputs/canonical_validation/source_integrity_initial.json').read_text())
    assert all(hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==digest for path,digest in hashes.items())
    result={'source_endpoints_checked':compared,'corrected_reference_samples':5,'excluded_formula_zero_samples':13,
            'pooled_controls':13,'pellet_records_without_plasma_volume':len(pellet),'separate_cohort_models':True,
            'source_files_unchanged':True,'passed':True}
    (base/'validation.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result,indent=2))


if __name__=='__main__':main()
