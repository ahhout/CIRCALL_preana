"""Cohort-labelled tables and shared plotting conventions."""
from pathlib import Path
import json

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import FuncFormatter

from .policies import PRIMARY, TIMEPOINTS, eligible, pooled_controls

LABELS = {
    'volume_ml': 'Initial fluid volume (mL)', 'elution_volume_uL': 'Elution volume (µL)',
    'blood_volume_ml': 'Collected blood volume (mL)',
    'dna_concentration_ng_per_uL': 'Unadjusted DNA concentration (ng/µL)',
    'dna_total_ng': 'Total extracted DNA (ng)', PRIMARY: 'Total extracted DNA / initial plasma (ng/mL)',
}
COLORS = {'retrospective': '#4E79A7', 'circall': '#E28E62', 'control': '#7D7D7D'}


def table(path, frame):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False)


def workbook(path, tables):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(path, engine='openpyxl') as writer:
        used = set()
        for name, frame in tables.items():
            sheet = name[:31]
            if sheet in used:
                sheet = name[:26] + f'_{len(used)}'
            used.add(sheet)
            frame.to_excel(writer, sheet_name=sheet, index=False)
            ws = writer.sheets[sheet]
            ws.freeze_panes = 'B2'; ws.auto_filter.ref = ws.dimensions
            for cells in ws.iter_cols():
                ws.column_dimensions[cells[0].column_letter].width = min(40, max(16, len(str(cells[0].value or '')) + 2))


def save(fig, path):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=180, bbox_inches='tight')
    plt.close(fig)


def inventory_plot(summary, cohorts, path):
    fig, axes = plt.subplots(1, len(cohorts), figsize=(7*len(cohorts), 4.5), squeeze=False)
    for ax, cohort in zip(axes[0], cohorts):
        data = summary.loc[summary.cohort.eq(cohort)].groupby('compartment')[['present_records','na_coded_records','blank_id_records']].sum()
        if data.empty:
            ax.text(.5,.5,'No inventory records',ha='center'); continue
        bottom = np.zeros(len(data))
        for column, label, color in [('present_records','Present ID','#4E79A7'),('na_coded_records','ID coded na','#E28E62'),('blank_id_records','Blank ID','#BBBBBB')]:
            ax.bar(data.index, data[column], bottom=bottom, label=label, color=color)
            bottom += data[column].to_numpy()
        ax.set(title=cohort, ylabel='Inventory records'); ax.tick_params(axis='x',rotation=25)
        ax.legend(fontsize=8)
    fig.suptitle('Recorded inventory coverage — blank IDs are distinct from na')
    fig.tight_layout(); save(fig,path)


def volume_plot(frame, cohorts, metric, path):
    fig, axes = plt.subplots(1,len(cohorts),figsize=(6*len(cohorts),4.5),squeeze=False)
    for ax,cohort in zip(axes[0],cohorts):
        data=frame.loc[frame.cohort.eq(cohort) & ~frame.qc_hold & np.isfinite(frame[metric])]
        groups=[(name,group[metric].to_numpy()) for name,group in data.groupby('compartment',sort=True)]
        rng=np.random.default_rng(42)
        for position,(name,values) in enumerate(groups):
            if len(values)>1 and np.ptp(values)>0:
                parts=ax.violinplot([values],positions=[position],showmedians=True)
                parts['bodies'][0].set_facecolor(COLORS[cohort])
            ax.scatter(position+rng.uniform(-.08,.08,len(values)),values,s=12,alpha=.65,color=COLORS[cohort])
        ax.set_xticks(range(len(groups)),[f'{name}\nn={len(values)}' for name,values in groups],rotation=20)
        ax.set(title=cohort,ylabel=LABELS.get(metric,metric))
        if not groups:ax.text(.5,.5,'Measurement unavailable',ha='center',transform=ax.transAxes)
    fig.tight_layout();save(fig,path)


