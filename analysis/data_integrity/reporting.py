"""Excel 2021 reports: grouped findings, with references strictly below ten."""
from collections import Counter
from pathlib import Path

from openpyxl import Workbook, load_workbook
from openpyxl.chart import BarChart, Reference
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

TABS = ['Summary','Issues','Coverage','Definitions']
ISSUE_HEADERS = ['Severity','Source workbook','Sheet','Field','Issue','Occurrences','Cell references','Suggested action','Rule','Category','Context']


def issue_row(group):
    context='; '.join(f'{label}: {count}/{group["count"]} occurrences' for label,count in group.get('context_counts',{}).items())
    return [group['severity'],Path(group['source']).name,group['sheet'],group['field'],group['issue'],group['count'],
            ', '.join(group['cells']) or None,group['action'],group['rule'],group['category'],context or None]


def put(ws,row,col,value):
    cell=ws.cell(row,col,value)
    if isinstance(value,str):
        cell.data_type='s'  # Source/configuration strings never become Excel formulas.
    cell.font=Font(name='Calibri',size=11)
    cell.alignment=Alignment(vertical='top',wrap_text=True)
    return cell


def table(wb,name,headers,rows,widths):
    ws=wb.create_sheet(name)
    ws.sheet_view.showGridLines=False
    put(ws,1,1,name).font=Font(name='Calibri',size=17,bold=True,color='19364A')
    for col,(header,width) in enumerate(zip(headers,widths),1):
        cell=put(ws,4,col,header)
        cell.font=Font(name='Calibri',bold=True,color='FFFFFF')
        cell.fill=PatternFill('solid',fgColor='19364A')
        ws.column_dimensions[get_column_letter(col)].width=width
    ws.row_dimensions[4].height=32
    for r,values in enumerate(rows,5):
        for c,value in enumerate(values,1):
            cell=put(ws,r,c,value)
            color='FFF0D7' if name=='Issues' and values[0]=='review' else 'FBE4E5' if name=='Issues' and values[0]=='error' else 'F1F6F8' if r%2 else 'FFFFFF'
            cell.fill=PatternFill('solid',fgColor=color)
        ws.row_dimensions[r].height=65 if name=='Issues' else 45
    ws.auto_filter.ref=f'A4:{get_column_letter(len(headers))}{max(4,4+len(rows))}'
    ws.freeze_panes='D5' if name=='Issues' else 'A5'
    ws.sheet_view.zoomScale=85
    ws.print_title_rows='1:4'
    ws.page_setup.orientation='landscape'
    ws.page_setup.fitToWidth=1
    ws.page_setup.fitToHeight=0
    return ws


