"""Cohort-labelled tables and shared plotting conventions."""
from pathlib import Path
import json

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.ticker import FuncFormatter, NullFormatter

from analysis.sample_analysis.policies import PRIMARY, eligible, pooled_controls

LABELS = {
    'volume_ml': 'Initial fluid volume (mL)', 'elution_volume_uL': 'Elution volume (µL)',
    'dna_concentration_ng_per_uL': 'Unadjusted DNA concentration (ng/µL)',
    'dna_total_ng': 'Total extracted DNA (ng)', PRIMARY: 'Total extracted DNA / initial plasma (ng/mL)',
}
LABELS.update({
    'mnc_tube_count_million': 'Blood pellet cells per tube (million)',
    'mnc_aliquot_count_million': 'Blood pellet cells per aliquot (million)',
    'mnc_vario_ng_per_uL': 'Blood pellet DNA — Vario (ng/µL)',
    'mnc_vario_total_ng': 'Blood pellet total DNA — Vario (ng)',
    'mnc_albumin_ng_per_uL': 'Blood pellet DNA — albumin assay (ng/µL)',
    'mnc_DIN': 'Blood pellet DNA integrity number',
})
COLORS = {'retrospective': '#4E79A7', 'circall': '#E28E62', 'control': '#7D7D7D'}


def format_log_yaxis(ax, *, nonpositive='clip'):
    """Keep logarithmic spacing and label ticks with ordinary numeric values."""
    ax.set_yscale('log', nonpositive=nonpositive)
    ax.yaxis.set_major_formatter(FuncFormatter(
        lambda value, _: np.format_float_positional(value, trim='-')))
    ax.yaxis.set_minor_formatter(NullFormatter())


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
    from analysis.figure_layout import legends_below
    legends_below(fig)
    fig.savefig(path, dpi=180, bbox_inches='tight')
    plt.close(fig)


def csf_site_boxplot(frame, path):
    """All recorded timepoints combined; one box per center using individual volumes."""
    data = frame.loc[frame.cohort.eq('circall') & frame.compartment.eq('CSF') & ~frame.qc_hold]
    fig, ax = plt.subplots(figsize=(7, 5))
    rng = np.random.default_rng(42)
    labels = []
    for position, site, color in zip((0, 1), ('RDB','TRS'), ('#4E79A7','#E28E62')):
        group = data.loc[data.hospital.eq(site) & np.isfinite(data.volume_ml)]
        box_points(ax, group.volume_ml.to_numpy(), position, color, rng, width=.5)
        labels.append(f'{site}\nn={len(group)} measurements')
        if group.empty:
            ax.text(position, .05, 'No measured volumes', transform=ax.get_xaxis_transform(), ha='center')
    ax.set_xticks([0,1], labels)
    ax.set_xlim(-.6,1.6)
    ax.set_ylabel('CSF volume (mL)')
    ax.set_title('CIRCALL CSF volumes by center — all timepoints')
    ax.set_ylim(bottom=0)
    ax.grid(axis='y', alpha=.2)
    unknown = int((~data.hospital.isin(['RDB','TRS'])).sum())
    fig.text(.5,.015,'Boxes: median and interquartile range; whiskers: 1.5 × IQR; dots: measurements.\n'
        f'Missing volumes excluded. Repeated visits retained. Unknown-center records: {unknown}.',
        ha='center', fontsize=8)
    fig.tight_layout(rect=(0,.08,1,1))
    save(fig, path)


PLOT_TIMEPOINTS = ['Control', 'D1', 'D4', 'D8', 'D15', 'TP1 (D29)', 'TP2 (D71)']
PLOT_LABELS = {'control': 'Control', 'd1': 'D1', 'd4': 'D4', 'd8': 'D8',
               'd15': 'D15', 'tp1': 'TP1 (D29)', 'tp2': 'TP2 (D71)'}


