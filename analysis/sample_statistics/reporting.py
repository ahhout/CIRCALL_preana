"""Excel 2021 workbooks and aggregate, identifier-free figures."""
from collections import Counter, defaultdict
import json
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter


NOTES = [
    ('Observation unit', 'One inventory row is one sample. Repeats are retained; patients are counted distinctly within each view.'),
    ('Population', 'Patients represented in the inventory, not a verified enrollment roster. Separate views overlap: do not add their totals.'),
    ('Receipt', 'Actual sample ID is receipt evidence; literal na explicitly marks missingness. Blank/unknown IDs are unassessed. Early receipt is excluded from due percentages until its planned date.'),
    ('Deadline', 'Diagnosis/D4/D8/D15/TP1 only. Planned date midnight Europe/Paris, then 72 elapsed hours. Exactly 72 hours remains pending.'),
    ('Fallback', 'Without a reliable applicable planned date, literal na remains marked missing with lateness unassessed; it is excluded from the overdue percentage denominator.'),
    ('Percentage', 'Received / (received + missed) within the stated classification basis. Pending/future/unassessed/early rows excluded.'),
    ('Retrospective', 'ID-based receipt counts only; no expected-sample rates. All retrospective samples are attributed to RDB.'),
    ('Assessment', 'Current workbook snapshot evaluated at the recorded assessment timestamp; not reconstructed historical receipt.'),
    ('Extraction', 'Derived from dna_id: filled actual ID means yes; blank/missing ID means no. Missing columns, formula IDs and Excel errors are unavailable. Recorded measurements do not substitute for a DNA ID.'),
    ('Missing annotations', 'Canonical literal marker is na. Empty cells and formulas remain unchanged; historical aliases remain readable.'),
    ('cfDNA total amount', 'cfdna_total_ng is the total amount of cfDNA in the extract, in ng.'),
    ('Quantities', 'Received samples only, including early arrivals. Genuine zero retained. No imputation or Excel recalculation.'),
    ('Volumes', 'The legacy extraction_input_volume_ml field records available plasma after centrifugation or available CSF, independently of extraction status. For extracted samples the entire recorded available volume was used. Plasma and CSF remain separate.'),
    ('Concentration plots', 'Logarithmic y-axis in original units. Nonpositive observations are counted but not plotted; boxes use positive values. Tables retain genuine zeros, with no pseudocount.'),
    ('Summaries', 'Sample-based mean, sample SD (n-1), median, linearly interpolated quartiles, min/max. Totals only for mass/volume.'),
    ('Pooling', 'Approved plasma DNA endpoints and plasma/CSF input volumes only; shared diag/TP1/TP2 visits. Cohort contributions remain explicit.'),
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
        ws.append([json.dumps(row.get(h), ensure_ascii=False) if isinstance(row.get(h),(dict,list)) else row.get(h) for h in headers])
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


def workbook(path, result, d):
    book = Workbook()
    book.remove(book.active)
    meta = [{'kind':'run', 'field': k, 'value':v} for k,v in result['metadata'].items()]
    reasons = [{'kind':'blocked', **r} for r in result.get('blocking',[])]
    table(book, 'Summary', meta + reasons + result.get('tables',{}).get('summary',[]))
    for title,key in [('Receipt','receipt'),('Measurements','measurements'),('Availability','availability')]:
        table(book,title,result.get('tables',{}).get(key,[]), 'Blocked: see Summary' if result['status']!='complete' else 'No applicable observations')
    if result['scope']=='circall':
        table(book,'Missed samples',result.get('tables',{}).get('missed',[]), 'Blocked: see Summary' if result['status']!='complete' else 'No missed samples')
    if result['scope']!='pooled' and result['include_controls']:
        records = [{'section':section,**row} for section,values in result.get('controls',{}).items() if section!='missed' for row in values]
        table(book,'Controls',records,'Blocked: see Summary' if result['status']!='complete' else 'No control observations')
    definitions = [{'field':k,'description':v} for k,v in NOTES]
    definitions += [{'field':f, 'description':json.dumps(value,ensure_ascii=False)} for f,value in d['metrics'].items()]
    table(book,'Definitions',definitions)
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
            if a.sheetnames!=b.sheetnames or any(list(a[s].values)!=list(b[s].values) for s in a.sheetnames):
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
        ax.set_xticks(range(len(keys)),[k.replace('_',' ') for k in keys],rotation=25,ha='right')
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
                assay = 'specimen_volume' if field=='extraction_input_volume_ml' else 'plasma_DNA' if r['specimen']=='plasma' else r['assay']
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
                for j,cohort in enumerate(cohorts):
                    values=[r['measurements'][field]['value'] for r in subset if r['cohort']==cohort]
                    if logarithmic:values=[v for v in values if v>0]
                    if not values:continue
                    x=i+(j-(len(cohorts)-1)/2)*.3
                    color={'retrospective':'#247B89','circall':'#B75B28'}[cohort]
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
