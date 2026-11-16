"""Fill retrospective patient_id gaps using the investigator's exact identity tuples.

Only blank/na cells are changed. Existing IDs are preserved. This does not remove
names or alter inclusion/sample/DNA identifiers. Save and close Excel before use.
"""
import argparse
from collections import defaultdict
from datetime import date, datetime
import json
from pathlib import Path
import posixpath
import re
import shutil
import sys
import tempfile
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from openpyxl.utils.cell import coordinate_to_tuple

from analysis.provenance import digest, write_json
from analysis.sample_io import read_sheet
from analysis.maintenance.xlsx_patch import CELL, ROW, cell_xml
from analysis.maintenance.workbook_cleanup import NS, REL


def missing(value):
    return value is None or isinstance(value,str) and value.strip().casefold() in ('','na')


def plan(path):
    sheet=read_sheet(path,'Inventaire')
    headers=[c.value for c in sheet.headers]
    id_header = 'patient_id' if 'patient_id' in headers else 'inclusion_id'
    fields=(id_header,'lastname','firstname','dob')
    if any(headers.count(f)!=1 for f in fields):
        raise ValueError('Require unique patient_id, lastname, firstname and dob headers; save the renamed workbook first')
    groups=defaultdict(list);numbers=[];issues=[];edits={}
    for row in sheet.rows:
        cells={h:c for h,c in zip(headers,row) if h}
        cells['patient_id']=cells[id_header]
        if not any(cells[f].value is not None for f in fields):continue
        values=tuple(cells[f].value for f in fields[1:])
        # Only actual Excel dates lose their time-of-day; text dates are not guessed.
        key=values[:2]+((values[2].date() if isinstance(values[2],datetime) else values[2]),)
        groups[key].append(cells)
        identifier=cells['patient_id'].value
        if not missing(identifier):
            match=re.fullmatch(r'unk-(\d+)-[^-]+-[^-]+',str(identifier),re.I)
            if match:numbers.append(int(match[1]))
    next_number=max(numbers,default=0)+1
    new_patients=reused_cells=0
    owners=defaultdict(set)
    for key,rows in groups.items():
        for cells in rows:
            value=cells['patient_id'].value
            if not missing(value):owners[str(value)].add(key)
    for key,rows in groups.items():
        targets=[cells for cells in rows if missing(cells['patient_id'].value)]
        existing={str(c['patient_id'].value) for c in rows if not missing(c['patient_id'].value)}
        reason=None
        if any(c['patient_id'].formula for c in rows):reason='formula_patient_id_requires_review'
        elif len(existing)>1:reason='multiple_existing_ids_for_identity'
        elif any(len(owners[value])>1 for value in existing):reason='existing_id_shared_by_different_identity_tuples'
        elif any(missing(v) or v=='?' for v in key) or not isinstance(key[2],date):reason='incomplete_or_uninterpreted_identity'
        if reason:
            issues.append({'reason':reason,'cells':[c['patient_id'].coordinate for c in rows],'unfilled_cells':len(targets)})
            continue
        if not targets:continue
        if existing:
            value=next(iter(existing));reused_cells+=len(targets)
        else:
            initials=[]
            for name in key[:2]:
                letter=next((ch for ch in str(name) if ch.isalpha()),None)
                if letter is None:break
                initials.append(letter.upper())
            if len(initials)!=2:
                issues.append({'reason':'name_initial_unavailable','cells':[c['patient_id'].coordinate for c in targets],'unfilled_cells':len(targets)})
                continue
            value=f'unk-{next_number:03d}-{initials[0]}-{initials[1]}'
            next_number+=1;new_patients+=1
        for cells in targets:edits[cells['patient_id'].coordinate]=value
    filled_count=len(edits)
    if id_header=='inclusion_id':
        edits[sheet.headers[headers.index(id_header)].coordinate]='patient_id'
    return sheet,edits,dict(renamed_header=id_header=='inclusion_id',new_patient_ids=new_patients,reused_existing_id_cells=reused_cells,
                           filled_cells=filled_count,next_unused_number=next_number,
                           review_groups=issues,unfilled_cells=sum(i['unfilled_cells'] for i in issues))


