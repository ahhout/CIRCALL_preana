"""Excel 2021 workbooks and compatibility imports for Layer 2 figures."""
from analysis.sample_statistics.report_records import inventory_records, measurement_records, display_order, display_timepoint
import json
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.table import Table, TableStyleInfo
from openpyxl.utils import get_column_letter
from .labels import RECEIPT_LABELS, MEASUREMENT_LABELS
from .figures import grant_figure, figures


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
