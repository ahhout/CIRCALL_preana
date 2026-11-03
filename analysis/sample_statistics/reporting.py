"""Excel 2021 workbooks and aggregate, identifier-free figures."""
from collections import Counter, defaultdict
import json
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.table import Table, TableStyleInfo
from openpyxl.utils import get_column_letter
from analysis.plot_style import COHORT_COLORS, COHORT_MARKERS, COHORT_LABELS, BOX_STYLE, style_axes, save_figure
from analysis.figure_layout import remove_plot_text
from .calendar_volumes import calendar_groups, calendar_coverage, calendar_figure

RECEIPT_LABELS = {'received':'Received', 'marked_missing':'Marked missing', 'unassessed':'Unassessed'}

NOTES = [
    ('Observation unit', 'One inventory row is one sample. Repeats are retained; patients are counted distinctly within each view.'),
    ('Population', 'Patients represented in the inventory, not a verified enrollment roster. Main counts show the overall total, center totals and specimen/timepoint breakdown. These views overlap; never sum across them.'),
    ('Receipt', 'Three labels: Received, Marked missing (literal na), Unassessed (blank/unknown ID). Overdue is a separate flag, not another receipt category. Early receipt is excluded from timed percentages until the planned date.'),
    ('Deadline', 'Diagnosis/D4/D8/D15/TP1 only. Planned date midnight Europe/Paris, then 72 elapsed hours. Exactly 72 hours remains pending.'),
    ('Fallback', 'Without a reliable applicable planned date, literal na remains marked missing with lateness unassessed; it is excluded from the overdue percentage denominator.'),
    ('Overdue status', 'Overdue unreceived samples are Marked missing when explicitly na, otherwise Late. Late is a follow-up flag while receipt remains unassessed. Both require reliable applicable CIRCALL timing beyond 72 hours; future, untimed and retrospective records are not flagged.'),
    ('Percentage', 'Timed received / (timed received + overdue explicitly marked missing). Late remains outside this denominator; it is not confirmed missingness. Future/pending/unassessed/early rows stay excluded. Marked-missing percentages refer to the overdue subset, not all na rows.'),
    ('Retrospective', 'ID-based receipt counts only; no expected-sample rates. All retrospective samples are attributed to RDB.'),
    ('Assessment', 'Current workbook snapshot evaluated at the recorded assessment timestamp; not reconstructed historical receipt.'),
    ('Extraction', 'Derived from dna_id: filled actual ID means yes; blank/missing ID means no. Missing columns, formula IDs and Excel errors are unavailable. Recorded measurements do not substitute for a DNA ID.'),
    ('Missing annotations', 'Canonical literal marker na means unavailable. Applicability comes from extraction/specimen context. Empty cells and formulas remain unchanged; historical aliases remain readable.'),
    ('cfDNA total amount', 'cfdna_total_ng is the total amount of cfDNA in the extract, in ng.'),
    ('Quantities', 'Received samples only, including early arrivals. Genuine zero retained. No imputation or Excel recalculation.'),
    ('Volumes', 'The legacy extraction_input_volume_ml field records available plasma after centrifugation or available CSF, independently of extraction status. For extracted samples the entire recorded available volume was used. Plasma and CSF remain separate.'),
    ('Calendar volumes', 'Additional CIRCALL plasma/CSF available-volume plots use recorded collection dates, received samples and individual sample points. Genuine zeros remain. No planned-date substitution, time jitter, smoothing, tests or performance thresholds. Missing volume and missing collection-date exclusions are reported separately; dates remain local audit metadata.'),
    ('Mass and concentration plots', 'Logarithmic y-axis in original units for DNA/cfDNA total ng and concentrations in ng/µL and ng/mL. Nonpositive observations are counted but not plotted; boxes use positive values. Tables retain genuine zeros, with no pseudocount.'),
    ('Summaries', 'Sample-based mean, sample SD (n-1), median, linearly interpolated quartiles, min/max. Totals only for mass/volume.'),
    ('Pooling', 'Plasma DNA endpoints, plasma/CSF available volumes and cfDNA fragment size; shared diag/TP1/TP2 timepoints in tables. DNA-per-mL patient figures show only Diagnosis, D4, D8, D15, TP1 (D29) and TP2 (D71), including single-cohort timepoints. Validated selected CIRCALL and retrospective controls share one Controls reference bin before Diagnosis. Specimens stay separate. One combined box per metric/timepoint, or across eligible timepoints for overall-display metrics, with cohort-colored points; tables retain cohort contributions.'),
    ('Excluded measurements', 'Albumin concentration and DNA integrity number are excluded from Layer 2 descriptions and plots; original source fields remain preserved.'),
    ('Retrospective donor mapping', 'Donor workbook plasma ng/mL endpoint maps to dna_ng_per_ml_plasma, preserving the established workflow. Other metrics and timing metadata are not inferred. Controls are inventory records, not an assessed scheduled-receipt population.'),
    ('Controls', 'Separate descriptive reference; excluded from patient counts, receipt percentages and patient pooling.'),
    ('Unknown categories', 'Unapproved timepoint/specimen labels are unclassified; no unrestricted source text is exported.'),
    ('DNA-type metadata', 'The legacy assay key records nucleic_acid labels, not a measured assay identity. not_recorded means that label is unavailable, not that the DNA measurement is missing. It is omitted from plot subtitles.'),
    ('Privacy', 'Only the missed checklist uses approved pseudonymous patient IDs. No names, DOB, sample IDs or source free text are exported.'),
]