def timepoint_plot(frame, cohorts, metric, path, *, longitudinal=False, connect=False, subtype=False):
    fig, axes=plt.subplots(1,len(cohorts),figsize=(7*len(cohorts),5.5),squeeze=False,sharey=True)
    subtype_labels=sorted(set(frame.loc[~frame.is_control,'genetic_subtype'])-{'','na'})
    display_labels={}
    for name in subtype_labels:display_labels.setdefault(name.casefold(),name)
    palette={key:plt.get_cmap('tab20')(i%20) for i,key in enumerate(display_labels)}
    used_subtypes=set(); plotted_values=[]
    controls=pooled_controls(frame)
    for ax,cohort in zip(axes[0],cohorts):
        data,_=eligible(frame,cohort,'longitudinal' if longitudinal else 'yield')
        data=data.loc[np.isfinite(data[metric]) & (data[metric].gt(0) if longitudinal else data[metric].ge(0))]
        order=[tp for tp in TIMEPOINTS[cohort] if tp in set(data.timepoint)]
        order += sorted(set(data.timepoint.dropna())-set(order))
        if longitudinal and cohort=='retrospective':
            order=[tp for tp in order if tp!='tp0,5'] # existing subset-plot exclusion only
        data=data.loc[data.timepoint.isin(order)]
        if longitudinal:
            data=data.groupby(['patient_key','timepoint'],as_index=False).agg({metric:'median','genetic_subtype':'first','mrd_status':'first'})
        reference=controls.loc[np.isfinite(controls[metric]) & (controls[metric].gt(0) if longitudinal else controls[metric].ge(0))].copy()
        reference['timepoint']='Control'
        groups=pd.concat([reference,data],ignore_index=True)
        order=(['Control'] if not reference.empty else [])+order
        transform=(lambda x:np.asarray(x)) if longitudinal else (lambda x:np.log10(1+np.asarray(x)))
        rng=np.random.default_rng(42)
        for position,tp in enumerate(order):
            group=groups.loc[groups.timepoint.eq(tp)]
            values=transform(group[metric])
            if len(values)>1 and np.ptp(values)>0:
                # Positive longitudinal densities are estimated in log space.
                density=np.log10(values) if longitudinal else values
                parts=ax.violinplot([density],positions=[position],showmedians=False,showextrema=False)
                if longitudinal:
                    for body in parts['bodies']:
                        for polygon in body.get_paths():polygon.vertices[:,1]=10**polygon.vertices[:,1]
                parts['bodies'][0].set_facecolor(COLORS['control' if tp=='Control' else cohort])
            plotted_values.extend(values)
            if len(values):ax.plot([position-.16,position+.16],[np.median(values)]*2,color=COLORS['control' if tp=='Control' else cohort],linewidth=2)
            for offset,(_,row) in zip(rng.uniform(-.10,.10,len(group)),group.iterrows()):
                color=COLORS['control' if tp=='Control' else cohort]
                if subtype and tp!='Control':
                    key=row.genetic_subtype.casefold()
                    color=palette.get(key,'#999999')
                    if key in palette:used_subtypes.add(key)
                marker='x' if tp=='Control' or (tp!='diag' and row.get('mrd_status')=='neg') else 'o'
                ax.scatter(position+offset,transform([row[metric]])[0],s=20,alpha=.7,c=[color],marker=marker)
        if connect:
            for _,group in data.groupby('patient_key'):
                group=group.assign(position=group.timepoint.map({tp:i for i,tp in enumerate(order)})).sort_values('position')
                ax.plot(group.position,transform(group[metric]),color='#888888',alpha=.2,linewidth=.6)
        counts=groups.groupby('timepoint').size()
        ax.set_xticks(range(len(order)),[f'{tp}\nn={counts.get(tp,0)}' for tp in order],rotation=35,ha='right')
        ax.set_title(cohort);ax.set_ylabel(LABELS.get(metric,metric))
        if longitudinal:ax.set_yscale('log')
        else:ax.yaxis.set_major_formatter(FuncFormatter(lambda x,_:f'{10**x-1:g}'))
        ax.grid(axis='y',alpha=.2)
    if plotted_values:
        low,high=min(plotted_values),max(plotted_values)
        for ax in axes[0]:
            if longitudinal:ax.set_ylim(low/1.5,high*1.5)
            else:
                ax.set_ylim(0,high+max(.05,high*.06))
                ticks=[v for v in (0,.1,.5,1,2,5,10,20,50,100,200,500,1000,2000,5000,10000) if np.log10(1+v)<=ax.get_ylim()[1]]
                spaced=[]
                for value in ticks:
                    if not spaced or np.log10(1+value)-np.log10(1+spaced[-1])>=ax.get_ylim()[1]/16:
                        spaced.append(value)
                ax.set_yticks(np.log10(1+np.asarray(spaced)),[f'{v:g}' for v in spaced])
    if subtype and used_subtypes:
        fig.legend(handles=[Line2D([],[],marker='o',linestyle='',color=palette[key],label=display_labels[key]) for key in sorted(used_subtypes)],
                   loc='center left',bbox_to_anchor=(1,.5),fontsize=8,title='Genetic subtype')
    fig.suptitle(('Patient medians; log scale' if longitudinal else 'Sample distributions; log10(1+x) scale')+' — unadjusted DNA')
    fig.tight_layout();save(fig,path)


def correlation_plot(frame, cohorts, x, y, path):
    from .analyses import transformed_y
    fig,axes=plt.subplots(1,len(cohorts),figsize=(6*len(cohorts),4.5),squeeze=False,sharey=True)
    for ax,cohort in zip(axes[0],cohorts):
        data,_=eligible(frame,cohort,'correlations')
        data=data.loc[np.isfinite(data[x]) & np.isfinite(data[y]) & (data[y].ge(0) if y=='dna_total_ng' else data[y].gt(0))]
        for i,(tp,group) in enumerate(data.groupby('timepoint',sort=True)):
            ax.scatter(group[x],transformed_y(y,group[y]),label=tp,s=18,alpha=.7,color=plt.get_cmap('tab10')(i%10))
        ax.set(title=cohort,xlabel=LABELS.get(x,x),ylabel=('log10(1 + total DNA ng)' if y=='dna_total_ng' else 'log10 '+LABELS.get(y,y)))
        if len(data):ax.legend(fontsize=7)
        else:ax.text(.5,.5,'Paired measurements unavailable',ha='center',transform=ax.transAxes)
    fig.tight_layout();save(fig,path)
