"""Add a descriptive pooled companion to a retained longitudinal run."""
import argparse
import json
from pathlib import Path
import shutil

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from analysis.outputs import engine_directory
from analysis.provenance import ROOT, digest, envelope, utc_now, write_json, verify_inputs
from analysis.sample_analysis import longitudinal_trends as trends, reporting
from analysis.sample_analysis.policies import PRIMARY, pooled_controls


def write(frame, output, settings):
    """Write the canonical pooled view using the established companion method."""
    output = Path(output)
    settings = dict(settings)
    settings.update(pooling='Concatenate cohort-qualified patient/visit medians; no identity linkage',
                    bootstrap_unit='Whole patient history across the pooled population',
                    seed_streams='Direct default_rng(seed)',
                    interval_omissions=['TP2 (preserve sparse CIRCALL display restriction)', 'Fewer than two patients'])
    patients, _ = trends.summarize(frame, ['retrospective', 'circall'],
                                  diagnosis_as_d1=settings['diagnosis_as_d1'],
                                  resamples=settings['resamples'], seed=settings['seed'], method=settings['method'])
    pooled = pd.concat([data.assign(cohort=cohort) for cohort, data in patients.items()], ignore_index=True)
    order = [tp for tp in reporting.PLOT_TIMEPOINTS if tp in set(pooled.plot_timepoint)]
    matrix = pooled.pivot(index=['cohort', 'patient_key'], columns='plot_timepoint', values=PRIMARY).reindex(columns=order).sort_index()
    draws = trends.bootstrap_medians(matrix.to_numpy(), resamples=settings['resamples'], seed=settings['seed'])
    rows = []
    for j, tp in enumerate(order):
        values = matrix[tp].dropna()
        valid = draws[:, j][np.isfinite(draws[:, j])]
        reason = 'TP2 sparse-follow-up display rule' if tp == reporting.PLOT_LABELS['tp2'] else 'Fewer than two patients' if len(values) < 2 else ''
        low, high = np.quantile(valid, [.025, .975]) if len(valid) and not reason else (np.nan, np.nan)
        rows.append(dict(plot_timepoint=tp, n_patients=len(values), median=values.median(), ci95_low=low, ci95_high=high,
                         bootstrap_valid_draws=len(valid), bootstrap_empty_draws=len(draws)-len(valid), interval_omission=reason))
    summary = pd.DataFrame(rows, columns=['plot_timepoint', 'n_patients', 'median', 'ci95_low', 'ci95_high',
                                          'bootstrap_valid_draws', 'bootstrap_empty_draws', 'interval_omission'])
    # Independent aggregation verifies the plotted pooled statistic and denominator.
    for row in summary.itertuples():
        values = pooled.loc[pooled.plot_timepoint.eq(row.plot_timepoint), PRIMARY]
        assert len(values) == row.n_patients and np.isclose(values.median(), row.median)
    controls = pooled_controls(frame)
    controls = controls.loc[np.isfinite(controls[PRIMARY]) & controls[PRIMARY].gt(0), PRIMARY].to_numpy()
    visits = (['Control'] if len(controls) else []) + order
    positions = {tp: i for i, tp in enumerate(visits)}
    fig, ax = plt.subplots(figsize=(12, 6))
    rng = np.random.default_rng(42)
    if len(controls):
        ax.scatter(rng.uniform(-.08, .08, len(controls)), controls, color=reporting.COLORS['control'], s=18, alpha=.65, label='Pooled controls')
        ax.plot([-.15, .15], [np.median(controls)]*2, color=reporting.COLORS['control'], lw=2)
    for cohort, data in patients.items():
        ax.scatter(data.plot_timepoint.map(positions).to_numpy()+rng.uniform(-.07, .07, len(data)), data[PRIMARY],
                   color=reporting.COLORS[cohort], s=18, alpha=.4, label=cohort.capitalize())
    x = summary.plot_timepoint.map(positions).to_numpy(dtype=float)
    ax.plot(x, summary['median'], color='#303030', marker='o', lw=2, label='Pooled median', zorder=4)
    ax.fill_between(x, summary.ci95_low.to_numpy(float), summary.ci95_high.to_numpy(float), color='#606060', alpha=.2, linewidth=0)
    for row in summary.loc[summary.interval_omission.ne('')].itertuples():
        ax.annotate('no CI', (positions[row.plot_timepoint], row.median), xytext=(0,-20), textcoords='offset points', ha='center', fontsize=8)
    counts = summary.set_index('plot_timepoint').n_patients.to_dict()
    counts['Control'] = len(controls)
    ax.set_xticks(range(len(visits)), [f'{tp}\nn={counts[tp]}' for tp in visits])
    reporting.format_log_yaxis(ax)
    if not visits:
        ax.set_ylim(.1, 10)
        ax.text(.5, .5, 'Measurement unavailable', ha='center', transform=ax.transAxes)
    ax.set_ylabel(reporting.LABELS[PRIMARY])
    ax.set_xlabel('Visit categories (spacing does not represent elapsed time)')
    ax.set_title('Pooled median DNA across visits — pointwise 95% bootstrap intervals')
    ax.legend(frameon=False)
    ax.grid(axis='y', alpha=.2)
    fig.text(.5, .015, 'Dots: patient/visit medians; one line connects pooled visit medians (not a fitted trajectory).\n'
             'Whole patients resampled; observed visits only. Cohort composition varies by visit; visit windows may differ.\n'
             'TP2 interval omitted under the sparse-follow-up display rule; controls remain a separate reference.', ha='center', fontsize=8)
    fig.tight_layout(rect=(0, .12, 1, 1))
    output.mkdir(parents=True, exist_ok=True)
    reporting.save(fig, output/'trendlines_pooled.png')
    summary.to_csv(output/'pooled_trendline_summary.csv', index=False)
    write_json(output/'pooled_trendline_settings.json', settings)
    return summary, settings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir', required=True, type=Path)
    args = parser.parse_args()
    root = args.run_dir.resolve()
    source = engine_directory(root, 'canonical')
    settings_path = source/'longitudinal/trendline_settings.json'
    settings = json.loads(settings_path.read_text())
    audit = root/'.audit/supplements/pooled_trend'
    destination = root/'sample_analysis/longitudinal/trendlines_pooled.png'
    if audit.exists() or destination.exists():
        parser.error('Pooled companion already exists; refusing replacement')
    original = {p: digest(p) for p in root.rglob('*') if p.is_file()}
    settings.update(pooling='Concatenate cohort-qualified patient/visit medians; no identity linkage',
                    bootstrap_unit='Whole patient history across the pooled population',
                    seed_streams='Direct default_rng(seed)',
                    interval_omissions=['TP2 (preserve sparse CIRCALL display restriction)', 'Fewer than two patients'])
    record = envelope('canonical', settings,
                      {'prepared': source/'prepared/inventory.csv', 'source_settings': settings_path},
                      [Path(__file__), ROOT/'analysis/sample_analysis/longitudinal_trends.py',
                       ROOT/'analysis/sample_analysis/reporting.py', ROOT/'analysis/sample_analysis/policies.py'],
                      ROOT/'environments/conda-linux-64.lock')
    frame = pd.read_csv(source/'prepared/inventory.csv', low_memory=False)
    summary, settings = write(frame, audit, settings)
    verify_inputs(record['inputs'])
    assert all(digest(p) == value for p, value in original.items()), 'An original artifact changed'
    assert plt.imread(audit/'trendlines_pooled.png').size > 0
    shutil.copy2(audit/'trendlines_pooled.png', destination)
    record.update(status='complete', finished_utc=utc_now(), validation={'pooled_medians_and_counts': len(summary), 'original_files_unchanged': len(original), 'png_decoded': True},
                  publications=[{'path': str(destination.relative_to(root)), 'source': str((audit/'trendlines_pooled.png').relative_to(root)), 'sha256': digest(destination)}],
                  artifacts={p.name: digest(p) for p in audit.iterdir() if p.is_file()})
    write_json(audit/'manifest.json', record)
    print(f'Created {destination}; verified {len(summary)} pooled visit summaries and {len(original)} unchanged original files')


if __name__ == '__main__':
    main()