def patch_workbook(source,destination,edits):
    with ZipFile(source) as zin:
        rels={e.attrib['Id']:e.attrib['Target'] for e in ET.fromstring(zin.read('xl/_rels/workbook.xml.rels'))}
        sheet=next(s for s in ET.fromstring(zin.read('xl/workbook.xml')).find('m:sheets',NS) if s.attrib['name']=='Inventaire')
        target=rels[sheet.attrib[REL]]
        member=target.lstrip('/') if target.startswith('/') else posixpath.normpath('xl/'+target)
        original=zin.read(member);seen=set();reverse={}
        def row_replace(match):
            number=int(match[2]);body=match[3]
            def cell_replace(cell):
                coord=cell[1].decode()
                if coord not in edits:return cell[0]
                if b'<f' in cell[0]:raise ValueError('Refusing to overwrite a formula')
                seen.add(coord);reverse[coord]=cell[0]
                return cell_xml(coord,edits[coord],cell[0])
            body=CELL.sub(cell_replace,body)
            for coord,value in edits.items():
                if coordinate_to_tuple(coord)[0]!=number or coord in seen:continue
                insertion=cell_xml(coord,value);col=coordinate_to_tuple(coord)[1]
                following=next((c for c in CELL.finditer(body) if coordinate_to_tuple(c[1].decode())[1]>col),None)
                where=following.start() if following else len(body)
                body=body[:where]+insertion+body[where:]
                seen.add(coord);reverse[coord]=b''
            return match[1]+body+match[4]
        changed=ROW.sub(row_replace,original)
        if seen!=set(edits):raise ValueError('Could not locate every target row')
        ET.fromstring(changed)
        if CELL.sub(lambda m:reverse.get(m[1].decode(),m[0]),changed)!=original:
            raise ValueError('Unexpected worksheet change')
        with destination.open('xb') as stream,ZipFile(stream,'w') as zout:
            zout.comment=zin.comment
            for info in zin.infolist():zout.writestr(info,changed if info.filename==member else zin.read(info.filename))
    with ZipFile(source) as a,ZipFile(destination) as b:
        if a.namelist()!=b.namelist() or b.testzip() is not None:raise ValueError('Invalid output archive')
        for name in a.namelist():
            value=b.read(name)
            if name==member:value=CELL.sub(lambda m:reverse.get(m[1].decode(),m[0]),value)
            if value!=a.read(name):raise ValueError('Unexpected package change')


def run(source,destination,adopt=False):
    source=Path(source).resolve();destination=Path(destination).absolute()
    if source.with_name('~$'+source.name).exists():
        raise ValueError('Save and close the workbook first; Excel lock file is present')
    if destination.exists() or any(p.is_symlink() for p in (destination,*destination.parents)):
        raise ValueError('Choose a fresh output directory')
    before=digest(source);sheet,edits,report=plan(source)
    destination.mkdir(parents=True)
    backup=destination/'original.xlsx';shutil.copyfile(source,backup)
    if digest(backup)!=before:raise ValueError('Source changed while backing up')
    updated=destination/source.name
    patch_workbook(source,updated,edits)
    following=read_sheet(updated,'Inventaire')
    old={c.coordinate:c for r in [sheet.headers,*sheet.rows] for c in r}
    new={c.coordinate:c for r in [following.headers,*following.rows] for c in r}
    for coordinate,cell in old.items():
        if coordinate not in edits and cell!=new.get(coordinate):raise ValueError('Non-ID cell changed')
    if any(new[c].value!=v or new[c].data_type!='s' for c,v in edits.items()):raise ValueError('ID verification failed')
    if digest(source)!=before:raise ValueError('Source changed during preparation')
    report.update(source_sha256=before,updated_sha256=digest(updated),changed_cells=sorted(edits,key=coordinate_to_tuple),
                  identity_rule='Exact stored lastname, firstname, and actual Excel DOB date; no spelling/case normalization',
                  adopted=False)
    write_json(destination/'patient_id_report.json',report)
    if adopt:
        if source.with_name('~$'+source.name).exists() or digest(source)!=before:
            raise ValueError('Source reopened or changed; prepared copy retained without adoption')
        with tempfile.NamedTemporaryFile(dir=source.parent,prefix='.patient_ids_',suffix='.xlsx',delete=False) as temp:
            staged=Path(temp.name)
        try:
            shutil.copyfile(updated,staged)
            if digest(staged)!=report['updated_sha256']:raise ValueError('Adoption checksum mismatch')
            if digest(source)!=before:raise ValueError('Source changed before adoption')
            staged.replace(source)
        finally:staged.unlink(missing_ok=True)
        report['adopted']=True;write_json(destination/'patient_id_report.json',report)
    return report


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    p.add_argument('--inventory',type=Path,required=True)
    p.add_argument('--output-dir',type=Path,required=True)
    p.add_argument('--adopt',action='store_true',help='Back up and update the selected input after verification')
    a=p.parse_args(argv)
    try:
        result=run(a.inventory,a.output_dir,a.adopt)
        print(json.dumps({k:result[k] for k in ('new_patient_ids','reused_existing_id_cells','filled_cells','unfilled_cells','adopted')}))
        return 1 if result['unfilled_cells'] else 0
    except Exception as error:
        print(f'Patient ID update unavailable ({type(error).__name__}); check saved headers, workbook lock and destination',file=sys.stderr)
        return 1


if __name__=='__main__':raise SystemExit(main())
