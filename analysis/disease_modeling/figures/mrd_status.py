"""Aggregate pooled MRD status with the established fixed population."""
import matplotlib.pyplot as plt
import numpy as np

from analysis.utils.figure_layout import remove_plot_text


def mrd_status_figure(rows, d):
    fig, ax = plt.subplots(figsize=(8.4, 6))
    bottom = np.zeros(len(rows))
    for group in d['mrd']['pooled_status_display_groups']:
        counts = np.array([sum(r[s] for s in group['statuses']) for r in rows])
        percentages = np.array([100*c/r['patients'] if r['patients'] else 0 for c, r in zip(counts, rows, strict=True)])
        ax.bar(range(len(rows)), percentages, bottom=bottom, color=group['color'], label=group['label'], edgecolor='white')
        for pos, (height, count) in enumerate(zip(percentages, counts, strict=True)):
            if height >= 5:
                ax.text(pos, bottom[pos]+height/2, f'{height:.1f}%\n(n={count})', ha='center', va='center', fontsize=9)
        bottom += percentages
    ax.set_xticks(range(len(rows)), [f'{r["visit"]}\nN={r["patients"]}' for r in rows])
    ax.set(ylim=(0, 100), ylabel='Patients (%) — fixed MRD population', title='Pooled MRD status')
    ax.legend(frameon=False)
    fig.text(.5, -.01, 'Diagnosis is an assumed disease-positive reference. Missing results are hidden; fixed denominators retained.\n'
             'Display groups combine statuses; the workbook retains all clinical categories and missing counts.',
             ha='center', va='top', fontsize=8)
    remove_plot_text(fig)
    return fig