def table(book, name, records, empty='No applicable observations'):
    ws = book.create_sheet(name)
    if not records:
        records = [{'status': empty}]
    headers = list(dict.fromkeys(k for row in records for k in row))
    ws.append(headers)
    for row in records:
        ws.append([json.dumps(row.get(h), ensure_ascii=False) if isinstance(row.get(h),(dict,list)) else
                   RECEIPT_LABELS.get(row.get(h),row.get(h)) if h=='status' and isinstance(row.get(h),str) else row.get(h) for h in headers])
    for cell in ws[1]:
        cell.font = Font(bold=True, color='FFFFFF')
        cell.fill = PatternFill('solid', fgColor='174B59')
    for row in ws.iter_rows(min_row=2):
        for cell in row:
            # Pseudonyms and metadata are always literal strings, never Excel formulas.
            if isinstance(cell.value, str):
                cell.data_type = 's'
            cell.alignment = Alignment(vertical='top', wrap_text=True)
            if isinstance(cell.value, float):
                cell.number_format = '0.0%' if headers[cell.column-1]=='classified_percentage' else '0.000'
    for i, h in enumerate(headers, 1):
        ws.column_dimensions[get_column_letter(i)].width = 65 if h in ('description','reason','issue','action','value') else min(36,max(16,len(h)+2))
    for i in range(2,ws.max_row+1):
        ws.row_dimensions[i].height = 44
    ws.freeze_panes = 'A2'
    ws.auto_filter.ref = ws.dimensions
    ws.sheet_view.showGridLines = True
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_setup.orientation = 'landscape'
    ws.page_setup.paperSize = ws.PAPERSIZE_A4
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.print_title_rows = '1:1'
    return ws


MEASUREMENT_LABELS = {
    'extraction_input_volume_ml': 'Available specimen volume',
    'elution_volume_ul': 'Elution volume',
    'dna_concentration_ng_per_ul': 'DNA concentration',
    'dna_total_ng': 'DNA total amount',
    'dna_ng_per_ml_plasma': 'DNA per mL plasma',
    'cfdna_fraction': 'cfDNA fraction',
    'cfdna_concentration_ng_per_ul': 'cfDNA concentration',
    'cfdna_total_ng': 'cfDNA total amount',
    'cfdna_ng_per_ml_plasma': 'cfDNA per mL plasma',
    'cfdna_avg_size_bp': 'cfDNA average fragment size',
}