def write_workbook(path, result, rules, source_hash):
    wb=Workbook();wb.remove(wb.active)
    ws=wb.create_sheet('Summary');ws.sheet_view.showGridLines=False
    summary=result['summary']
    rows=[['Data integrity — '+result['cohort']],[],['Data quality',summary['quality_status']],
          ['Report generation','complete'],['Error occurrences',summary['errors']],
          ['Review occurrences',summary['reviews']],['Unique affected data rows',summary['affected_rows']],
          ['Source workbook',result['source']],['Source SHA-256',source_hash or 'Unavailable'],
          ['Rows inspected',sum(s['rows'] for s in result['sheets'])],[],
          ['Sheet','Rows inspected','Error occurrences','Review occurrences','Affected rows','Inspection status']]
    from .checks import summarize
    for sheet in result['sheets']:
        counts=summarize([i for i in result['findings'] if i['sheet']==sheet['sheet']])
        rows.append([sheet['sheet'],sheet['rows'],counts['errors'],counts['reviews'],counts['affected_rows'],sheet['status']])
    rows.extend([[],['How to count','Occurrences count distinct affected cells per sheet/field/rule/severity; structural problems count once per scope.'],
                 ['Cell references','Shown for 1–9 occurrences; blank for 10 or more. Complete findings remain in the audit JSON.'],
                 ['Scope','Inventory integrity only; controls are separate; identifiers and clinical interpretation remain deferred.'],
                 ['Interpretation','No issues detected means no issues under the checks performed; see Coverage for unassessed fields.']])
    rows.extend([[],['Unique affected cells',summary['affected_cells']],['Unique cells with errors',summary['error_cells']],
                 ['Unique cells requiring review',summary['review_cells']],['Unique data rows with errors',summary['error_rows']],
                 ['Unique data rows requiring review',summary['review_rows']],
                 ['Context','Future-visit rows remain subject to formula checks. A conflicting extraction status is a logic error even if the correct replacement is not yet known.']])
    for source in result.get('additional_sources',[]):
        rows.extend([['Additional control source',source['source']],['Control source SHA-256',source.get('sha256') or 'Unavailable']])
    for r,values in enumerate(rows,1):
        for c,value in enumerate(values,1):put(ws,r,c,value)
        ws.row_dimensions[r].height=35 if r<16 else 65
    for col in 'ABCDEF':ws.column_dimensions[col].width=28
    ws.column_dimensions['B'].width=65
    ws.column_dimensions['H'].width=38
    ws.column_dimensions['I'].width=16
    ws.column_dimensions['J'].width=16
    for r in range(14+len(result['sheets']),18+len(result['sheets'])):
        ws.merge_cells(start_row=r,start_column=2,end_row=r,end_column=6)
        ws.row_dimensions[r].height=45
    ws.freeze_panes='A3'
    for col,label in enumerate(['Rule','Errors','Reviews'],8):put(ws,3,col,label)
    by_rule=Counter()
    for g in result['groups']:by_rule[g['rule'],g['severity']]+=g['count']
    names=sorted({key[0] for key in by_rule})
    for r,name in enumerate(names,4):
        put(ws,r,8,name);put(ws,r,9,by_rule[name,'error']);put(ws,r,10,by_rule[name,'review'])
    if names:
        chart=BarChart();chart.type='bar';chart.title='Issue occurrences by rule and severity'
        chart.add_data(Reference(ws,min_col=9,max_col=10,min_row=3,max_row=3+len(names)),titles_from_data=True)
        chart.set_categories(Reference(ws,min_col=8,min_row=4,max_row=3+len(names)))
        chart.width=25;chart.height=max(12,min(28,len(names)*1.1));ws.add_chart(chart,'L3')
    issue_rows=[issue_row(g) for g in result['groups']]
    table(wb,'Issues',ISSUE_HEADERS,issue_rows,[12,35,22,35,43,14,45,65,28,18,65])
    table(wb,'Coverage',['Sheet','Field','Check','Assessed','Unavailable / not applicable','Reason'],
          [[c[k] for k in ['sheet','field','check','assessed','unavailable','reason']] for c in result['coverage']],
          [22,38,30,14,25,65])
    definitions=[['Field',name,d['unit'],d['description']] for name,d in rules['fields'].items()]
    if result.get('additional_sources'):
        from analysis.retrospective_controls import NUMERIC
        definitions += [['Control field',name,unit,'Recorded donor field; fixed-volume formula assumptions are not independently validated.'] for name,unit in NUMERIC.items()]
        definitions += [['Control mapping','Conc ng/mL  plasma','ng/mL','Retrospective control plasma DNA endpoint; existing workflow maps this to dna_ng_per_ml_plasma. Other extraction metadata are not inferred.']]
    definitions += [['Rule',name,values[0],values[1]+'. '+values[2]] for name,values in rules['rules'].items()]
    definitions += [['Category',name,category,'Classification of the rule; severity determines whether the run fails.'] for name,category in rules['rule_categories'].items()]
    definitions += [['Calculation',c['output'],c['operation'],' × '.join(c['operands']) if c['operation']=='multiply' else ' / '.join(c['operands'])] for c in rules['calculations']]
    definitions += [['Setting','Arithmetic tolerance','rtol / atol',f"{rules['rtol']} / {rules['atol']}"],
                    ['Setting','Reference threshold','occurrences','All references for 1–9; none for 10+.'],
                    ['Setting','Identifier handling','deferred','No identifier validation, normalization, matching or exports.'],
                    ['Setting','Explicit unknown','?','Unknown differs from blank, zero and not applicable; see Coverage.'],
                    ['Setting','Not extracted','extraction_status','Dependent calculations are not applicable; preserved contradictory values remain logic errors requiring resolution.'],
                    ['Setting','Measurement basis','volume','extraction_input_volume_ml records available plasma/CSF volume independently of extraction status; the whole recorded volume is used when extracted.']]
    table(wb,'Definitions',['Kind','Field / rule','Unit / severity / operation','Definition'],definitions,[18,40,28,90])
    wb.properties.title='Data integrity — '+result['cohort']
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open('xb') as stream:wb.save(stream)
    validate_workbook(path,result)


def validate_workbook(path,result):
    wb=load_workbook(path,read_only=False,data_only=False)
    try:
        if wb.sheetnames!=TABS:
            raise ValueError('Integrity workbook tabs differ from the publication contract')
        ws=wb['Issues']
        rows=list(ws.iter_rows(min_row=5,values_only=True)) if ws.max_row>=5 else []
        expected=[issue_row(g) for g in result['groups']]
        if [list(r) for r in rows]!=expected:
            raise ValueError('Integrity issue groups do not match the source findings')
        for row in rows:
            if row[5]>=10 and row[6] is not None:
                raise ValueError('Cell references exceed the approved display threshold')
        for row,key in [(5,'errors'),(6,'reviews'),(7,'affected_rows')]:
            if wb['Summary'].cell(row,2).value!=result['summary'][key]:
                raise ValueError('Integrity summary counts do not reconcile')
        labels={r[0].value:r[1].value for r in wb['Summary'].iter_rows() if len(r)>1}
        for label,key in [('Unique affected cells','affected_cells'),('Unique cells with errors','error_cells'),
                          ('Unique cells requiring review','review_cells'),('Unique data rows with errors','error_rows'),
                          ('Unique data rows requiring review','review_rows')]:
            if labels.get(label)!=result['summary'][key]:raise ValueError('Unique issue counts do not reconcile')
        if any(cell.data_type=='f' for sheet in wb for row in sheet for cell in row):
            raise ValueError('Report contains an unexpected formula')
    finally:
        wb.close()
