"""Explain existing test tables visually; no tests or corrections are recalculated."""
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle
from matplotlib.ticker import FuncFormatter, MaxNLocator
import numpy as np
import pandas as pd

from analysis.sample_analysis.policies import PRIMARY
from analysis.sample_analysis.reporting import save


def label(value, diagnosis_as_d1):
    return {'Control': 'Controls', 'diag': 'D1 (diagnosis)' if diagnosis_as_d1 else 'Diagnosis',
            'd4': 'D4', 'd8': 'D8', 'd15': 'D15', 'tp0,5': 'TP0.5',
            'tp1': 'TP1', 'tp2': 'TP2'}.get(value, value)


def p_text(value):
    if not np.isfinite(value):
        return 'unavailable'
    if value == 0:
        return '0 [precision limit]'
    return f'{value:.1e}' if value < .001 else f'{value:.3f}'


def log_values(patients, controls, bins, unit):
    """Reproduce the observation units of the exported Welch table for display."""
    groups = {}
    for group in bins:
        data = controls if group == 'Control' else patients.loc[
            patients.timepoint.astype(str).str.strip().str.lower().eq(group.lower())]
        data = data.copy()
        data['value'] = pd.to_numeric(data[PRIMARY], errors='coerce')
        data = data.loc[np.isfinite(data.value) & data.value.gt(0)].copy()
        data['value'] = np.log10(data.value)
        if group != 'Control' and unit == 'patient_median':
            data = data.dropna(subset=['patient_key']).groupby('patient_key', as_index=False).value.median()
        groups[group] = data.value.to_numpy()
    return groups


def welch_plot(table, patients, controls, path, cohort, *, diagnosis_as_d1):
    units = table.unit.unique()
    if len(units) != 1 or units[0] not in ('sample', 'patient_median'):
        raise ValueError('Welch plot requires one supported observation unit')
    unit = units[0]
    bins = list(dict.fromkeys(table[['bin_a','bin_b']].to_numpy().ravel()))
    groups = log_values(patients, controls, bins, unit)
    for row in table.itertuples():
        if len(groups[row.bin_a]) != row.n_a or len(groups[row.bin_b]) != row.n_b:
            raise ValueError('Welch plot observation counts differ from the exported test table')
    names = [label(b, diagnosis_as_d1) for b in bins]
    fig, (ax, matrix) = plt.subplots(1, 2, figsize=(14, max(6.2, len(bins)*.75)),
                                    gridspec_kw={'width_ratios': [1.2, 1]})
    rng = np.random.default_rng(42)
    for i, group in enumerate(bins):
        values = groups[group]
        color = '#7D7D7D' if group == 'Control' else '#357C94'
        if len(values):
            ax.boxplot([values], positions=[i], vert=False, widths=.45, patch_artist=True,
                       showfliers=False, manage_ticks=False,
                       boxprops={'facecolor': color, 'alpha': .2}, medianprops={'color': color})
            ax.scatter(values, i+rng.uniform(-.13,.13,len(values)), s=14, color=color, alpha=.65)
            ax.scatter([values.mean()], [i], marker='D', s=45, color='black', zorder=5)
    ax.set_yticks(range(len(bins)), [f'{name}  (n={len(groups[b])})' for name,b in zip(names,bins)])
    ax.set_ylim(len(bins)-.6,-.6)
    ax.xaxis.set_major_locator(MaxNLocator(integer=True))
    ax.xaxis.set_major_formatter(FuncFormatter(lambda x,_: f'{10**x:g}'))
    ax.set_xlabel('Extracted DNA per mL plasma (ng/mL; log10 spacing)')
    ax.set_title('Measurements used by this test', pad=12)
    ax.grid(axis='x', alpha=.2)
    ax.legend(handles=[Line2D([],[],color='black',marker='D',linestyle='',label='Geometric mean (mean on log scale)')],
              loc='upper left', bbox_to_anchor=(0,-.15), frameon=False, fontsize=9)
    matrix.set_xlim(-.5,len(bins)-.5);matrix.set_ylim(len(bins)-.5,-.5)
    matrix.set_xticks(range(len(bins)),names,rotation=40,ha='right')
    matrix.set_yticks(range(len(bins)),names)
    matrix.set_title('Pairwise comparisons: BH-adjusted p-values', pad=12)
    lookup = {b:i for i,b in enumerate(bins)}
    for row in table.itertuples():
        i,j = lookup[row.bin_a],lookup[row.bin_b]
        p = row.p_adj_bh
        shade = '#e8edf0' if not np.isfinite(p) or p >= .05 else '#c4dce6' if p >= .01 else '#78afc3' if p >= .001 else '#225b70'
        matrix.add_patch(Rectangle((j-.5,i-.5),1,1,facecolor=shade,edgecolor='white'))
        matrix.text(j,i,p_text(p),ha='center',va='center',fontsize=9,
                    color='white' if np.isfinite(p) and p < .001 else '#202020')
    for i in range(len(bins)):
        matrix.text(i,i,'—',ha='center',va='center',color='#999999')
    title = 'Welch test — all samples' if unit == 'sample' else 'Welch test — one median per patient and timepoint'
    fig.suptitle(f'{cohort}: {title}', fontsize=15)
    unit_note = 'Each dot is a sample record.' if unit == 'sample' else 'Each patient dot is a median of log10 measurements at that visit; controls remain individual records.'
    fig.text(.02,.025,unit_note+'\nBoxes show quartiles; all points, including extremes, remain visible. Darker cells mean smaller adjusted p-values, not larger effects.\n'
             'These Welch tests treat groups as independent, including when patients recur across visits. Blank lower cells repeat the upper comparisons.',fontsize=9)
    fig.tight_layout(rect=(0,.18,1,.93),w_pad=3)
    save(fig,path)