def inventory_records(tables, *, include_specimen_totals=False):
    """Pivot existing counts, including separately identified center totals."""
    records = []
    groups = [(summary, tables) for summary in tables.get('summary', [])]
    detail = tables.get('audit_detail', {})
    if include_specimen_totals:
        existing = {row.get('specimen') for row in tables.get('summary', []) if row.get('view') == 'specimen'}
        groups.extend((row, detail) for row in detail.get('summary', [])
                      if row.get('view') == 'specimen' and row.get('specimen') not in existing)
        center_tissues = {(row['specimen'], row['center']): row
                          for row in detail.get('summary', []) if row.get('view') == 'center_specimen'}
        if center_tissues:
            for specimen in sorted({row['specimen'] for row, _ in groups if row.get('view') == 'specimen'}):
                for center in ('RDB', 'TRS', *(['unknown'] if (specimen, 'unknown') in center_tissues else [])):
                    summary = center_tissues.get((specimen, center), dict(
                        view='center_specimen', specimen=specimen, center=center,
                        samples=0, patients=0, received_samples=0, received_patients=0))
                    groups.append((summary, detail))
    centers = {row['center']:row for row in detail.get('summary', [])
               if row.get('view')=='center' and row.get('center') in ('RDB','TRS','unknown')}
    if any(row.get('view')=='overall' for row in tables.get('summary', [])):
        for center in ('RDB','TRS', *(['unknown'] if 'unknown' in centers else [])):
            summary = centers.get(center, dict(view='center',center=center,samples=0,patients=0,
                                               received_samples=0,received_patients=0))
            groups.append((summary, detail))
    for summary, source in groups:
        same = lambda row: all(row.get(k) == summary.get(k) for k in ('view', 'center', 'specimen', 'visit'))
        receipt = [row for row in source.get('receipt', []) if same(row)]
        status = Counter()
        for row in receipt:
            status[row['status']] += row['samples']
        deadline = [row for row in receipt if row['basis'] == 'deadline']
        denominators = {row['classified_denominator'] for row in deadline if row['classified_denominator'] is not None}
        if len(denominators) > 1:
            raise ValueError('Receipt denominators disagree within a report group')
        denominator = next(iter(denominators), 0)
        due_received = sum(row['classified_samples'] or 0 for row in deadline if row['status'] == 'received')
        extraction = [row for row in source.get('availability', []) if same(row) and row['field'] == 'extraction_status']
        records.append({
            'Specimen': summary.get('specimen', 'All specimens'),
            'Center': {'unknown':'Unknown'}.get(summary.get('center'), summary.get('center', 'All centers')),
            'Timepoint': summary.get('visit', 'All timepoints'),
            'Patients': summary['patients'], 'Inventory samples': summary['samples'],
            'Received': summary['received_samples'],
            'Marked missing': status['marked_missing'] if receipt else None,
            'Unassessed': status['unassessed'] if receipt else None,
            'Overdue': sum(row['overdue_samples'] for row in receipt) if receipt else None,
            'Extracted': sum(row['count'] for row in extraction if row['state'] == 'yes') if any(row['state'] in ('yes', 'no') for row in extraction) else None,
            'Receipt rate': due_received / denominator if denominator else None,
            'Due received': due_received if denominator else None,
            'Timed denominator': denominator or None,
        })
    return records


def measurement_records(tables):
    return [{
        'Specimen': row['specimen'], 'Timepoint': row.get('visit', 'All timepoints'),
        'Measurement': MEASUREMENT_LABELS.get(row['field'], row['field']),
        'DNA label': None if row.get('assay') in ('specimen volume', 'plasma DNA', 'cfDNA size') else row.get('assay', '').replace('not_recorded', 'Not recorded'),
        'Unit': {'mL available specimen': 'mL', 'ng/mL recorded available plasma': 'ng/mL plasma'}.get(row['unit'], row['unit']), 'Measured samples': row['n'],
        'Missing samples': row['unavailable_samples'], 'Median': row['median'],
        'Q1': row['q1'], 'Q3': row['q3'],
        'Mean': row['mean'], 'SD': row['sd'], 'Minimum': row['minimum'],
        'Maximum': row['maximum'], 'Total': row['total'],
        'Available patients': row['available_patients'], 'Received samples': row['received_samples'],
    } for row in tables.get('measurements', [])]


