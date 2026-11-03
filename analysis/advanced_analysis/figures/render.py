"""Prepare and annotate the established original-unit association figures."""
import textwrap

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter

from analysis.figure_layout import remove_plot_text, legends_below
from analysis.plot_style import INK, style_axes
from ..statistics import pairs
from .continuous import draw_continuous
from .categorical import draw_categorical


def figure(frame, predictor, model, coverage, association, scope, args, definitions, *, outcome='cfdna_ng_per_ml_plasma'):
    data = pairs(frame, predictor)
    if not len(data) or coverage['status'] != 'available':
        return None
    log_x = predictor.variable in definitions['rules']['log_x_predictors']
    displayed = data.loc[data[predictor.variable].gt(0)] if log_x else data
    category_n = data[predictor.variable].nunique() if predictor.kind == 'categorical' else 0
    fig, ax = plt.subplots(figsize=(8.4 if predictor.kind == 'continuous' else max(10, category_n*1.1), 6))
    if predictor.kind == 'continuous':
        draw_continuous(ax, data, predictor, model, displayed, log_x, scope)
    else:
        draw_categorical(ax, data, predictor, scope, definitions)
    if scope == 'circall' and predictor.kind == 'categorical':
        ax.get_legend().set_title(f'CIRCALL patients (n={len(data)})')
    if scope == 'pooled' and predictor.kind == 'continuous':
        ax.text(.02, .98, f'n={len(data)}', transform=ax.transAxes, ha='left', va='top')
    label = predictor.label
    if predictor.variable == 'gb_per_l':
        label = 'Maximum diagnosis blood WBC (×10⁹/L)' if coverage['unit'] == 'x10^9/L' else 'Maximum diagnosis blood WBC (source units unconfirmed)'
    spec = definitions['outcomes'][outcome]
    ax.set(xlabel=label, ylabel=f"{spec['label']} ({spec['unit']})", yscale='log')
    if log_x:
        ax.set_xscale('log')
        ax.xaxis.set_major_formatter(FuncFormatter(lambda v, _: f'{v:g}'))
    ax.yaxis.set_major_formatter(FuncFormatter(lambda v, _: f'{v:g}'))
    title = f"{spec['label']} versus {label}"
    subtitle = f'Plasma · Diagnosis patient samples · {scope.capitalize()} · Analysis patients n={len(data)}'
    fig.suptitle(textwrap.fill(title,85,break_long_words=False), fontsize=15, color=INK)
    ax.set_title(subtitle, fontsize=10, pad=12)
    notes = []
    if log_x and len(displayed) < len(data):
        display_label = {'gb_per_l': 'WBC', 'tumor_fraction_percent': 'marrow blast percentages'}.get(predictor.variable, predictor.label)
        notes.append(f'Nonpositive {display_label} omitted from log display: {len(data)-len(displayed)}; retained in tables/models; no pseudocount')
        if displayed.empty:
            ax.text(.5, .5, f'No positive {display_label} values for logarithmic display', transform=ax.transAxes, ha='center')
    if coverage['nonpositive_pairs']:
        notes.append(f"Nonpositive selected sample outcomes excluded from log display/models: {coverage['nonpositive_pairs']}; no pseudocount")
    if association and association['status'] != 'fit':
        notes.append('Fit unavailable: '+association['reason'])
    if association and association['status'] == 'fit':
        notes.append(f"Unadjusted {'categorical omnibus' if predictor.kind == 'categorical' else 'regression'} p={association['p_value']:.3g}; no multiplicity correction")
    if association and association.get('spearman_status') == 'computed':
        notes.append(f"Secondary unadjusted Spearman: ρ={association['spearman_rho']:.3f}, p={association['spearman_p_value']:.3g}")
    if predictor.kind == 'categorical':
        notes.append('Boxes calculated on log10(outcome), back-transformed for display')
    if predictor.variable == 'elution_volume_ul' and outcome != 'cfdna_fraction':
        notes.append('Elution volume enters the outcome calculation; association includes arithmetic dependence')
    if scope == 'pooled':
        notes.append('Descriptive only; no pooled inference')
    if notes:
        fig.text(.5, -.01, '\n'.join(textwrap.fill(note,110,break_long_words=False) for note in notes), ha='center', va='top', fontsize=9,color='#52616B')
    style_axes(ax)
    if predictor.kind == 'continuous':
        handles, labels = ax.get_legend_handles_labels()
        unique = dict(zip(labels, handles))
        ax.legend(unique.values(), unique.keys(), frameon=False,
                  title=f'CIRCALL patients (n={len(data)})' if scope=='circall' else None)
    remove_plot_text(fig)
    fig.tight_layout()
    legends_below(fig)
    return fig

