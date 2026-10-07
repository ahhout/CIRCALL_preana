"""Descriptive visit medians with whole-patient bootstrap intervals."""
from pathlib import Path
import warnings

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

from analysis.provenance import write_json
from analysis.sample_analysis import reporting
from analysis.sample_analysis.policies import PRIMARY, eligible, pooled_controls


def bootstrap_medians(matrix, *, resamples, seed):
    """Rows are patients, columns are visits; missing visits remain missing.

    Each draw uses the same sampled patients at every visit. Empty-visit draws
    remain NaN and are counted explicitly when forming pointwise intervals.
    """
    matrix = np.asarray(matrix, dtype=float)
    if matrix.ndim != 2 or resamples < 1 or seed < 0:
        raise ValueError('Bootstrap requires a patient-by-visit matrix, positive resamples and nonnegative seed')
    draws = np.full((resamples, matrix.shape[1]), np.nan)
    if not len(matrix):
        return draws
    rng = np.random.default_rng(seed)
    for start in range(0, resamples, 256):
        indices = rng.integers(len(matrix), size=(min(256, resamples-start), len(matrix)))
        with warnings.catch_warnings():
            warnings.filterwarnings('ignore', message='All-NaN slice encountered', category=RuntimeWarning)
            draws[start:start+len(indices)] = np.nanmedian(matrix[indices], axis=1)
    return draws


def summarize(frame, cohorts, *, diagnosis_as_d1, resamples, seed, method):
    if method != 'percentile':
        raise ValueError('Only the approved percentile interval method is supported')
    if resamples < 1 or seed < 0:
        raise ValueError('Resamples must be positive and seed must be nonnegative')
    patients, rows = {}, []
    for cohort in cohorts:
        data, _ = eligible(frame, cohort, 'longitudinal')
        data = reporting.plot_data(data, diagnosis_as_d1=diagnosis_as_d1)
        data = data.loc[np.isfinite(data[PRIMARY]) & data[PRIMARY].gt(0)]
        data = data.groupby(['patient_key', 'plot_timepoint'], as_index=False)[PRIMARY].median()
        patients[cohort] = data
        order = [tp for tp in reporting.PLOT_TIMEPOINTS if tp in set(data.plot_timepoint)]
        matrix = data.pivot(index='patient_key', columns='plot_timepoint', values=PRIMARY).reindex(columns=order).sort_index()
        # Stable per-cohort streams: selecting one cohort does not change its CI.
        cohort_seed = np.random.SeedSequence([seed, ('retrospective', 'circall').index(cohort)])
        draws = bootstrap_medians(matrix.to_numpy(), resamples=resamples,
                                  seed=int(cohort_seed.generate_state(1)[0]))
        for j, tp in enumerate(order):
            values = matrix[tp].dropna().to_numpy()
            valid = draws[:, j][np.isfinite(draws[:, j])]
            reason = ('CIRCALL TP2: interval omitted by approved display rule'
                      if cohort == 'circall' and tp == reporting.PLOT_LABELS['tp2']
                      else 'Fewer than two patients' if len(values) < 2 else '')
            if not len(valid) and not reason:
                reason = 'No nonempty bootstrap draws'
            low, high = np.quantile(valid, [.025, .975]) if not reason else (np.nan, np.nan)
            rows.append(dict(cohort=cohort, plot_timepoint=tp, n_patients=len(values),
                             median=float(np.median(values)), ci95_low=low, ci95_high=high,
                             bootstrap_valid_draws=len(valid), bootstrap_empty_draws=resamples-len(valid),
                             interval_omission=reason))
    columns = ['cohort', 'plot_timepoint', 'n_patients', 'median', 'ci95_low', 'ci95_high',
               'bootstrap_valid_draws', 'bootstrap_empty_draws', 'interval_omission']
    return patients, pd.DataFrame(rows, columns=columns)


