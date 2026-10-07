"""Excel 2021 workbooks and aggregate, identifier-free figures."""
from collections import Counter, defaultdict
import json
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.comments import Comment
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.table import Table, TableStyleInfo
from openpyxl.utils import get_column_letter

RECEIPT_LABELS = {'received':'Received', 'marked_missing':'Marked missing', 'unassessed':'Unassessed'}

NOTES = [
    ('Observation unit', 'One inventory row is one sample. Repeats are retained; patients are counted distinctly within each view.'),
    ('Population', 'Patients represented in the inventory, not a verified enrollment roster. Main counts show the overall total and specimen/visit breakdown; center detail stays in audit evidence.'),
    ('Receipt', 'Three labels: Received, Marked missing (literal na), Unassessed (blank/unknown ID). Overdue is a separate flag, not another receipt category. Early receipt is excluded from timed percentages until the planned date.'),
    ('Deadline', 'Diagnosis/D4/D8/D15/TP1 only. Planned date midnight Europe/Paris, then 72 elapsed hours. Exactly 72 hours remains pending.'),
    ('Fallback', 'Without a reliable applicable planned date, literal na remains marked missing with lateness unassessed; it is excluded from the overdue percentage denominator.'),
    ('Percentage', 'Timed received / (timed received + overdue missing). Only reliable applicable timing produces percentages; future/pending/unassessed/early rows stay outside that denominator. Marked-missing percentages refer to the overdue subset, not all na rows.'),
    ('Retrospective', 'ID-based receipt counts only; no expected-sample rates. All retrospective samples are attributed to RDB.'),
    ('Assessment', 'Current workbook snapshot evaluated at the recorded assessment timestamp; not reconstructed historical receipt.'),
    ('Extraction', 'Derived from dna_id: filled actual ID means yes; blank/missing ID means no. Missing columns, formula IDs and Excel errors are unavailable. Recorded measurements do not substitute for a DNA ID.'),
    ('Missing annotations', 'Canonical literal marker na means unavailable. Applicability comes from extraction/specimen context. Empty cells and formulas remain unchanged; historical aliases remain readable.'),
    ('cfDNA total amount', 'cfdna_total_ng is the total amount of cfDNA in the extract, in ng.'),
    ('Quantities', 'Received samples only, including early arrivals. Genuine zero retained. No imputation or Excel recalculation.'),
    ('Volumes', 'The legacy extraction_input_volume_ml field records available plasma after centrifugation or available CSF, independently of extraction status. For extracted samples the entire recorded available volume was used. Plasma and CSF remain separate.'),
    ('Concentration plots', 'Logarithmic y-axis in original units. Nonpositive observations are counted but not plotted; boxes use positive values. Tables retain genuine zeros, with no pseudocount.'),
    ('Summaries', 'Sample-based mean, sample SD (n-1), median, linearly interpolated quartiles, min/max. Totals only for mass/volume.'),
    ('Pooling', 'Plasma DNA endpoints, plasma/CSF available volumes and cfDNA fragment size; shared diag/TP1/TP2 visits. Specimens stay separate. One combined box per metric/visit with cohort-colored points; tables retain cohort contributions.'),
    ('Excluded measurements', 'Albumin concentration and DNA integrity number are excluded from Layer 2 descriptions and plots; original source fields remain preserved.'),
    ('Retrospective donor mapping', 'Donor workbook plasma ng/mL endpoint maps to dna_ng_per_ml_plasma, preserving the established workflow. Other metrics and timing metadata are not inferred. Controls are inventory records, not an assessed scheduled-receipt population.'),
    ('Controls', 'Separate descriptive reference; excluded from patient counts, receipt percentages and patient pooling.'),
    ('Unknown categories', 'Unapproved visit/specimen labels are unclassified; no unrestricted source text is exported.'),
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
    ws.sheet_view.showGridLines = False
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


def inventory_records(tables):
    """Pivot existing receipt counts; never add overlapping population views."""
    records = []
    for summary in tables.get('summary', []):
        same = lambda row: all(row.get(k) == summary.get(k) for k in ('view', 'specimen', 'visit'))
        receipt = [row for row in tables.get('receipt', []) if same(row)]
        status = Counter()
        for row in receipt:
            status[row['status']] += row['samples']
        deadline = [row for row in receipt if row['basis'] == 'deadline']
        denominators = {row['classified_denominator'] for row in deadline if row['classified_denominator'] is not None}
        if len(denominators) > 1:
            raise ValueError('Receipt denominators disagree within a report group')
        denominator = next(iter(denominators), 0)
        due_received = sum(row['classified_samples'] or 0 for row in deadline if row['status'] == 'received')
        extraction = [row for row in tables.get('availability', []) if same(row) and row['field'] == 'extraction_status']
        records.append({
            'Specimen': summary.get('specimen', 'All specimens'),
            'Visit': summary.get('visit', 'All visits'),
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
        'Specimen': row['specimen'], 'Visit': row.get('visit', 'All visits'),
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
    visits = {name: i for i, name in enumerate(d['visits'] + ['control', 'unclassified'])}
    ordered = sorted(records, key=lambda row: (
        0 if row.get('Specimen') == 'All specimens' else 1,
        specimens.get(row.get('Specimen'), 99), visits.get(row.get('Visit'), 99),
        row.get('Measurement', ''), row.get('DNA label', '')))
    return [{**row, 'Visit': {'diag': 'Diagnosis', 'control': 'Control'}.get(row.get('Visit'), str(row.get('Visit', '')).upper())}
            for row in ordered]


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
        ws.column_dimensions[letter].width = 32 if header in ('Measurement', 'Issue', 'Patient') else 60 if header in ('Reason', 'description', 'value') else 22 if header == 'Visit' else 20 if header in ('Specimen', 'DNA label', 'Unit') else 16
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
                      'Overall and specimen/visit counts overlap. Overdue is part of Marked missing. Rate = due received / (due received + overdue); blank means not assessed. Hover over a rate for its denominator.')
    records = display_order(inventory_records(tables), d) if complete else [
        {'Issue': row.get('field', ''), 'Reason': row.get('issue', row.get('reason', '')), 'Occurrences': row.get('occurrences')}
        for row in result.get('blocking', [])]
    section(ws, records, empty=empty, hidden=('Due received', 'Timed denominator'))
    if complete and records:
        for i, record in enumerate(records, 6):
            if record['Receipt rate'] is not None:
                ws.cell(i, 10).comment = Comment(f'{record["Due received"]} due received / {record["Timed denominator"]} assessed samples. Pending, future, early and unassessed samples are excluded.', 'Pre-analysis')
        for cell in ws[6]:
            cell.font = Font(bold=True, color='174B59')
    ws = report_sheet(book, 'Measurements', result,
                      'Received samples only; zeros retained. Q1–Q3 describe the middle 50%. DNA label is recorded metadata. Additional statistics are in hidden columns and Reference.')
    hidden = ('Mean', 'SD', 'Minimum', 'Maximum', 'Total', 'Available patients', 'Received samples')
    section(ws, display_order(measurement_records(tables), d) if complete else [], empty=empty, hidden=hidden)
    if result['scope'] != 'pooled' and result['include_controls']:
        ws = report_sheet(book, 'Controls', result, 'Descriptive reference only. Controls are excluded from patient inventory counts and pooled results.')
        controls = result.get('controls', {})
        summary = [{'Specimen': row.get('specimen', 'All specimens'), 'Visit': row.get('visit', 'All visits'),
                    'Participants': row['patients'], 'Control records': row['samples'], 'Received': row['received_samples']}
                   for row in controls.get('summary', [])]
        end = section(ws, display_order(summary, d) if complete else [], start=5, title='Control inventory', empty=empty)
        section(ws, display_order(measurement_records(controls), d) if complete else [], start=end, title='Control measurements', empty=empty, hidden=hidden)
    if result['scope'] == 'circall':
        ws = report_sheet(book, 'Overdue', result, 'Samples explicitly marked na and overdue at the recorded assessment time. Only approved patient pseudonyms appear here.')
        missed = [{'Patient': row['patient_id'], 'Center': row['center'], 'Visit': row['visit'],
                   'Specimen': row['specimen'], 'Reason': row['receipt_reason'],
                   'Source worksheet': row['sheet'], 'Source row': row['row']} for row in tables.get('missed', [])]
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


def figures(destination, rows, d, pooled=False, controls=False):
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    artifacts=[]
    def save(fig, name):
        fig.tight_layout()
        for ext in ('png','pdf'):
            path=destination/f'{name}.{ext}'
            path.parent.mkdir(parents=True, exist_ok=True)
            fig.savefig(path, dpi=150)
            artifacts.append(path)
        plt.close(fig)
    if not pooled and rows:
        fig,ax=plt.subplots(figsize=(10,5))
        counts=Counter(r['receipt'] for r in rows)
        keys=sorted(counts)
        ax.bar(range(len(keys)),[counts[k] for k in keys],color='#247B89')
        ax.set_xticks(range(len(keys)),[RECEIPT_LABELS.get(k,k.replace('_',' ')) for k in keys],rotation=25,ha='right')
        ax.set_ylabel('Samples (inventory rows)')
        ax.set_title(f'Receipt status | n={len(rows)} samples, {len({r["subject_key"] for r in rows})} participants')
        save(fig,'receipt_status')
    for field, definition in d['metrics'].items():
        groups=defaultdict(list)
        for r in rows:
            if r['receipt'] not in ('received','received_early') or r['specimen'] not in definition['specimens'] or r['cohort'] in definition.get('exclude_cohorts',[]):
                continue
            if pooled and (r['specimen'] not in definition['pool'] or r['visit'] not in d['pooled_visits']):
                continue
            value=r['measurements'][field]['value']
            if value is not None:
                assay = 'specimen_volume' if field=='extraction_input_volume_ml' else 'cfDNA_size' if pooled and field=='cfdna_avg_size_bp' else 'plasma_DNA' if r['specimen']=='plasma' else r['assay']
                groups[(r['specimen'],assay)].append(r)
        for (specimen,assay), group in sorted(groups.items()):
            visits=[v for v in d['visits']+['control','unclassified'] if any(r['visit']==v for r in group)]
            cohorts=sorted({r['cohort'] for r in group})
            fig,ax=plt.subplots(figsize=(max(9,len(visits)*1.3),5.5))
            logarithmic=definition.get('plot_scale')=='log'
            if logarithmic:ax.set_yscale('log',base=10,nonpositive='mask')
            labeled=set()
            labels=[]
            for i,visit in enumerate(visits):
                subset=[r for r in group if r['visit']==visit]
                label=f'{visit}\nn={len(subset)}, P={len({r["subject_key"] for r in subset})}'
                if logarithmic:
                    nonpositive=sum(r['measurements'][field]['value']<=0 for r in subset)
                    if nonpositive:label+=f'\n{nonpositive} nonpositive, not plotted'
                labels.append(label)
                combined=pooled and d['pooled_display']=='combined_box_per_visit_with_cohort_points'
                if combined:
                    values=[r['measurements'][field]['value'] for r in subset]
                    if logarithmic:values=[v for v in values if v>0]
                    if values:
                        ax.boxplot([values],positions=[i],widths=.4,showfliers=False,manage_ticks=False,
                                   medianprops={'color':'#52616B'},boxprops={'color':'#52616B'})
                for j,cohort in enumerate(cohorts):
                    values=[r['measurements'][field]['value'] for r in subset if r['cohort']==cohort]
                    if logarithmic:values=[v for v in values if v>0]
                    if not values:continue
                    x=i if combined else i+(j-(len(cohorts)-1)/2)*.3
                    color={'retrospective':'#247B89','circall':'#B75B28'}[cohort]
                    if not combined:
                        ax.boxplot([values],positions=[x],widths=.22,showfliers=False,manage_ticks=False,
                                   medianprops={'color':color},boxprops={'color':color})
                    ax.scatter([x]*len(values),values,color=color,alpha=.5,s=18,label=cohort if cohort not in labeled else None)
                    labeled.add(cohort)
            ax.set_xticks(range(len(visits)),labels,rotation=25,ha='right')
            ax.set_ylabel(definition['unit']+(' (log scale)' if logarithmic else ''))
            specimen_label={'plasma':'Plasma','CSF':'CSF','blood pellet':'Blood pellet','bone marrow':'Bone marrow'}[specimen]
            subtitle=f'{specimen_label} · {"Controls" if controls else "Patient samples"}'
            ax.set_title(f'{field}\n{subtitle}')
            if labeled:ax.legend()
            if logarithmic and any(r['measurements'][field]['value']<=0 for r in group):
                ax.text(0,1.01,'Boxes show positive values; tables retain all values.',transform=ax.transAxes,fontsize=9)
            if logarithmic and not labeled:
                ax.set_ylim(1,10)
                ax.text(.5,.5,'No positive values to plot',transform=ax.transAxes,ha='center')
            suffix=f'__{assay}' if sum(key[0]==specimen for key in groups)>1 else ''
            specimen_dir=specimen.replace(' ','_')
            save(fig,f'{specimen_dir}/{field}{suffix}')
    return artifacts
