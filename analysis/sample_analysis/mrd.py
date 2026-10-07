"""Patient-level CIRCALL MRD trajectories with explicitly assigned display levels."""
from pathlib import Path
import json
import math

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

from analysis.sample_analysis.preparation import read_sheet, subject_key, text
from analysis.sample_analysis import reporting

FIELDS = {'TP1 (D29)': 'MRD_TP1', 'TP2 (D71)': 'MRD_TP2'}
ORDER = ['D1', *FIELDS]
MISSING = {'', 'na', 'n/a', 'nan', 'none'}


def parse_value(value, coordinate):
    label = ' '.join(text(value).split()).casefold()
    if label in MISSING:
        return 'missing', None
    if label in {'negative', 'neg'}:
        return 'negative', None
    if label in {'unknown significance', 'unknown signif', 'unknown signif.'}:
        return 'unknown_significance', None
    if isinstance(value, bool):
        raise ValueError(f'Invalid MRD value at {coordinate}: boolean')
    try:
        number = float(label.replace(',', '.'))
    except ValueError:
        raise ValueError(f'Unrecognised MRD category at {coordinate}; source entry requires review') from None
    if not math.isfinite(number) or not 0 < number <= 1:
        raise ValueError(f'MRD fraction at {coordinate} must be greater than zero and at most 1; confirm source units')
    return 'quantified', number


def observations(path, *, unknown_level, negative_level):
    for name, value in [('unknown significance', unknown_level), ('negative', negative_level)]:
        if not math.isfinite(value) or not 0 < value <= 1:
            raise ValueError(f'{name} display level must be a fraction greater than zero and at most 1')
    sheet, rows, _ = read_sheet(path, 'cohorte_lal', {'circall_id', *FIELDS.values()})
    patients = {}
    for row in rows:
        key = subject_key('circall', row.value('circall_id'))
        if key is None:
            continue
        patient = patients.setdefault(key, {tp: {} for tp in FIELDS})
        for tp, field in FIELDS.items():
            cell = row.cells[field]
            status, fraction = parse_value(cell.value, cell.coordinate)
            if status == 'missing':
                continue
            patient[tp].setdefault((status, fraction), []).append(cell.coordinate)
    records = []
    for key, visits in sorted(patients.items()):
        if not any(visits.values()):
            continue
        for tp in ORDER:
            values = visits.get(tp, {})
            if len(values) > 1:
                cells = [cell for group in values.values() for cell in group]
                raise ValueError(f'Conflicting patient-level MRD entries at {", ".join(cells)}; no value was selected')
            if tp == 'D1':
                status, fraction, coordinates = 'normalized_baseline', None, []
                displayed = 1.0
                basis = 'diagnostic clone normalised to 100%; not a measured MRD result'
            else:
                ((status, fraction), coordinates) = next(iter(values.items())) if values else (('missing', None), [])
                displayed = {'unknown_significance': unknown_level, 'negative': negative_level}.get(status, fraction)
                basis = 'reported quantitative fraction' if status == 'quantified' else 'user-assigned display level; not a quantified result' if displayed is not None else 'no MRD result supplied'
            records.append({'cohort': 'circall', 'patient_key': key, 'timepoint': tp,
                            'status': status, 'measured_fraction': fraction,
                            'measured_log10_reduction': -math.log10(fraction) if fraction is not None else None,
                            'display_fraction': displayed,
                            'display_log10_reduction': -math.log10(displayed) if displayed is not None else None,
                            'display_basis': basis, 'source_file': str(Path(path).resolve()),
                            'source_sheet': sheet, 'source_column': FIELDS.get(tp, ''),
                            'source_cells': json.dumps(coordinates), 'repeated_source_entries': len(coordinates)})
    if not records:
        raise ValueError('No patient-level CIRCALL MRD results found in MRD_TP1 or MRD_TP2')
    return pd.DataFrame(records)


def summary_table(frame):
    rows = []
    for tp in ORDER:
        group = frame.loc[frame.timepoint.eq(tp)]
        counts = group.status.value_counts()
        rows.append({'timepoint': tp, 'patients': len(group),
                     **{status: int(counts.get(status, 0)) for status in ('normalized_baseline', 'quantified', 'unknown_significance', 'negative', 'missing')},
                     'patients_with_result': int(group.status.isin(['quantified','unknown_significance','negative']).sum())})
    return pd.DataFrame(rows)


