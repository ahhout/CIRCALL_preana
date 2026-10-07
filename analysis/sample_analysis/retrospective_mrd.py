"""Descriptive retrospective TP1/TP2 MRD; approved worst-outcome priority, bounds stay bounds."""
from pathlib import Path
import json
import math
import re

import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
import numpy as np
import pandas as pd

from analysis.sample_analysis import mrd, reporting
from analysis.sample_analysis.preparation import read_sheet, retrospective_timepoint, subject_key, text

FIELD = 'MRD_IgTCR'
SHEET = 'Inventaire'
VISITS = ('tp1', 'tp2')
STATUSES = ('quantified', 'positive_nonquantifiable', 'negative', 'missing')


class MRDConflictError(ValueError):
    def __init__(self, conflicts):
        self.conflicts = conflicts
        super().__init__(f'Conflicting retrospective MRD annotations for {len(conflicts)} patient/visit groups; '
                         'correct Inventaire/MRD_IgTCR before MRD output. No annotation was selected.')


def parse_annotation(value, coordinate):
    label = ' '.join(text(value).split()).casefold()
    match = re.fullmatch(r'pos\s+nq(?:\s*<\s*(.+))?', label)
    if match:
        bound = None
        if match[1] is not None:
            encoded = match[1].replace(' ', '')
            power = re.fullmatch(r'(?:(\d+(?:[.,]\d+)?)[.*×])?10\^?(-\d+)', encoded)
            try:
                bound = (float((power[1] or '1').replace(',', '.')) * 10.0**int(power[2])
                         if power else float(encoded.replace(',', '.')))
            except (ValueError, OverflowError):
                raise ValueError(f'Invalid positive-nonquantifiable MRD bound at {coordinate}') from None
            if not math.isfinite(bound) or not 0 < bound <= 1:
                raise ValueError(f'MRD upper bound at {coordinate} must be a fraction in (0, 1]')
        return 'positive_nonquantifiable', None, bound
    status, fraction = mrd.parse_value(value, coordinate)
    if status == 'unknown_significance':
        raise ValueError(f'Unconfirmed retrospective MRD category at {coordinate}; pos NQ is a separate category')
    return status, fraction, None


def observations(path, *, tissue='Moelle', duplicate_policy='worst'):
    if duplicate_policy not in ('worst', 'error'):
        raise ValueError('MRD duplicate policy must be worst or error')
    if not text(tissue):
        raise ValueError('Retrospective MRD tissue filter must be nonempty')
    sheet, rows, _ = read_sheet(path, SHEET, {'lastname', FIELD, 'treatment_phase', 'tissue'})
    patients, phase_cells = {}, {}
    for row in rows:
        if text(row.value('tissue')).casefold() != text(tissue).casefold():
            continue
        visit = retrospective_timepoint(row.value('treatment_phase'))
        if visit not in VISITS:
            continue
        cell = row.cells[FIELD]
        annotation = parse_annotation(cell.value, cell.coordinate)
        key = subject_key('retrospective', row.value('lastname'))
        if key is None:
            if annotation[0] != 'missing':
                raise ValueError(f'Retrospective MRD at {cell.coordinate} has no usable subject identity')
            continue
        values = patients.setdefault((key, visit), {})
        phase_cells.setdefault((key, visit), []).append(row.cells['treatment_phase'].coordinate)
        if annotation[0] != 'missing':
            values.setdefault(annotation, []).append(cell.coordinate)
    conflicts = []
    records = []
    for (key, visit), values in sorted(patients.items()):
        if len(values) > 1 and duplicate_policy == 'error':
            conflicts.append(dict(source_file=str(Path(path).resolve()), source_sheet=sheet,
                source_column=FIELD, timepoint=visit.upper(),
                treatment_phase_cells=json.dumps(phase_cells[key, visit]), source_cells=json.dumps(sorted(c for cells in values.values() for c in cells)),
                distinct_annotations=len(values), statuses='; '.join(sorted({v[0] for v in values}))))
            continue
        if values:
            priority = {'negative': 0, 'positive_nonquantifiable': 1, 'quantified': 2}
            def rank(annotation):
                status, fraction, bound = annotation
                magnitude = fraction if fraction is not None else bound
                return priority[status], magnitude if magnitude is not None else float('-inf')
            chosen = max(values, key=rank)
            (status, fraction, bound), cells = chosen, values[chosen]
        else:
            (status, fraction, bound), cells = ('missing', None, None), []
        records.append(dict(cohort='retrospective', patient_key=key, timepoint=visit.upper(), status=status,
            measured_fraction=fraction, measured_log10_reduction=-math.log10(fraction) if fraction is not None else None,
            reported_upper_bound_fraction=bound, source_cells=json.dumps(cells), repeated_source_entries=len(cells),
            distinct_source_annotations=len(values), resolved_disagreement=len(values)>1,
            all_source_cells=json.dumps(sorted(c for cells in values.values() for c in cells))))
    if conflicts:
        raise MRDConflictError(conflicts)
    if not records:
        raise ValueError('No identified retrospective TP1/TP2 patient visits available for MRD')
    return pd.DataFrame(records)


