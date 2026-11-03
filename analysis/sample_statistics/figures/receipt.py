"""Receipt-status counts using the established cohort display."""
from collections import Counter

from analysis.plot_style import COHORT_COLORS, COHORT_LABELS, style_axes
from ..labels import RECEIPT_LABELS


def receipt_figure(rows, controls=False):
    import matplotlib.pyplot as plt

    fig,ax=plt.subplots(figsize=(10,5))
    counts=Counter(r['receipt'] for r in rows)
    keys=sorted(counts)
    cohort=rows[0]['cohort']
    bars=ax.bar(range(len(keys)),[counts[k] for k in keys],color=COHORT_COLORS[cohort],width=.6,alpha=.8)
    ax.bar_label(bars,padding=5,fontsize=11,color='#243746')
    ax.margins(y=.15)
    ax.set_xticks(range(len(keys)),[RECEIPT_LABELS.get(k,k.replace('_',' ')) for k in keys],rotation=25,ha='right')
    ax.set_ylabel('Samples (inventory rows)')
    ax.set_title(f'Receipt status · {COHORT_LABELS[cohort]}\n{"Controls" if controls else "Patient samples"} · n={len(rows)} · P={len({r["subject_key"] for r in rows})}',fontsize=15,pad=18)
    style_axes(ax)
    return fig