def display_order(records, d):
    specimens = {name: i for i, name in enumerate(('plasma', 'CSF', 'blood pellet', 'bone marrow'))}
    visits = {'All timepoints': -1, **{name: i for i, name in enumerate(d['visits'] + ['control', 'unclassified'])}}
    ordered = sorted(records, key=lambda row: (
        0 if row.get('Specimen') == 'All specimens' else 1,
        specimens.get(row.get('Specimen'), 99),
        0 if row.get('Timepoint') == 'All timepoints' else 1,
        {'All centers':0,'RDB':1,'TRS':2,'Unknown':3}.get(row.get('Center'), 0),
        visits.get(row.get('Timepoint'), 99),
        row.get('Measurement', ''), row.get('DNA label', '')))
    return [{**row, 'Timepoint': display_timepoint(row.get('Timepoint', ''))}
            for row in ordered]


def display_timepoint(value):
    return {'diag':'Diagnosis', 'control':'Control', 'All timepoints':'All timepoints'}.get(value,str(value).upper())


def report_sheet(book, name, result, note):
    ws = book.create_sheet(name)
    ws.cell(1, 1, f'{result["scope"].upper()} · {name}')
    ws.cell(1, 1).font = Font(size=18, bold=True, color='174B59')
    ws.cell(2, 1, f'Status: {result["status"]} | Assessment: {result["metadata"].get("assessment_time", "Unavailable")}')
    ws.cell(3, 1, note)
    ws.cell(3, 1).alignment = Alignment(wrap_text=True, vertical='top')
    ws.row_dimensions[3].height = 32
    ws.freeze_panes = 'C6'
    ws.sheet_view.showGridLines = True
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.page_setup.orientation = 'landscape'
    ws.page_setup.paperSize = ws.PAPERSIZE_A3
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.print_title_rows = '1:5'
    return ws


def section(ws, records, *, start=5, title=None, empty='No applicable observations', hidden=()):
    if title:
        ws.cell(start, 1, title).font = Font(size=13, bold=True, color='174B59')
        start += 1
    records = records or [{'Status': empty}]
    headers = list(dict.fromkeys(key for row in records for key in row))
    for column, header in enumerate(headers, 1):
        cell = ws.cell(start, column, header)
        cell.font = Font(bold=True, color='FFFFFF')
        cell.fill = PatternFill('solid', fgColor='174B59')
        cell.alignment = Alignment(wrap_text=True, vertical='center')
        letter = get_column_letter(column)
        ws.column_dimensions[letter].width = 32 if header in ('Measurement', 'Issue', 'Patient') else 60 if header in ('Reason', 'description', 'value') else 22 if header == 'Timepoint' else 20 if header in ('Specimen', 'DNA label', 'Unit') else 16
        if header in hidden:
            ws.column_dimensions[letter].hidden = True
    ws.row_dimensions[start].height = 30
    for row_index, record in enumerate(records, start + 1):
        for column, header in enumerate(headers, 1):
            value = record.get(header)
            if isinstance(value, (dict, list)):
                value = json.dumps(value, ensure_ascii=False)
            cell = ws.cell(row_index, column, value)
            if isinstance(value, str):
                cell.data_type = 's'
            cell.alignment = Alignment(wrap_text=True, vertical='top')
            if isinstance(value, float):
                cell.number_format = '0.0%' if header == 'Receipt rate' else '0.###'
        ws.row_dimensions[row_index].height = 30
    table_name = f'{ws.title.replace(" ", "_")}_{len(ws.tables) + 1}'
    block = Table(displayName=table_name, ref=f'A{start}:{get_column_letter(len(headers))}{start + len(records)}')
    block.tableStyleInfo = TableStyleInfo(name='TableStyleMedium2', showRowStripes=True)
    ws.add_table(block)
    ws.print_area = f'A1:{get_column_letter(len(headers))}{start + len(records)}'
    return start + len(records) + 3