def plot_data(frame, *, diagnosis_as_d1=False):
    labels = dict(PLOT_LABELS)
    if diagnosis_as_d1:
        labels['diag'] = 'D1'
    data = frame.copy()
    data['plot_timepoint'] = data.timepoint.str.casefold().map(labels)
    return data.loc[data.plot_timepoint.notna()]


def cohort_legend(ax, cohorts):
    ax.legend(handles=[Line2D([], [], marker='s', linestyle='', color=COLORS[c], label=c.capitalize())
                       for c in cohorts], frameon=False)


def box_points(ax, values, position, color, rng, *, width=.30, markers=None, point_colors=None):
    if not len(values):
        return
    ax.boxplot([values], positions=[position], widths=width, patch_artist=True,
               showfliers=False, manage_ticks=False,
               boxprops={'facecolor': color, 'alpha': .3, 'edgecolor': color},
               medianprops={'color': color, 'linewidth': 2},
               whiskerprops={'color': color}, capprops={'color': color})
    offsets = position+rng.uniform(-width/4, width/4, len(values))
    markers = np.asarray(markers if markers is not None else ['o']*len(values))
    point_colors = np.asarray(point_colors if point_colors is not None else [color]*len(values))
    for marker in dict.fromkeys(markers):
        selected = markers==marker
        ax.scatter(offsets[selected], np.asarray(values)[selected], s=16, alpha=.65,
                   color=point_colors[selected], marker=marker, zorder=3)


def compartment_slug(name):
    return str(name).casefold().replace(' ', '_').replace('/', '_')


def single_compartment(frame):
    compartments = frame.compartment.dropna().unique()
    if len(compartments) > 1:
        raise ValueError('Plot one compartment at a time; cross-compartment comparisons are disabled')
    return compartments[0] if len(compartments) else 'Unavailable compartment'


def inventory_plot(summary, cohorts, path, *, diagnosis_as_d1=False):
    compartment = single_compartment(summary)
    data = plot_data(summary, diagnosis_as_d1=diagnosis_as_d1)
    compartments = sorted(set(data.compartment))
    fig, ax = plt.subplots(figsize=(max(7, len(compartments)*2), 5))
    width = .8/len(cohorts)
    for i, cohort in enumerate(cohorts):
        counts = data.loc[data.cohort.eq(cohort)].groupby('compartment')[['present_records','na_coded_records','blank_id_records']].sum().reindex(compartments, fill_value=0)
        positions = np.arange(len(compartments)) + (i-(len(cohorts)-1)/2)*width
        bottom = np.zeros(len(compartments))
        for column, label, color in [('present_records','Present ID','#4E79A7'),('na_coded_records','ID coded na','#E28E62'),('blank_id_records','Blank ID','#BBBBBB')]:
            ax.bar(positions, counts[column], width=width*.9, bottom=bottom,
                   label=label if i==0 else None, color=color)
            bottom += counts[column].to_numpy()
    ticks = [(j+(i-(len(cohorts)-1)/2)*width, f'{cohort.capitalize()}\n{compartment}')
             for j, compartment in enumerate(compartments) for i, cohort in enumerate(cohorts)]
    ax.set_xticks([x for x,_ in ticks], [label for _,label in ticks], rotation=25, ha='right')
    ax.set(ylabel='Inventory records', title=f'{compartment} inventory — canonical timepoints')
    if compartments: ax.legend(frameon=False)
    else: ax.text(.5,.5,'No inventory records',ha='center',transform=ax.transAxes)
    fig.tight_layout(); save(fig,path)


