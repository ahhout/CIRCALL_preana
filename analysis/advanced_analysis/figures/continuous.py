"""Continuous associations with the established fitted curves and intervals."""
import numpy as np
import pandas as pd

from analysis.utils.plot_style import COHORT_LABELS, INK, scatter_points


def draw_continuous(ax, data, predictor, model, displayed, log_x, scope):
    centers = lambda part: part['center'].fillna('unknown') if 'center' in part else ['unknown']*len(part)
    for cohort, group in data.groupby('cohort', sort=True):
        points = group.loc[group[predictor.variable].gt(0)] if log_x else group
        scatter_points(ax, points[predictor.variable], points.cfdna_ng_per_ml, cohort, centers(points),
                   circall_only=scope=='circall',
                   edgecolor='white', linewidths=.5, alpha=.8, s=38, zorder=3,
                   label=COHORT_LABELS[cohort] if scope == 'pooled' else f'{COHORT_LABELS[cohort]} patients (n={len(group)})')
    if displayed[predictor.variable].nunique() > 1:
        grid = (np.geomspace if log_x else np.linspace)(displayed[predictor.variable].min(), displayed[predictor.variable].max(), 200)
        if model is not None:
            inference = model.get_robustcov_results(cov_type='HC3') if predictor.robust_se else model
            prediction = inference.get_prediction(pd.DataFrame({predictor.variable: grid})).summary_frame(alpha=.05)
            with np.errstate(over='ignore'):
                mean, low, high = [np.power(10., prediction[c].to_numpy()) for c in ('mean', 'mean_ci_lower', 'mean_ci_upper')]
            usable = np.isfinite(low) & np.isfinite(high) & (low > 0)
            ax.plot(grid, mean, color=INK, linewidth=2, label='Fitted single-predictor association')
            if usable.any():
                ax.fill_between(grid, low, high, where=usable, color='#8795A1', alpha=.18, label='Ordinary 95% confidence interval')
        elif len(data) >= 2:
            slope, intercept = np.polyfit(data[predictor.variable], data.log10_cfDNA, 1)
            ax.plot(grid, np.power(10., intercept+slope*grid), color=INK, linewidth=2, label='Descriptive linear trend on log10 scale')