def plot(patients, controls, summary, cohorts, path):
    available = set(summary.loc[summary.cohort.isin(cohorts), 'plot_timepoint'])
    if len(controls):
        available.add('Control')
    order = [tp for tp in reporting.PLOT_TIMEPOINTS if tp in available]
    positions = {tp: j for j, tp in enumerate(order)}
    fig, ax = plt.subplots(figsize=(12, 6))
    rng = np.random.default_rng(42)
    if len(controls):
        # Independent controls stay a separate reference, never part of a trend.
        x = positions['Control']
        ax.scatter(x+rng.uniform(-.08, .08, len(controls)), controls, s=18,
                   color=reporting.COLORS['control'], alpha=.65)
        ax.plot([x-.15, x+.15], [np.median(controls)]*2, color=reporting.COLORS['control'], lw=2)
    for i, cohort in enumerate(cohorts):
        color = reporting.COLORS[cohort]
        data = patients[cohort]
        group = summary.loc[summary.cohort.eq(cohort)].copy()
        group['position'] = group.plot_timepoint.map(positions)
        group = group.sort_values('position')
        offset = (i-(len(cohorts)-1)/2)*.18
        for tp in group.plot_timepoint:
            values = data.loc[data.plot_timepoint.eq(tp), PRIMARY].to_numpy()
            ax.scatter(positions[tp]+offset+rng.uniform(-.045, .045, len(values)), values,
                       color=color, s=18, alpha=.4, zorder=2)
        ax.plot(group.position, group['median'], color=color, marker='o', lw=2, zorder=4)
        # NaN endpoints break shading, including the segment leading into TP2.
        ax.fill_between(group.position.to_numpy(dtype=float), group.ci95_low.to_numpy(dtype=float),
                        group.ci95_high.to_numpy(dtype=float), color=color, alpha=.2, linewidth=0)
        for row in group.loc[group.interval_omission.ne('')].itertuples():
            ax.annotate(f'n={row.n_patients}; no CI', (row.position, row.median),
                        xytext=(0, -22), textcoords='offset points', ha='center', fontsize=8, color=color)
    labels = []
    for tp in order:
        if tp == 'Control':
            labels.append(f'Control\nn={len(controls)}')
        else:
            counts = [str(int(summary.loc[summary.cohort.eq(c) & summary.plot_timepoint.eq(tp),
                                         'n_patients'].sum())) for c in cohorts]
            labels.append(f'{tp}\nn={" / ".join(counts)}')
    ax.set_xticks(range(len(order)), labels)
    reporting.format_log_yaxis(ax)
    ax.set_ylabel(reporting.LABELS[PRIMARY])
    ax.set_xlabel('Visit categories (n follows cohort order; spacing does not represent elapsed time)')
    ax.set_title('Median DNA across visits — pointwise 95% bootstrap intervals')
    handles = [Line2D([], [], color=reporting.COLORS[c], marker='o', lw=2, label=c.capitalize()) for c in cohorts]
    if len(controls):
        handles.append(Line2D([], [], color=reporting.COLORS['control'], marker='o', linestyle='', label='Pooled controls'))
    ax.legend(handles=handles, frameon=False)
    ax.grid(axis='y', alpha=.2)
    if not order:
        ax.set_ylim(.1, 10)
        ax.text(.5, .5, 'Measurement unavailable', ha='center', transform=ax.transAxes)
    note = ('Dots: patient/visit medians; lines connect visit medians. Shading: uncertainty in the median, not patient spread.\n'
            'Whole patients resampled; observed visits only. Connecting segments are visual guides, not fitted trajectories.')
    if 'circall' in cohorts and ((summary.cohort == 'circall') & (summary.plot_timepoint == reporting.PLOT_LABELS['tp2'])).any():
        note += '\nCIRCALL TP2: median and observations only; confidence shading omitted under the approved sparse-follow-up rule.'
    fig.text(.5, .015, note, ha='center', fontsize=8)
    fig.tight_layout(rect=(0, .115, 1, 1))
    reporting.save(fig, path)


def write(frame, cohorts, output, *, diagnosis_as_d1, resamples, seed, method):
    output = Path(output)
    patients, summary = summarize(frame, cohorts, diagnosis_as_d1=diagnosis_as_d1,
                                  resamples=resamples, seed=seed, method=method)
    controls = pooled_controls(frame)
    controls = controls.loc[np.isfinite(controls[PRIMARY]) & controls[PRIMARY].gt(0), PRIMARY].to_numpy()
    reporting.table(output/'trendline_summary.csv', summary)
    settings = dict(statistic='Median of raw-scale patient/visit medians',
                    bootstrap_unit='Whole patient observed history, independently within each cohort',
                    confidence_level=.95, interval_scope='Pointwise, not simultaneous',
                    method=method, resamples=resamples, seed=seed,
                    seed_streams='SeedSequence([seed, cohort index]); retrospective=0, circall=1',
                    empty_draws='Exclude empty-visit draws from that visit CI; counts exported in summary',
                    interval_omissions=['CIRCALL TP2', 'Visits with fewer than two patients'],
                    diagnosis_as_d1=diagnosis_as_d1, control_reference='Individual records and their median; no CI or trend connection',
                    pooling='None across patient cohorts', missingness='Observed visits only; no imputation',
                    time_axis='Existing categorical plot labels; equal spacing does not imply equal elapsed time',
                    source='prepared/inventory.csv; unchanged longitudinal eligibility', jitter_seed=42)
    write_json(output/'trendline_settings.json', settings)
    plot(patients, controls, summary, cohorts, output/'trendlines.png')
    for cohort in cohorts:
        plot(patients, controls, summary, [cohort], output/cohort/'trendlines.png')
    print(f'Trendline summary: {len(summary)} cohort/visit groups; {resamples} whole-patient bootstrap draws')
    return settings