def volume_plot(frame, cohorts, metric, path, *, diagnosis_as_d1=False):
    compartment = single_compartment(frame)
    data = plot_data(frame, diagnosis_as_d1=diagnosis_as_d1)
    data = data.loc[data.cohort.isin(cohorts) & ~data.qc_hold & np.isfinite(data[metric])]
    compartments = sorted(set(data.compartment))
    fig, ax = plt.subplots(figsize=(max(7, len(compartments)*2), 5))
    rng = np.random.default_rng(42)
    width = .8/len(cohorts)
    for j, compartment in enumerate(compartments):
        for i, cohort in enumerate(cohorts):
            values = data.loc[data.cohort.eq(cohort) & data.compartment.eq(compartment),metric].to_numpy()
            position = j+(i-(len(cohorts)-1)/2)*width
            box_points(ax, values, position, COLORS[cohort], rng, width=width*.8)
    ax.set_xticks(range(len(compartments)), compartments)
    ax.set(ylabel=LABELS.get(metric,metric), title=f'{compartment} — canonical timepoints')
    if not compartments: ax.text(.5,.5,'Measurement unavailable',ha='center',transform=ax.transAxes)
    cohort_legend(ax, cohorts)
    ax.grid(axis='y',alpha=.2)
    fig.tight_layout(); save(fig,path)


def blood_pellet_plot(frame, cohorts, metric, path, *, diagnosis_as_d1=True):
    data = frame.loc[frame.compartment.eq('blood pellet') & frame.cohort.isin(cohorts) & ~frame.qc_hold]
    data = plot_data(data, diagnosis_as_d1=diagnosis_as_d1)
    data = data.loc[np.isfinite(data[metric])]
    order = [tp for tp in PLOT_TIMEPOINTS if tp in set(data.plot_timepoint)]
    fig, ax = plt.subplots(figsize=(10, 5))
    width = .8/len(cohorts)
    rng = np.random.default_rng(42)
    labels = []
    for j, tp in enumerate(order):
        sizes = []
        for i, cohort in enumerate(cohorts):
            values = data.loc[data.cohort.eq(cohort) & data.plot_timepoint.eq(tp), metric].to_numpy()
            box_points(ax, values, j+(i-(len(cohorts)-1)/2)*width, COLORS[cohort], rng, width=width*.8)
            sizes.append(str(len(values)))
        labels.append(f'{tp}\nn={" / ".join(sizes)}')
    ax.set_xticks(range(len(order)), labels)
    ax.set(xlabel='Timepoint', ylabel=LABELS.get(metric,metric), title='Blood pellet — canonical timepoints')
    if not order:
        ax.text(.5,.5,'Measurement unavailable at canonical timepoints',ha='center',transform=ax.transAxes)
    cohort_legend(ax, cohorts)
    ax.grid(axis='y',alpha=.2)
    fig.tight_layout(); save(fig,path)