def workbook(path, result, d):
    book = Workbook()
    book.remove(book.active)
    tables = result.get('tables', {})
    complete = result['status'] == 'complete'
    empty = 'No applicable observations' if complete else 'Blocked: see Inventory for reasons'
    ws = report_sheet(book, 'Inventory', result,
                      'Overall, center and specimen/timepoint rows overlap. Overdue includes Late and overdue Marked missing. Rate = due received / (due received + overdue Marked missing); Late is excluded. Denominators are in hidden columns.')
    records = display_order(inventory_records(tables, include_specimen_totals=result['scope']=='circall'), d) if complete else [
        {'Issue': row.get('field', ''), 'Reason': row.get('issue', row.get('reason', '')), 'Occurrences': row.get('occurrences')}
        for row in result.get('blocking', [])]
    section(ws, records, empty=empty, hidden=('Due received', 'Timed denominator'))
    if complete and records:
        rate_column = list(records[0]).index('Receipt rate') + 1
        for i, record in enumerate(records, 6):
            if record['Receipt rate'] is not None:
                ws.cell(i, rate_column).number_format = '0.0%'
        for cell in ws[6]:
            cell.font = Font(bold=True, color='174B59')
    ws = report_sheet(book, 'Measurements', result,
                      'Received samples only; zeros retained. Q1–Q3 describe the middle 50%. DNA label is recorded metadata. Additional statistics are in hidden columns and Reference.')
    hidden = ('Mean', 'SD', 'Minimum', 'Maximum', 'Total', 'Available patients', 'Received samples')
    section(ws, display_order(measurement_records(tables), d) if complete else [], empty=empty, hidden=hidden)
    if 'comparisons' in result:
        ws=report_sheet(book,'Comparisons',result,
                        'One median per participant/timepoint. Controls: independent Mann–Whitney U; patient timepoints: paired Wilcoxon. Holm correction includes all planned tests; pooled tests combine cohorts.')
        records=[]
        for row in result['comparisons'] if complete else []:
            labels=d['metrics'][row['field']].get('plot_visit_labels',{})
            records.append({'Cohort':row['cohort'],'Measurement':MEASUREMENT_LABELS[row['field']],
                            'Specimen':row['specimen'],'Comparison':f'{labels.get(row["visit_1"],row["visit_1"])} vs {labels.get(row["visit_2"],row["visit_2"])}',
                            'Test':row['test'],'n1':row['n_1'],'n2':row['n_2'],'Matched pairs':row['paired_n'],
                            'Median 1':row['median_1'],'Median 2':row['median_2'],
                            'Raw p':row['p_value'],'Holm p':row['p_adjusted'],'Stars':row['significance'],
                            'Status':row['status'],'Reason':row['reason'],'Method':row['p_method'],
                            'Family size':row['family_size']})
        section(ws,records,empty=empty)
        for row in ws.iter_rows(min_row=6) if records else []:
            for index in (11,12):
                row[index-1].number_format='0.00E+00'
    if result['scope'] != 'pooled' and result['include_controls']:
        ws = report_sheet(book, 'Controls', result, 'Controls remain outside patient descriptive counts; their approved comparison tests are in Comparisons.')
        controls = result.get('controls', {})
        summary = [{'Specimen': row.get('specimen', 'All specimens'), 'Timepoint': row.get('visit', 'All timepoints'),
                    'Participants': row['patients'], 'Control records': row['samples'], 'Received': row['received_samples']}
                   for row in controls.get('summary', [])]
        end = section(ws, display_order(summary, d) if complete else [], start=5, title='Control inventory', empty=empty)
        section(ws, display_order(measurement_records(controls), d) if complete else [], start=end, title='Control measurements', empty=empty, hidden=hidden)
    if result['scope'] == 'circall':
        ws = report_sheet(book, 'Overdue', result, 'Late: overdue and not explicitly na. Marked missing: overdue and explicitly na. Late rows appear first; filter Status to follow up. Only approved patient pseudonyms appear here.')
        missed = [{'Patient': row['patient_id'], 'Center': row['center'], 'Timepoint': display_timepoint(row['visit']),
                   'Specimen': row['specimen'], 'Status': RECEIPT_LABELS.get(row['status'], row['status'].capitalize()),
                   'Source worksheet': row['sheet'], 'Source row': row['row']}
                  for row in sorted(tables.get('missed', []), key=lambda row: row['status']!='late')]
        section(ws, missed if complete else [], empty='No overdue samples' if complete else empty,
                hidden=('Source worksheet', 'Source row'))
    ws = book.create_sheet('Reference')
    ws.sheet_state = 'hidden'
    ws.sheet_view.showGridLines = True
    raw = [{'section': 'Metadata', 'field': key, 'value': value} for key, value in result['metadata'].items()]
    raw += [{'section': 'Blocking', **row} for row in result.get('blocking', [])]
    for key in ('summary', 'receipt', 'measurements', 'availability'):
        raw += [{'section': key, **row} for row in tables.get(key, [])]
    for key in ('summary', 'receipt', 'measurements', 'availability'):
        raw += [{'section': 'controls_' + key, **row} for row in result.get('controls', {}).get(key, [])]
    raw += [{'section': 'Definitions', 'field': key, 'description': value} for key, value in NOTES]
    raw += [{'section': 'Metrics', 'field': key, 'description': value} for key, value in d['metrics'].items()]
    raw += [{'section':'Comparisons',**row} for row in result.get('comparisons',[]) if complete]
    raw += [{'section':'Inference settings','field':key,'value':value} for key,value in d.get('inference',{}).items()]
    section(ws, raw)
    for sheet in book:
        if sheet.title == 'Reference':
            continue
        last_visible = max(column for column in range(1, sheet.max_column + 1)
                           if not sheet.column_dimensions[get_column_letter(column)].hidden)
        for row in (1, 2, 3):
            if last_visible > 1:
                sheet.merge_cells(start_row=row, start_column=1, end_row=row, end_column=last_visible)
        sheet.row_dimensions[1].height = 30
        sheet.row_dimensions[2].height = 24
        sheet.row_dimensions[3].height = 42
        sheet.print_area = f'A1:{get_column_letter(last_visible)}{sheet.max_row}'
    if 'Controls' in book:
        book['Controls'].freeze_panes = 'C7'
    book.active = 0
    if result['scope'] == 'circall':
        from .workbook_french import localize_workbook
        localize_workbook(book)
    book.save(path)
    book.close()


