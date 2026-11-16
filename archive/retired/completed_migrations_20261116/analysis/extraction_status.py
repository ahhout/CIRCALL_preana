"""Consolidate explicit not-extracted notes in new workbook copies.

Only explicit 'pas extrait' extraction-date notes establish not_extracted. Add an
extraction_status column, clear dependent text notes on those rows, and preserve
numbers, identifiers and formulas. Numeric contradictions are reported for review.
"""
import argparse
from collections import Counter
from datetime import datetime, timezone
from html import escape
import json
from pathlib import Path
import posixpath
import re
import sys
import warnings
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter

from analysis.provenance import ROOT, digest
from analysis.maintenance.xlsx_patch import CELL, ROW, cell_xml
from analysis.maintenance.workbook_cleanup import NS, REL, numeric

DIMENSION = re.compile(rb'<dimension\b[^>]*\bref="([^"]+)"[^>]*/>')


def plan_changes(path, selected, dependent):
    changes, conflicts = {}, []
    with warnings.catch_warnings():
        warnings.simplefilter('ignore',UserWarning)
        raw=load_workbook(path,read_only=True,data_only=False)
        cached=load_workbook(path,read_only=True,data_only=True)
        try:
            for name in selected:
                if name not in raw.sheetnames:
                    raise ValueError('A selected sheet is missing')
                rows=list(raw[name].iter_rows());values=list(cached[name].iter_rows())
                headers=[c.value for c in rows[0]]
                if 'extraction_status' in headers:
                    raise ValueError('An extraction_status column already exists; review instead of replacing it')
                named=[h for h in headers if h]
                if len(named)!=len(set(named)):
                    raise ValueError('Duplicate source headers')
                ix={h:i for i,h in enumerate(headers) if h}
                if 'extraction_date' not in ix:
                    raise ValueError('Extraction-date header missing')
                new_col=get_column_letter(len(headers)+1)
                edits={new_col+'1':{'field':'extraction_status','value':'extraction_status','operation':'add_status_header'}}
                for i,row in enumerate(rows[1:],1):
                    date=values[i][ix['extraction_date']].value
                    if str(date).strip().casefold()!='pas extrait':
                        continue
                    edits[new_col+str(i+1)]={'field':'extraction_status','value':'not_extracted','operation':'set_explicit_status'}
                    for field in dependent:
                        if field not in ix:
                            continue
                        cell=row[ix[field]];value=values[i][ix[field]].value
                        if numeric(value):
                            conflicts.append({'sheet':name,'cell':cell.coordinate,'field':field,'reason':'numeric_value_preserved_on_not_extracted_row'})
                            continue
                        if cell.data_type=='f':
                            if value not in (None,''):
                                conflicts.append({'sheet':name,'cell':cell.coordinate,'field':field,'reason':'nonempty_formula_preserved_on_not_extracted_row'})
                            continue
                        if cell.value is not None:
                            edits[cell.coordinate]={'field':field,'value':None,'operation':'clear_inapplicable_text'}
                changes[name]={'edits':edits,'new_column':new_col,'last_row':len(rows),
                               'header_style':getattr(rows[0][0],'style_id',0)}
        finally:
            raw.close();cached.close()
    return changes,conflicts