def plot(frame, path, *, unknown_level, negative_level):
    fig, ax = plt.subplots(figsize=(7.875, 6.5))
    color = reporting.COLORS['circall']
    rng = np.random.default_rng(42)
    positions = {tp: i for i, tp in enumerate(ORDER)}
    symbols = {'normalized_baseline': 'o', 'quantified': 'o', 'unknown_significance': 'D', 'negative': 'v'}
    for _, patient in frame.groupby('patient_key', sort=True):
        patient = patient.loc[patient.display_fraction.notna()].copy()
        patient['x'] = patient.timepoint.map(positions) + rng.uniform(-.09, .09)
        patient = patient.sort_values('x')
        for first, second in zip(patient.iloc[:-1].itertuples(), patient.iloc[1:].itertuples()):
            assigned = first.status in ('negative','unknown_significance') or second.status in ('negative','unknown_significance')
            ax.plot([first.x,second.x], [first.display_fraction,second.display_fraction],
                    color='#777777', linewidth=.8, alpha=.35, linestyle=':' if assigned else '-')
        for row in patient.itertuples():
            baseline = row.status == 'normalized_baseline'
            ax.scatter(row.x, row.display_fraction, marker=symbols[row.status], s=40,
                       facecolors='none' if row.status=='unknown_significance' else '#777777' if baseline else color,
                       edgecolors='#777777' if baseline else color, linewidths=1.2, alpha=.85, zorder=3)
    ax.set_yscale('log')
    low = min(frame.display_fraction.dropna().min(), unknown_level, negative_level)
    ax.set_ylim(low/3, 2.5)
    for value in (unknown_level, negative_level):
        ax.axhline(value, color='#BBBBBB', linestyle='--', linewidth=.8, zorder=0)
    powers = np.arange(0, math.ceil(-math.log10(low))+1)
    ticks = 10.0**(-powers)
    ax.set_yticks(ticks, [f'{v:.0e}' for v in ticks])
    counts = summary_table(frame).set_index('timepoint')
    labels = []
    for tp in ORDER:
        n = len(frame.patient_key.unique()) if tp=='D1' else int(counts.loc[tp,'patients_with_result'])
        labels.append(f'{tp}\nn={n}')
    ax.set_xticks(range(len(ORDER)), labels)
    ax.set(xlim=(-.35, 2.35), ylabel='Residual clone relative to diagnostic baseline (fraction)',
           title='CIRCALL MRD over time', xlabel='Timepoint')
    ax.grid(axis='y', alpha=.18)
    handles = [Line2D([],[],marker='o',linestyle='',color=color,label='Quantified MRD'),
               Line2D([],[],marker='D',linestyle='',markerfacecolor='none',color=color,
                      label=f'Unknown significance: assigned {unknown_level:g}'),
               Line2D([],[],marker='v',linestyle='',color=color,
                      label=f'Negative: assigned {negative_level:g}')]
    ax.legend(handles=handles,loc='upper center',bbox_to_anchor=(.5,-.17),frameon=False,fontsize=9,ncol=1)
    fig.text(.5,.015,'D1 is normalised to 1. Categorical levels are display conventions, not quantified values.\nDotted segments touch assigned levels; missing results are not plotted.',ha='center',fontsize=9)
    fig.tight_layout(rect=(0,.14,1,1)); reporting.save(fig,path)


def run(path, output, *, unknown_level, negative_level, write_workbook=True):
    output = Path(output); output.mkdir(parents=True, exist_ok=True)
    data = observations(path, unknown_level=unknown_level, negative_level=negative_level)
    summary = summary_table(data)
    reporting.table(output/'circall_mrd_observations.csv', data)
    reporting.table(output/'circall_mrd_summary.csv', summary)
    if write_workbook:
        reporting.workbook(output/'circall_mrd.xlsx', {'summary': summary, 'observations': data})
    settings = {'source': 'cohorte_lal: MRD_TP1 and MRD_TP2, keyed by circall_id',
                'figure_size_inches': [7.875, 6.5],
                'numeric_unit': 'fraction relative to diagnostic clone = 1', 'baseline': 'normalised 100%, not measured',
                'unknown_significance_display_fraction': unknown_level, 'negative_display_fraction': negative_level,
                'categorical_values_are_not_measurements': True, 'assay_detection_limit_inferred': False,
                'missing': 'blank/na/n/a remain missing', 'patient_repeats': 'identical repeated entries collapsed; conflicts fail',
                'violin': 'not estimated: few quantified patients and categorical display levels',
                'patients_with_any_mrd': data.patient_key.nunique()}
    (output/'plot_settings.json').write_text(json.dumps(settings, indent=2)+'\n')
    plot(data,output/'circall_mrd_trajectories.png',unknown_level=unknown_level,negative_level=negative_level)
    print(f'MRD: {settings["patients_with_any_mrd"]} patients; '+', '.join(f'{row.timepoint}: {row.patients_with_result} results ({row.quantified} quantified)' for row in summary.itertuples() if row.timepoint!='D1'))
    return summary