def timepoint_plot(frame, cohorts, metric, path, *, longitudinal=False, connect=False, diagnosis_as_d1=False, combine_cohorts=False):
    fig, ax = plt.subplots(figsize=(12, 5.5))
    controls = pooled_controls(frame)
    reference = controls.loc[np.isfinite(controls[metric]) & (controls[metric].gt(0) if longitudinal else controls[metric].ge(0))]
    patients = {}
    available = {'Control'} if not reference.empty else set()
    for cohort in cohorts:
        data,_ = eligible(frame,cohort,'longitudinal' if longitudinal else 'yield')
        data = plot_data(data, diagnosis_as_d1=diagnosis_as_d1)
        data = data.loc[np.isfinite(data[metric]) & (data[metric].gt(0) if longitudinal else data[metric].ge(0))]
        if longitudinal:
            data = data.groupby(['patient_key','plot_timepoint'],as_index=False)[metric].median()
        patients[cohort] = data
        available.update(data.plot_timepoint)
    order = [tp for tp in PLOT_TIMEPOINTS if tp in available]
    transform = (lambda x: np.asarray(x)) if longitudinal else (lambda x: np.log10(1+np.asarray(x)))
    rng = np.random.default_rng(42)
    plotted_values = []
    counts = []
    width = .8/len(cohorts)
    for j,tp in enumerate(order):
        if tp=='Control':
            values = transform(reference[metric])
            box_points(ax, values, j, COLORS['control'], rng, markers=['o']*len(values))
            plotted_values.extend(values)
            counts.append(f'{tp}\nn={len(values)}')
            continue
        sizes = []
        combined_values, combined_markers, combined_colors = [], [], []
        for i,cohort in enumerate(cohorts):
            group = patients[cohort].loc[patients[cohort].plot_timepoint.eq(tp)]
            values = transform(group[metric])
            markers = ['o']*len(values)
            if combine_cohorts:
                combined_values.extend(values)
                combined_markers.extend(markers)
                combined_colors.extend([COLORS[cohort]]*len(values))
            else:
                box_points(ax, values, j+(i-(len(cohorts)-1)/2)*width, COLORS[cohort], rng, width=width*.8, markers=markers)
            plotted_values.extend(values)
            sizes.append(str(len(values)))
        if combine_cohorts:
            box_points(ax, combined_values, j, '#888888', rng, width=.55,
                       markers=combined_markers, point_colors=combined_colors)
        counts.append(f'{tp}\nn={" / ".join(sizes)}')
    if connect:
        for i,cohort in enumerate(cohorts):
            positions = {tp:j+(0 if combine_cohorts else (i-(len(cohorts)-1)/2)*width) for j,tp in enumerate(order)}
            for _,group in patients[cohort].groupby('patient_key'):
                group = group.assign(position=group.plot_timepoint.map(positions)).sort_values('position')
                ax.plot(group.position,transform(group[metric]),color=COLORS[cohort],alpha=.2,linewidth=.6)
    ax.set_xticks(range(len(order)),counts)
    ax.set_ylabel(LABELS.get(metric,metric))
    if longitudinal:
        format_log_yaxis(ax)
    else:
        ax.yaxis.set_major_formatter(FuncFormatter(lambda x,_:f'{10**x-1:g}'))
    if plotted_values:
        low,high=min(plotted_values),max(plotted_values)
        if longitudinal:ax.set_ylim(low/1.5,high*1.5)
        else:
            ax.set_ylim(0,high+max(.05,high*.06))
            ticks=[v for v in (0,.1,.5,1,2,5,10,20,50,100,200,500,1000,2000,5000,10000) if np.log10(1+v)<=ax.get_ylim()[1]]
            spaced=[]
            for value in ticks:
                if not spaced or np.log10(1+value)-np.log10(1+spaced[-1])>=ax.get_ylim()[1]/16:
                    spaced.append(value)
            ax.set_yticks(np.log10(1+np.asarray(spaced)),[f'{v:g}' for v in spaced])
    else:
        ax.text(.5,.5,'Measurement unavailable',ha='center',transform=ax.transAxes)
    ax.grid(axis='y',alpha=.2)
    cohort_legend(ax, cohorts)
    ax.set_title(('Patient medians; log scale' if longitudinal else 'Sample distributions; log10(1+x) scale')+' — unadjusted DNA'+(' — pooled cohorts' if combine_cohorts else ''))
    ax.set_xlabel('Timepoint (n follows cohort order in legend; controls are pooled)')
    fig.tight_layout();save(fig,path)


def correlation_plot(frame, cohorts, x, y, path, *, diagnosis_as_d1=False):
    from analysis.sample_analysis.analyses import transformed_y
    fig,ax=plt.subplots(figsize=(8,5))
    for i,cohort in enumerate(cohorts):
        data,_=eligible(frame,cohort,'correlations')
        data=plot_data(data, diagnosis_as_d1=diagnosis_as_d1)
        data=data.loc[np.isfinite(data[x]) & np.isfinite(data[y]) & (data[y].ge(0) if y=='dna_total_ng' else data[y].gt(0))]
        ax.scatter(data[x],transformed_y(y,data[y]),label=cohort.capitalize(),s=20,alpha=.65,
                   color=COLORS[cohort],marker=['o','^'][i%2])
    ax.set(xlabel='Initial plasma volume (mL)' if x=='volume_ml' else LABELS.get(x,x),
           ylabel=('log10(1 + total DNA ng)' if y=='dna_total_ng' else 'log10 '+LABELS.get(y,y)),
           title='Plasma — canonical timepoints')
    ax.legend(frameon=False)
    ax.grid(alpha=.2)
    fig.tight_layout();save(fig,path)
