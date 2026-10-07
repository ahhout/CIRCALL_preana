"""Compare preserved and imported engines locally without reporting clinical records."""
import argparse
from dataclasses import asdict
import importlib.util
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd

from analysis.provenance import digest
from analysis.cfdna_associations import analyze_blast_cfdna as imported


def require(condition, message):
    if not condition:
        raise ValueError(message)


def compare_tables(left, right, label):
    require(list(left.columns) == list(right.columns) and left.shape == right.shape,
            f'{label}: table structure differs')
    for column in left:
        a, b = left[column], right[column]
        if pd.api.types.is_numeric_dtype(a) and pd.api.types.is_numeric_dtype(b):
            equal = np.isclose(a.to_numpy(dtype=float), b.to_numpy(dtype=float),
                               rtol=1e-10, atol=1e-12, equal_nan=True).all()
        else:
            equal = a.equals(b)
        require(equal, f'{label}: values differ in column {column}')


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--original', type=Path, required=True)
    parser.add_argument('--inventory', type=Path, required=True)
    parser.add_argument('--integrated-run', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True, help='New validation directory')
    args = parser.parse_args(argv)
    args.output_dir.mkdir(parents=True, exist_ok=False)
    # Do not create bytecode or any other files in the original repository.
    sys.dont_write_bytecode = True
    source_hash = digest(args.inventory)
    spec = importlib.util.spec_from_file_location('original_cfdna_engine', args.original)
    original = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = original
    spec.loader.exec_module(original)
    require(digest(args.original) == digest(Path(imported.__file__)), 'Engine code differs')
    require([asdict(p) for p in original.PREDICTORS] == [asdict(p) for p in imported.PREDICTORS],
            'Predictor settings differ')
    old_data = original.load_dataset(args.inventory, 'Inventaire')
    new_data = imported.load_dataset(args.inventory, 'Inventaire')
    require(old_data.equals(new_data), 'Loaded source rows differ')
    old_cohort, old_counts = original.prepare_cohort(old_data, original.CohortConfig())
    new_cohort, new_counts = imported.prepare_cohort(new_data, imported.CohortConfig())
    require(old_cohort.equals(new_cohort), 'Cohort membership, ordering or aggregation differs')
    require(old_counts == new_counts, 'Cohort counts differ')
    for old_predictor, new_predictor in zip(original.PREDICTORS, imported.PREDICTORS, strict=True):
        old_analysis = original.prepare_analysis_data(old_cohort, old_predictor)
        new_analysis = imported.prepare_analysis_data(new_cohort, new_predictor)
        require(old_analysis.equals(new_analysis), 'Predictor-specific observations differ')
        _, old_result = original.fit_regression(old_analysis, old_predictor)
        _, new_result = imported.fit_regression(new_analysis, new_predictor)
        compare_tables(old_result, new_result, new_predictor.variable)
    baseline = args.output_dir / 'original_outputs'
    original.write_outputs(baseline, old_cohort, old_counts, overwrite=False)
    from analysis.outputs import engine_directory
    native = engine_directory(args.integrated_run, 'cfdna_associations')
    actual = native / 'cfdna_associations'
    reference_files = {p.relative_to(baseline) for p in baseline.rglob('*') if p.is_file()}
    actual_files = {p.relative_to(actual) for p in actual.rglob('*') if p.is_file()}
    require(reference_files == actual_files, 'Output file sets differ')
    for relative in sorted(reference_files):
        if relative.suffix == '.csv':
            compare_tables(pd.read_csv(baseline / relative), pd.read_csv(actual / relative), str(relative))
        elif relative.suffix == '.png':
            require((actual / relative).stat().st_size > 0, 'Empty plot')
    require(digest(args.inventory) == source_hash, 'Input changed')
    manifest = json.loads((native / 'run_manifest.json').read_text())
    require(manifest['status'] == 'complete', 'Integrated run did not complete')
    require(manifest['inputs']['inventory']['sha256'] == source_hash, 'Integrated source differs')
    result = {'status': 'passed', 'source_sha256': source_hash, 'engine_sha256': digest(args.original),
              'cohort_membership': 'exact', 'predictor_observations': 'exact', 'counts': old_counts,
              'csv_files_compared': sum(p.suffix == '.csv' for p in reference_files),
              'plots_present': sum(p.suffix == '.png' for p in reference_files),
              'rtol': 1e-10, 'atol': 1e-12, 'input_unchanged': True}
    (args.output_dir / 'comparison.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({key: value for key, value in result.items() if key != 'counts'}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