def normalize(path,destination,selected,dependent):
    before=digest(path)
    planned,conflicts=plan_changes(path,selected,dependent)
    patches={};reverse={}
    with ZipFile(path) as source:
        if any(n.startswith('xl/tables/') for n in source.namelist()):
            raise ValueError('Excel table schema requires separate migration')
        rels={e.attrib['Id']:e.attrib['Target'] for e in ET.fromstring(source.read('xl/_rels/workbook.xml.rels'))}
        for sheet in ET.fromstring(source.read('xl/workbook.xml')).find('m:sheets',NS):
            name=sheet.attrib['name']
            if name not in planned:continue
            spec=planned[name];wanted=spec['edits'];changes={};seen=set()
            target=rels[sheet.attrib[REL]]
            member=target.lstrip('/') if target.startswith('/') else posixpath.normpath('xl/'+target)
            original=source.read(member)
            def patch_row(match):
                row=int(match.group(2));body=match.group(3)
                def patch_cell(m):
                    coord=m.group(1).decode()
                    if coord not in wanted:return m.group(0)
                    if b'<f' in m.group(0):raise ValueError('Refusing to clear a formula')
                    changes[coord]=m.group(0);seen.add(coord)
                    return cell_xml(coord,wanted[coord]['value'],m.group(0))
                body=CELL.sub(patch_cell,body)
                coord=spec['new_column']+str(row)
                if coord in wanted and coord not in seen:
                    changes[coord]=b'';seen.add(coord)
                    body+=cell_xml(coord,wanted[coord]['value'],style=spec['header_style'] if row==1 else None)
                return match.group(1)+body+match.group(4)
            modified=ROW.sub(patch_row,original)
            if seen!=set(wanted):raise ValueError('Some target cells could not be located')
            dim=DIMENSION.search(modified)
            if dim is None:raise ValueError('Worksheet dimension missing')
            old_dimension=dim.group(0)
            start=dim.group(1).split(b':')[0]
            lastrow=max(spec['last_row'],int(re.search(rb'[0-9]+$',dim.group(1)).group()))
            new_dimension=b'<dimension ref="'+start+b':'+spec['new_column'].encode()+str(lastrow).encode()+b'"/>'
            modified=modified[:dim.start()]+new_dimension+modified[dim.end():]
            ET.fromstring(modified)
            restored=CELL.sub(lambda m:changes.get(m.group(1).decode(),m.group(0)),modified)
            restored=restored.replace(new_dimension,old_dimension,1)
            if restored!=original:raise ValueError('Unexpected workbook alteration')
            patches[member]=modified;reverse[member]=(changes,new_dimension,old_dimension)
        with destination.open('xb') as stream,ZipFile(stream,'w') as output:
            output.comment=source.comment
            for info in source.infolist():output.writestr(info,patches.get(info.filename,source.read(info.filename)))
    with ZipFile(path) as old,ZipFile(destination) as new:
        if old.namelist()!=new.namelist() or new.testzip() is not None:raise ValueError('Archive verification failed')
        for member in old.namelist():
            data=new.read(member)
            if member in reverse:
                edits,newdim,olddim=reverse[member]
                data=CELL.sub(lambda m:edits.get(m.group(1).decode(),m.group(0)),data).replace(newdim,olddim,1)
            if data!=old.read(member):raise ValueError('Source content preservation failed')
    with warnings.catch_warnings():
        warnings.simplefilter('ignore',UserWarning)
        wb=load_workbook(destination,read_only=True,data_only=False)
        try:
            for name,spec in planned.items():
                actual={c.coordinate:c.value for row in wb[name].iter_rows() for c in row if getattr(c,'coordinate',None) in spec['edits']}
                expected={coord:e['value'] for coord,e in spec['edits'].items()}
                if actual!=expected:raise ValueError('Reopened cell verification failed')
        finally:wb.close()
    if digest(path)!=before:raise ValueError('Input changed during correction')
    events=[{'sheet':name,'cell':coord,'field':e['field'],'operation':e['operation']}
            for name,spec in planned.items() for coord,e in spec['edits'].items()]
    return {'source':str(path),'source_sha256':before,'output':str(destination),'output_sha256':digest(destination),
            'changes':events,'operation_counts':dict(Counter(e['operation'] for e in events)),
            'cleared_fields':dict(Counter(e['field'] for e in events if e['operation']=='clear_inapplicable_text')),
            'conflicts':conflicts,'verified':'Only listed text cells and worksheet dimensions changed; all numeric values, identifiers, formulas, caches and other package contents preserved.'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--retrospective',type=Path,required=True)
    parser.add_argument('--circall',type=Path,required=True)
    parser.add_argument('--rules',type=Path,default=ROOT/'configs/definitions/data_integrity.json')
    parser.add_argument('--output-dir',type=Path,required=True)
    args=parser.parse_args()
    if args.output_dir.exists():parser.error('Output directory must be fresh')
    config=json.loads(args.rules.read_text())
    dependent=config['extraction_dependent_fields']
    selections=[(args.retrospective,['Inventaire']),(args.circall,['cohorte_lal','cohorte_control','template'])]
    for source,sheets in selections:plan_changes(source,sheets,dependent)
    args.output_dir.mkdir(parents=True)
    record={'started_utc':datetime.now(timezone.utc).isoformat(),'code_sha256':digest(Path(__file__)),
            'command':[sys.executable,*sys.argv],
            'rules_path':str(args.rules),'rules_sha256':digest(args.rules),'workbooks':[]}
    for source,sheets in selections:
        result=normalize(source,args.output_dir/(source.stem+'_status_corrected.xlsx'),sheets,dependent)
        record['workbooks'].append(result)
        print(json.dumps({'file':source.name,'operations':result['operation_counts'],'cleared_fields':result['cleared_fields'],'numeric_conflicts_preserved':len(result['conflicts'])}))
    record['finished_utc']=datetime.now(timezone.utc).isoformat()
    with (args.output_dir/'correction_report.json').open('x') as f:json.dump(record,f,indent=2);f.write('\n')


if __name__=='__main__':main()