def validate_workbook(path, result, d):
    # Rebuild expected cells in memory using exactly the rendering contract, then compare.
    from tempfile import TemporaryDirectory
    with TemporaryDirectory() as tmp:
        expected = Path(tmp)/'expected.xlsx'
        workbook(expected,result,d)
        a,b = load_workbook(path,read_only=True),load_workbook(expected,read_only=True)
        try:
            if (a.sheetnames!=b.sheetnames or any(list(a[s].values)!=list(b[s].values) for s in a.sheetnames)
                    or any(a[s].sheet_state != b[s].sheet_state for s in a.sheetnames)):
                raise ValueError('Statistics workbook does not reconcile with audit tables')
        finally:
            a.close();b.close()


def grant_figure(group, field, definition, visits, pooled, controls, jitter_seed, comparisons=(), *, scope=None):
    """Original-unit distributions with deterministic display jitter only."""
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib.ticker import LogLocator, NullFormatter, FuncFormatter
    import numpy as np
    import textwrap

    from analysis.plot_style import scatter_points, point_handles
    patient_cohorts = {r['cohort'] for r in group if not r.get('control', False)}
    inferred = patient_cohorts or {r['cohort'] for r in group}
    circall_only = not pooled and (scope == 'circall' if scope is not None else inferred == {'circall'})
    palette=COHORT_COLORS
    markers=COHORT_MARKERS
    cohorts=sorted({r['cohort'] for r in group})
    rng=np.random.default_rng(definition.get('plot_jitter_seed',jitter_seed))
    logarithmic=definition.get('plot_scale')=='log'
    overall=definition.get('plot_grouping')=='overall'
    compact=pooled
    fig,ax=plt.subplots(figsize=(max(7.8,2.4+len(visits)*1.05),5.8))
    fig.subplots_adjust(left=.12,right=.98,bottom=.23,top=.96)
    labels=[]
    visit_labels={'diag':'Diagnosis','d4':'Day 4','d8':'Day 8','d15':'Day 15','control':'Controls',
                  'unclassified':'Unclassified'}
    if field in ('dna_ng_per_ml_plasma', 'cfdna_ng_per_ml_plasma'):
        visit_labels.update({'d4':'D4', 'd8':'D8', 'd15':'D15',
                             'tp1':'TP1 (D29)', 'tp2':'TP2 (D71)'})
    visit_labels.update(definition.get('plot_visit_labels',{}))
    for i,visit in enumerate(visits):
        subset=group if overall else [r for r in group if r['visit']==visit]
        values=[r['measurements'][field]['value'] for r in subset]
        positive=[v for v in values if v>0] if logarithmic else values
        if positive:
            ax.boxplot([positive],positions=[i],widths=.5,showfliers=False,manage_ticks=False,
                       **BOX_STYLE)
        for cohort in cohorts:
            rows=sorted((r for r in subset if r['cohort']==cohort and
                         (not logarithmic or r['measurements'][field]['value']>0)),
                        key=lambda r:r['measurements'][field]['value'])
            points=[r['measurements'][field]['value'] for r in rows]
            scatter_points(ax,i+rng.uniform(-.17,.17,len(points)),points,cohort,
                           [r.get('center','unknown') for r in rows],circall_only=circall_only,
                       s=25,alpha=.7,edgecolors='white',linewidths=.35,zorder=3,label=cohort)
        name=visit_labels.get(visit,visit.upper() if visit.startswith('tp') else visit)
        label=textwrap.fill(name,14)+f'\nn={len(subset)} · P={len({r["subject_key"] for r in subset})}'
        if compact:label=textwrap.fill(name,14)+f'\nn={len(subset)}'
        labels.append(label)
    if logarithmic:
        ax.set_yscale('log',base=10,nonpositive='mask')
        ax.yaxis.set_major_locator(LogLocator(base=10))
        ax.yaxis.set_major_formatter(FuncFormatter(lambda value,_: f'{value:,.0f}' if value>=1 else f'{value:g}'))
        ax.yaxis.set_minor_formatter(NullFormatter())
    ax.set_xticks(range(len(visits)),labels,fontsize=9)
    ax.set_xlim(-.6,len(visits)-.4)
    units={'dna_ng_per_ml_plasma':'DNA (ng/mL plasma)','cfdna_ng_per_ml_plasma':'cfDNA (ng/mL plasma)'}
    ax.set_ylabel(units.get(field,f"{MEASUREMENT_LABELS[field]} ({definition['unit']})"),fontsize=12,labelpad=10)
    ax.set_xlabel('Timepoint' if not controls and not overall else '',fontsize=11,labelpad=12)
    title='DNA yield per mL of plasma' if field=='dna_ng_per_ml_plasma' else MEASUREMENT_LABELS[field]
    specimen_label={'plasma':'Plasma','CSF':'CSF','blood pellet':'Blood pellet','bone marrow':'Bone marrow'}[group[0]['specimen']]
    population='Controls' if controls else 'Patient samples'
    reference=not controls and any(r.get('control',False) for r in group)
    if reference:population+=' + control references'
    ax.set_title(f'{title}\n{specimen_label} · {population}',
                 fontsize=15,fontweight='medium',pad=18)
    if compact:ax.set_title('')
    style_axes(ax)
    ax.tick_params(axis='x',length=0,pad=9)
    handles=[h for c in cohorts for h in point_handles(c,
             [r.get('center','unknown') for r in group if r['cohort']==c],circall_only=circall_only)]
    fig.legend(handles=handles,loc='lower center',bbox_to_anchor=(.55,.065),ncol=len(handles),frameon=False,fontsize=10)
    note='Box: median and IQR; whiskers: 1.5 × IQR. Points: samples. n: samples; P: participants.'
    if logarithmic:note+=' Log y-axis.'
    if pooled:note+='\nBoxes combine available samples across cohorts.' if overall else '\nCohort availability varies by timepoint; boxes combine available samples.'
    if reference:note+='\nControl cohorts share one reference distribution; excluded from patient summaries.'
    if logarithmic and any(r['measurements'][field]['value']<=0 for r in group):
        note+='\nNonpositive values are counted but not plotted; no pseudocount.'
    if not compact:fig.text(.55,.025,note,ha='center',va='top',fontsize=8,color='#52616B')
    if logarithmic and not any(r['measurements'][field]['value']>0 for r in group):
        ax.set_ylim(1,10)
        ax.text(.5,.5,'No positive values to plot',transform=ax.transAxes,ha='center')
    relevant=[r for r in comparisons if r['field']==field and r['specimen']==group[0]['specimen']]
    brackets=[]
    for result in relevant if not controls else []:
        if (result['field']!=field or result['specimen']!=group[0]['specimen'] or not result['display']
                or not result['significance'].startswith('*') or result['visit_2'] not in visits):
            continue
        reference_visits=[definition['reference_control_visit']]
        positions=[visits.index(v) for v in reference_visits if v in visits]
        if positions:
            brackets.append((sum(positions)/len(positions),visits.index(result['visit_2']),result['significance'],result.get('test','')))
    if brackets:
        fig.subplots_adjust(top=.68)
        if not compact:ax.set_title(ax.get_title(),y=1.42,pad=18)
        for level,(left,right,stars,test) in enumerate(brackets):
            y=1.04+level*.15
            ax.plot([left,left,right,right],[y,y+.025,y+.025,y],transform=ax.get_xaxis_transform(),
                    color='#243746',linewidth=1,clip_on=False)
            label=f'{stars}  {test}' if compact and level==len(brackets)-1 and test else stars
            ax.text((left+right)/2,y+.03,label,transform=ax.get_xaxis_transform(),
                    ha='center',va='bottom',fontsize=13,color='#243746')
    if relevant and not controls and not compact:
        note+='\nStars: Holm-adjusted participant-level tests; nonsignificant/unavailable brackets omitted.'
        if pooled:note+=' Controls and patient cohorts combined for testing.'
        elif reference:note+=' Tests use matching-cohort controls only.'
        fig.texts[-1].set_text(note)
    remove_plot_text(fig)
    return fig