def comparison_plot(table, path, cohort, *, mixed, diagnosis_as_d1, counts=None):
    fig,ax = plt.subplots(figsize=(14,max(5.5,.4*len(table)+2.4)))
    labels=[]
    for i,row in enumerate(table.itertuples()):
        if mixed:
            a,b=row.timepoint_a,row.timepoint_b
            value,low,high=row.fold_change,row.ci95_low_fc,row.ci95_high_fc
            p=row.p_adj
            if np.isfinite([value,low,high]).all() and min(value,low,high)>0:
                ax.errorbar(value,i,xerr=[[value-low],[high-value]],fmt='o',capsize=3,color='#286A80')
                effect=f'{value:.2f} ({low:.2f}–{high:.2f})'
            else:
                effect='unavailable'
            labels.append(f'{label(b,diagnosis_as_d1)} / {label(a,diagnosis_as_d1)}')
            n = f'{counts.get(b,"?")} / {counts.get(a,"?")}'
        else:
            a,b=row.bin_a,row.bin_b
            value,p=row.cliffs_delta,row.p_adj_bh
            if np.isfinite(value):
                ax.plot([0,value],[i,i],color='#286A80',linewidth=2)
                ax.plot(value,i,'o',color='#286A80')
            effect=f'{value:+.2f}' if np.isfinite(value) else 'unavailable'
            labels.append(f'{label(a,diagnosis_as_d1)} vs {label(b,diagnosis_as_d1)}')
            n=f'{row.n_a} / {row.n_b}'
        ax.text(1.02,i,effect,transform=ax.get_yaxis_transform(),va='center',fontsize=10)
        ax.text(1.52,i,p_text(p),transform=ax.get_yaxis_transform(),va='center',fontsize=10)
        ax.text(1.93,i,n,transform=ax.get_yaxis_transform(),va='center',fontsize=10)
    ax.set_yticks(range(len(table)),labels)
    ax.set_ylim(len(table)-.5,-.75)
    ax.text(1.02,1.04,'Ratio (95% CI)' if mixed else "Cliff's delta",transform=ax.transAxes,fontweight='bold')
    ax.text(1.52,1.04,'BH-adjusted p',transform=ax.transAxes,fontweight='bold')
    ax.text(1.93,1.04,'Patients B / A' if mixed else 'n A / B',transform=ax.transAxes,fontweight='bold')
    if mixed:
        ax.set_xscale('log');ax.axvline(1,color='#777777',linestyle='--')
        ax.xaxis.set_major_formatter(FuncFormatter(lambda x,_:f'{x:g}'))
        ax.set_xlabel('DNA level ratio: below 1 = numerator lower; above 1 = numerator higher')
        title='Mixed model — how much do timepoints differ?'
        note='Dots: model-estimated ratios. Bars: ordinary 95% confidence intervals (not adjusted for multiple comparisons).\n'
        note+='Outcome: log10 DNA per mL plasma. Fixed effect: categorical patient visit; controls are descriptive only. Random effect: patient intercept for repeated observations.\n'
        note+='No additional covariates (e.g. age, sex, hospital or subtype) are included. Configured descriptive visits are excluded from the model. The dashed line at 1 means equal levels.\n'
        note+='Ratios describe geometric levels, not arithmetic means. Patient counts are per group, not counts of matched pairs.'
    else:
        ax.set_xlim(-1.08,1.08);ax.axvline(0,color='#777777',linestyle='--')
        ax.set_xticks([-1,-.5,0,.5,1])
        ax.set_xlabel('B tends higher  ←    0 = balanced ordering    →  A tends higher')
        title='Mann–Whitney — which group tends to have higher DNA?'
        note="Cliff's delta = P(A > B) − P(A < B). It measures rank separation, not a fold change. No effect-size confidence intervals were calculated.\n"
        note+='n counts patient-timepoint summaries; controls remain individual records. The test treats groups as independent, including repeated patients.'
    if any((table.p_adj if mixed else table.p_adj_bh).eq(0)):
        note+='\n0 [precision limit] is the exported numerical result; it is not a literal zero probability.'
    ax.grid(axis='x',alpha=.2);ax.spines[['top','right']].set_visible(False)
    fig.suptitle(f'{cohort}: {title}',fontsize=15,y=.98)
    fig.subplots_adjust(left=.19,right=.54,bottom=.22 if len(table)<12 else .15,top=.86 if len(table)<12 else .91)
    fig.text(.02,.025,note,fontsize=9)
    save(fig,path)


def write_test_plots(tables, patients, controls, output, cohort, *, diagnosis_as_d1=False):
    output=Path(output)/'test_plots'
    names={'circall':'CIRCALL','retrospective':'Retrospective','combined':'Combined cohorts'}
    title=names.get(cohort,cohort)
    for name in ('welch_sample','welch_patient_median'):
        if name in tables and not tables[name].empty:
            welch_plot(tables[name],patients,controls,output/f'{name}.png',title,diagnosis_as_d1=diagnosis_as_d1)
    name='mannwhitney_patient_median'
    if name in tables and not tables[name].empty:
        comparison_plot(tables[name],output/f'{name}.png',title,mixed=False,diagnosis_as_d1=diagnosis_as_d1)
    name='mixed_contrasts'
    if name in tables and not tables[name].empty:
        counts=dict(zip(tables['timepoint_counts'].timepoint,tables['timepoint_counts'].n_patients))
        comparison_plot(tables[name],output/f'{name}.png',title,mixed=True,diagnosis_as_d1=diagnosis_as_d1,counts=counts)