def summary_table(frame):
    rows = []
    for visit in VISITS:
        group = frame.loc[frame.timepoint.eq(visit.upper())]
        counts = group.status.value_counts()
        rows.append(dict(cohort='retrospective', timepoint=visit.upper(), patients=len(group),
            **{status:int(counts.get(status, 0)) for status in STATUSES},
            patients_with_result=int(group.status.ne('missing').sum()),
            resolved_disagreements=int(group.resolved_disagreement.sum()),
            positive_nonquantifiable_with_bound=int((group.status.eq('positive_nonquantifiable') &
                                                      group.reported_upper_bound_fraction.notna()).sum())))
    return pd.DataFrame(rows)


def plot(frame, path, *, negative_level):
    fig, ax = plt.subplots(figsize=(7, 6))
    rng = np.random.default_rng(42)
    color = reporting.COLORS['retrospective']
    positions = {v.upper():i for i,v in enumerate(VISITS)}
    levels = [negative_level]
    for _, patient in frame.groupby('patient_key', sort=True):
        jitter = rng.uniform(-.1,.1)
        quantified = patient.loc[patient.status.eq('quantified')].copy()
        if len(quantified) == 2:
            quantified = quantified.sort_values('timepoint')
            ax.plot(quantified.timepoint.map(positions)+jitter, quantified.measured_fraction,
                    color=color, linewidth=.7, alpha=.3)
        for row in patient.itertuples():
            value = row.measured_fraction if row.status == 'quantified' else row.reported_upper_bound_fraction
            if row.status == 'negative':
                value = negative_level
            if row.status == 'missing' or pd.isna(value):
                continue
            levels.append(value)
            bounded = row.status == 'positive_nonquantifiable'
            ax.scatter(positions[row.timepoint]+jitter, value,
                marker='v' if bounded or row.status=='negative' else 'o',
                facecolors='none' if bounded else color, edgecolors=color, s=45)
    low = min(levels)
    ax.set_yscale('log')
    ax.set_ylim(low/3, max(levels)*3)
    counts = summary_table(frame)
    ax.set_xticks(range(len(VISITS)), [f'{r.timepoint}\nn={r.patients_with_result} results' for r in counts.itertuples()])
    ax.set(xlim=(-.4,1.4), ylabel='MRD residual fraction', title='Retrospective MRD by treatment phase')
    ax.grid(axis='y', alpha=.2)
    ax.legend(handles=[Line2D([],[],marker='o',linestyle='',color=color,label='Quantified MRD'),
        Line2D([],[],marker='v',linestyle='',color=color,markerfacecolor='none',label='Pos NQ: reported upper bound, not a measurement'),
        Line2D([],[],marker='v',linestyle='',color=color,label=f'Negative: assigned display level {negative_level:g}')],
        loc='upper center',bbox_to_anchor=(.5,-.12),frameon=False,fontsize=8)
    unbounded=int((frame.status.eq('positive_nonquantifiable') & frame.reported_upper_bound_fraction.isna()).sum())
    fig.text(.5,.015,f'One annotation per patient/visit. Lines connect quantified pairs only; no inferred calendar days.\n'
             f'Pos NQ without a bound: {unbounded} (counted, not positioned). Negative levels are display conventions.',
             ha='center',fontsize=8)
    fig.tight_layout(rect=(0,.17,1,1))
    reporting.save(fig,path)


def run(path, output, *, negative_level, tissue='Moelle', duplicate_policy='worst'):
    if not math.isfinite(negative_level) or not 0 < negative_level <= 1:
        raise ValueError('Negative MRD display level must be a fraction in (0, 1]')
    frame = observations(path, tissue=tissue, duplicate_policy=duplicate_policy)  # Validate all annotations before creating any MRD outputs.
    summary = summary_table(frame)
    output = Path(output); output.mkdir(parents=True, exist_ok=True)
    reporting.table(output/'retrospective_mrd_summary.csv', summary)
    settings = dict(source_file=str(Path(path).resolve()), source_sheet=SHEET, source_column=FIELD,
        timepoints=['TP1', 'TP2'], phase_column='treatment_phase', calendar_days=None,
        tissue_column='tissue', tissue_filter=text(tissue), tissue_matching='trimmed, case-insensitive exact match', numeric_unit='residual fraction; same scale as CIRCALL',
        log10_reduction='-log10(measured_fraction)',
        identity='existing retrospective surname-based subject_key; retained in memory only',
        annotation_scope='selected tissue, patient and recorded treatment_phase; only tp1/tp2; other phases excluded',
        duplicate_policy=duplicate_policy,
        duplicates='numeric > pos NQ > negative; highest numeric fraction, then highest reported pos NQ bound within category; identical annotations collapse' if duplicate_policy=='worst' else 'within-visit conflicts stop output',
        resolved_disagreements=int(frame.resolved_disagreement.sum()),
        positive_nonquantifiable='pos NQ; < limits retained as reported upper bounds, never measurements or inferred detection limits',
        negative_display_fraction=negative_level, row_level_export=False,
        inference='descriptive only; no cohort pooling or hypothesis tests')
    (output/'retrospective_plot_settings.json').write_text(json.dumps(settings,indent=2)+'\n')
    plot(frame,output/'retrospective_mrd_trajectories.png',negative_level=negative_level)
    print('Retrospective MRD: ' + ', '.join(f'{r.timepoint}: {r.patients_with_result} results' for r in summary.itertuples()))
    return summary
