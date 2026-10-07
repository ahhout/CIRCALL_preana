"""Read-only equivalence and provenance checks for additional trend figures."""
import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from analysis.outputs import engine_directory
from analysis.provenance import digest, utc_now, write_json
from analysis.sample_analysis import longitudinal_trends, reporting
from analysis.sample_analysis.policies import PRIMARY, eligible


def require(condition, message):
    if not condition:
        raise ValueError(message)


def validate(reference, current):
    old = engine_directory(reference, 'canonical')
    new = engine_directory(current, 'canonical')
    original = json.loads((old/'run_manifest.json').read_text())
    manifest = json.loads((new/'run_manifest.json').read_text())
    require(manifest['status'] == 'complete', 'New engine is incomplete')
    require(json.loads((current/'.audit/run_manifest.json').read_text())['status'] == 'complete', 'Publication is incomplete')
    for name, source in manifest['inputs'].items():
        require(source['sha256'] == original['inputs'][name]['sha256'] == digest(source['path']), 'Source hashes differ')
    # All retained original longitudinal figures/tables, not just selected results.
    unchanged = []
    for path in sorted((old/'longitudinal').rglob('*')):
        if path.is_file():
            relative = path.relative_to(old)
            require((new/relative).is_file() and digest(path) == digest(new/relative), f'Existing longitudinal artifact differs: {relative}')
            unchanged.append(str(relative))
    pooled = ['timepoint_counts', 'paired_counts', 'welch_sample', 'welch_patient_median',
              'mannwhitney_patient_median', 'mixed_contrasts', 'primary_contrasts']
    for name in pooled:
        require(digest(old/f'pooled/{name}.csv') == digest(new/f'pooled/{name}.csv'), f'Pooled statistics differ: {name}')
    args = manifest['arguments']
    cohorts = ['retrospective', 'circall'] if args['cohort'] == 'all' else [args['cohort']]
    frame = pd.read_csv(new/'prepared/inventory.csv', low_memory=False)
    saved = pd.read_csv(new/'longitudinal/trendline_summary.csv', keep_default_na=False)
    for field in ['ci95_low', 'ci95_high']:
        saved[field] = pd.to_numeric(saved[field], errors='coerce')
    _, repeated = longitudinal_trends.summarize(frame, cohorts, diagnosis_as_d1=args['plot_diagnosis_as_d1'],
        resamples=args['trend_bootstrap_resamples'], seed=args['trend_bootstrap_seed'], method=args['trend_bootstrap_method'])
    pd.testing.assert_frame_equal(saved, repeated, check_exact=False, rtol=1e-12, atol=1e-12)
    # Independent raw-scale aggregation mirrors the original box input contract.
    for cohort in cohorts:
        data, _ = eligible(frame, cohort, 'longitudinal')
        data = reporting.plot_data(data, diagnosis_as_d1=args['plot_diagnosis_as_d1'])
        medians = data.groupby(['patient_key', 'plot_timepoint'])[PRIMARY].median()
        for tp, group in medians.groupby(level='plot_timepoint'):
            row = saved.loc[saved.cohort.eq(cohort) & saved.plot_timepoint.eq(tp)].iloc[0]
            require(row.n_patients == len(group) and np.isclose(row['median'], group.median(), rtol=1e-12), 'Box medians/counts differ')
    sparse = saved.loc[saved.cohort.eq('circall') & saved.plot_timepoint.eq('TP2 (D71)')]
    require(sparse[['ci95_low', 'ci95_high']].isna().all().all(), 'CIRCALL TP2 must not have an interval')
    indexed = {}
    for root in (reference, current):
        records = json.loads((root/'.audit/artifact_index.json').read_text())['artifacts']
        for entry in records:
            require(digest(root/entry['path']) == entry['sha256'], 'Indexed artifact hash mismatch')
        indexed[str(root)] = len(records)
    root_manifest = json.loads((current/'.audit/run_manifest.json').read_text())
    for item in root_manifest['publications']:
        require(digest(current/item['path']) == digest(current/item['source']) == item['sha256'], 'Publication hash mismatch')
    require(manifest['plot_settings']['longitudinal_trends'] == json.loads((new/'longitudinal/trendline_settings.json').read_text()), 'Recorded trend settings disagree')
    return dict(unchanged_longitudinal_artifacts=len(unchanged), unchanged_pooled_statistical_tables=len(pooled),
                cohort_visit_medians_and_counts_verified=len(saved), bootstrap_reproduced=True,
                original_and_new_indexed_hashes_verified=indexed, publication_hashes_verified=len(root_manifest['publications']),
                source_hashes_verified=len(manifest['inputs']), circall_tp2_interval_omitted=True)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference-run', required=True, type=Path)
    parser.add_argument('--run-dir', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args(argv)
    if args.output.exists():
        parser.error('Report already exists; choose a fresh path')
    report = dict(started_utc=utc_now(), reference_run=str(args.reference_run), run_dir=str(args.run_dir))
    try:
        report.update(validate(args.reference_run, args.run_dir), status='passed')
    except Exception:
        report.update(status='failed', finished_utc=utc_now())
        args.output.parent.mkdir(parents=True, exist_ok=True)
        write_json(args.output, report)
        raise
    report['finished_utc'] = utc_now()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    write_json(args.output, report)
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