def figures(destination, rows, d, pooled=False, controls=False, reference_controls=(), comparisons=(), pdf_output=True):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    artifacts=[]
    def save(fig, name, grant=False):
        if not grant:fig.tight_layout()
        for ext in (('png','pdf') if pdf_output else ('png',)):
            path=destination/f'{name}.{ext}'
            path.parent.mkdir(parents=True, exist_ok=True)
            save_figure(fig,path)
            artifacts.append(path)
        plt.close(fig)
    if not pooled and rows:
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
        save(fig,'receipt_status')
    for field, definition in d['metrics'].items():
        groups=defaultdict(list)
        reference_cohorts=definition.get('reference_control_cohorts',[])
        references=[dict(r,visit=definition['reference_control_visit']) for r in reference_controls
                    if not controls and r.get('control',False) and r['cohort'] in reference_cohorts]
        for r in [*rows,*references]:
            reference=not controls and r.get('control',False) and r['cohort'] in reference_cohorts
            if r['receipt'] not in ('received','received_early') or r['specimen'] not in definition['specimens'] or r['cohort'] in definition.get('exclude_cohorts',[]):
                continue
            if not controls and not reference and 'plot_visits' in definition and r['visit'] not in definition['plot_visits']:
                continue
            if pooled and not reference and (r['specimen'] not in definition['pool'] or
                           definition.get('pooled_plot_visits')!='all' and r['visit'] not in d['pooled_visits']):
                continue
            value=r['measurements'][field]['value']
            if value is not None:
                assay = 'specimen_volume' if field=='extraction_input_volume_ml' else 'cfDNA_size' if pooled and field=='cfdna_avg_size_bp' else 'plasma_DNA' if r['specimen']=='plasma' else r['assay']
                groups[(r['specimen'],assay)].append(r)
        for (specimen,assay), group in sorted(groups.items()):
            overall=definition.get('plot_grouping')=='overall'
            visits=['Overall'] if overall else [v for v in d['visits']+['control','unclassified'] if any(r['visit']==v for r in group)]
            if not controls and 'plot_visits' in definition:
                visits=([definition['reference_control_visit']] if any(r.get('control',False) for r in group) else [])+definition['plot_visits']
            fig=grant_figure(group,field,definition,visits,pooled,controls,d['plot_jitter_seed'],comparisons,
                             scope='pooled' if pooled else rows[0]['cohort'] if rows else None)
            suffix=f'__{assay}' if sum(key[0]==specimen for key in groups)>1 else ''
            save(fig,f'{specimen.replace(" ","_")}/{field}{suffix}',grant=True)
    if not pooled and not controls:
        calendar = calendar_groups(rows, d)
        for coverage in calendar_coverage(rows, d):
            key = (coverage['cohort'], coverage['specimen'])
            fig = calendar_figure(calendar[key], coverage)
            save(fig, f"{coverage['specimen']}/extraction_input_volume_ml_by_collection_date", grant=True)
    return artifacts
