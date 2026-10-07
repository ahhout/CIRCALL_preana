"""Repair approved CIRCALL formulas without recalculating or altering measurements."""
import argparse
from html import escape
from pathlib import Path
import posixpath
import re
import shutil
import tempfile
from xml.etree import ElementTree as ET
from zipfile import ZipFile

from analysis.provenance import ROOT, digest, envelope, utc_now, write_json
from analysis.sample_io import read_sheet
from analysis.workbook_cleanup import NS, REL
from analysis.extraction_status import CELL, cell_xml


def plan(source, sheets=None):
    from analysis.data_integrity.checks import inspect_cohort, load_rules
    from analysis.provenance import ROOT
    findings=inspect_cohort(source,'circall',True,load_rules(ROOT/'configs/definitions/data_integrity.json'))
    error_rows={(f['sheet'],int(re.search(r'\d+$',f['cell'])[0])) for f in findings['findings'] if f['severity']=='error' and f.get('cell')}
    changes={}
    selected = sheets if sheets is not None else ('cohorte_lal','cohorte_control')
    if not selected or len(set(selected))!=len(selected) or any(name not in ('cohorte_lal','cohorte_control','template') for name in selected):
        raise ValueError('Select distinct supported CIRCALL sheets')
    for name in selected:
        s=read_sheet(source,name);headers=[c.value for c in s.headers]
        if len([h for h in headers if h])!=len(set(h for h in headers if h)):
            raise ValueError('Duplicate headers')
        edits={}
        for row in s.rows:
            if sheets is None and (name,row[0].row) not in error_rows:continue
            r={h:c for h,c in zip(headers,row) if h}
            def ref(f):return r[f].coordinate
            for field,a,b in [('dna_total_ng','dna_concentration_ng_per_ul','elution_volume_ul'),
                              ('dna_ng_per_ml_plasma','dna_total_ng','extraction_input_volume_ml'),
                              ('cfdna_concentration_ng_per_ul','cfdna_fraction','dna_concentration_ng_per_ul'),
                              ('cfdna_total_ng','cfdna_fraction','dna_total_ng'),
                              ('cfdna_ng_per_ml_plasma','cfdna_fraction','dna_ng_per_ml_plasma')]:
                cell=r[field]
                if cell.formula is None:continue  # Recorded numbers are never overwritten.
                x,y=ref(a),ref(b)
                if field=='dna_ng_per_ml_plasma':
                    formula=f'=IF(AND({ref("specimen_type")}="plasma",ISNUMBER({x}),ISNUMBER({y}),{y}>0),{x}/{y},"")'
                elif sheets is not None and field=='cfdna_ng_per_ml_plasma':
                    formula=f'=IF(AND({ref("specimen_type")}="plasma",ISNUMBER({x}),ISNUMBER({y})),{x}*{y},"")'
                else:formula=f'=IF(AND(ISNUMBER({x}),ISNUMBER({y})),{x}*{y},"")'
                if cell.formula!=formula:
                    edits[cell.coordinate]={'field':field,'formula':formula,'reason':'approved_guarded_calculation','old_formula':cell.formula}
            if name=='cohorte_lal' and row[0].row==199 and r['cfdna_fraction'].formula=='=AK199/AE199':
                cell=r['cfdna_fraction']
                edits[cell.coordinate]={'field':'cfdna_fraction','formula':None,'reason':'remove_invalid_identifier_division_no_measurement_available','old_formula':cell.formula}
            if sheets is not None and name=='template':
                for field in ('sampling_plan','day'):
                    cell=r.get(field)
                    if cell is None or cell.formula is None:continue
                    # Retain the recorded reference/offset; guard numeric Excel dates.
                    # Unsupported expressions require review, not guessed timing rules.
                    expr=cell.formula[1:]
                    if 'ISNUMBER(' in expr.upper():continue
                    if field=='sampling_plan':
                        match=re.fullmatch(r'(\$?[A-Z]+\$?\d+)(?:\+\d+)?',expr)
                        if match is None:raise ValueError('Unsupported planned-date formula')
                        formula=f'=IF(ISNUMBER({match[1]}),{expr},"")'
                    else:
                        match=re.fullmatch(r'(\$?[A-Z]+\$?\d+)-(\$?[A-Z]+\$?\d+)\+1',expr)
                        if match is None:raise ValueError('Unsupported treatment-day formula')
                        formula=f'=IF(AND(ISNUMBER({match[1]}),ISNUMBER({match[2]})),{expr},"")'
                    edits[cell.coordinate]={'field':field,'formula':formula,'reason':'guard_recorded_date_calculation_preserve_offset','old_formula':cell.formula}
        changes[name]=edits
    return changes


def calculation_metadata(archive):
    """Discard the dependency cache after formula edits; Excel rebuilds it."""
    parts = {}
    for name, pattern in (
        ('xl/_rels/workbook.xml.rels', rb'<Relationship\b(?=[^>]*\bType="[^"]*/calcChain")[^>]*/>'),
        ('[Content_Types].xml', rb'<Override\b(?=[^>]*\bPartName="/xl/calcChain.xml")[^>]*/>'),
    ):
        parts[name] = re.sub(pattern, b'', archive.read(name))
    def recalc(match):
        raw = match[0]
        for key in (b'fullCalcOnLoad', b'forceFullCalc'):
            raw = re.sub(rb'\s+'+key+rb'="[^"]*"', b'', raw)
        return raw[:-2]+b' fullCalcOnLoad="1" forceFullCalc="1"/>'
    data, count = re.subn(rb'<calcPr\b[^>]*/>', recalc, archive.read('xl/workbook.xml'))
    if count != 1:
        raise ValueError('Unsupported workbook calculation settings')
    parts['xl/workbook.xml'] = data
    for data in parts.values():
        ET.fromstring(data)
    return parts


def run(source,destination,adopt=False,*,sheets=None):
    source=Path(source).resolve();destination=Path(destination).absolute()
    lock=source.with_name('~$'+source.name)
    if lock.exists():raise ValueError('Save and close Excel first')
    if destination.exists() or any(p.is_symlink() for p in (destination,*destination.parents)):raise ValueError('Fresh destination required')
    before=digest(source);changes=plan(source,sheets)
    provenance=envelope('inventory_formula_repair',{'sheets':list(changes),'adopt':adopt},
                        {'circall':source,'rules':ROOT/'configs/definitions/data_integrity.json'},
                        [Path(__file__),ROOT/'analysis/sample_io.py',ROOT/'analysis/extraction_status.py',
                         ROOT/'analysis/data_integrity/checks.py',ROOT/'analysis/sample_definitions.py',
                         ROOT/'analysis/workbook_cleanup.py',ROOT/'analysis/provenance.py'],
                        ROOT/'environments/conda-linux-64.lock')
    original_sheets={name:read_sheet(source,name) for name in changes}
    materialized={}
    destination.mkdir(parents=True);backup=destination/'original.xlsx';shutil.copyfile(source,backup)
    if digest(backup)!=before:raise ValueError('Backup mismatch')
    output=destination/source.name;reverse={};patched={}
    with ZipFile(source) as zin:
        targets={r.attrib['Id']:r.attrib['Target'] for r in ET.fromstring(zin.read('xl/_rels/workbook.xml.rels'))}
        for sheet in ET.fromstring(zin.read('xl/workbook.xml')).find('m:sheets',NS):
            name=sheet.attrib['name'];wanted=changes.get(name,{})
            if not wanted:continue
            target=targets[sheet.attrib[REL]];member=target.lstrip('/') if target.startswith('/') else posixpath.normpath('xl/'+target)
            original=zin.read(member);old={}
            xml=ET.fromstring(original)
            formula_cells={c.attrib['r']:c.find('m:f',NS) for c in xml.findall('.//m:c',NS) if c.find('m:f',NS) is not None}
            touched_shared={f.attrib['si'] for coord,f in formula_cells.items() if coord in wanted and f.attrib.get('t')=='shared'}
            expanded={c.coordinate:c.formula for row in original_sheets[name].rows for c in row if c.formula}
            extra={coord:expanded[coord] for coord,f in formula_cells.items() if f.attrib.get('t')=='shared' and f.attrib.get('si') in touched_shared and coord not in wanted}
            materialized[name]=list(extra)

            def replace(match):
                coord=match[1].decode()
                if coord not in wanted and coord not in extra:return match[0]
                element=ET.fromstring(match[0]);formula=element.find('f')
                if formula is None or formula.attrib.get('t') not in (None,'shared'):raise ValueError('Unsupported formula encoding')
                old[coord]=match[0]
                if coord in extra:
                    return re.sub(rb'<f\b[^>]*(?:/>|>.*?</f>)',b'<f>'+escape(extra[coord][1:],quote=False).encode()+b'</f>',match[0],count=1,flags=re.S)
                new=wanted[coord]['formula']
                if new is None:return cell_xml(coord,None,match[0])
                opening=match[0][:match[0].index(b'>')+1]
                opening=re.sub(rb'\s+t="[^"]*"',b'',opening)
                # No invented caches: Excel must recalculate these formulas.
                return opening+b'<f>'+escape(new[1:],quote=False).encode()+b'</f></c>'
            data=CELL.sub(replace,original)
            if set(old)!=set(wanted)|set(extra):raise ValueError('Missing target formula')
            if CELL.sub(lambda m:old.get(m[1].decode(),m[0]),data)!=original:raise ValueError('Unexpected worksheet change')
            ET.fromstring(data);patched[member]=data;reverse[member]=old
        metadata=calculation_metadata(zin)
        with output.open('xb') as stream,ZipFile(stream,'w') as zout:
            zout.comment=zin.comment
            for info in zin.infolist():
                if info.filename!='xl/calcChain.xml':
                    zout.writestr(info,metadata.get(info.filename,patched.get(info.filename,zin.read(info.filename))))
    with ZipFile(source) as a,ZipFile(output) as b:
        if [n for n in a.namelist() if n!='xl/calcChain.xml']!=b.namelist() or b.testzip() is not None:raise ValueError('Invalid archive')
        for member in a.namelist():
            if member=='xl/calcChain.xml':continue
            if member in metadata:
                if b.read(member)!=metadata[member]:raise ValueError('Calculation metadata mismatch')
                continue
            data=b.read(member)
            if member in reverse:data=CELL.sub(lambda m:reverse[member].get(m[1].decode(),m[0]),data)
            if data!=a.read(member):raise ValueError('Other workbook content changed')
    for sheet,edits in changes.items():
        reread=read_sheet(output,sheet);cells={c.coordinate:c for row in reread.rows for c in row}
        original_cells={c.coordinate:c for row in original_sheets[sheet].rows for c in row}
        if any(cells.get(coord)!=cell for coord,cell in original_cells.items() if coord not in edits):raise ValueError('Unchanged source cells differ')
        for coord,edit in edits.items():
            if cells[coord].formula!=edit['formula'] or cells[coord].value is not None:raise ValueError('Formula verification failed')
    report={**provenance,'source':str(source),'backup':str(backup),'output':str(output),
            'source_sha256':before,'updated_sha256':digest(output),'changes':changes,
            'recalculation_required':True,'adopted':False,'shared_formula_materialized_preserving_values':materialized}
    write_json(destination/'formula_correction_report.json',report)
    if digest(source)!=before or lock.exists():raise ValueError('Source changed or reopened')
    if adopt:
        with tempfile.NamedTemporaryFile(dir=source.parent,prefix='.formula_repair_',suffix='.xlsx',delete=False) as tmp:staged=Path(tmp.name)
        try:
            shutil.copyfile(output,staged)
            if digest(staged)!=report['updated_sha256'] or digest(source)!=before or lock.exists():raise ValueError('Source changed before adoption')
            staged.replace(source)
        finally:staged.unlink(missing_ok=True)
        report['adopted']=True;write_json(destination/'formula_correction_report.json',report)
    report.update(status='complete',finished_utc=utc_now())
    write_json(destination/'formula_correction_report.json',report)
    return report


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__,allow_abbrev=False)
    p.add_argument('--circall',type=Path,required=True);p.add_argument('--output-dir',type=Path,required=True);p.add_argument('--adopt',action='store_true')
    p.add_argument('--sheets',nargs='+',choices=['cohorte_lal','cohorte_control','template'],
                   help='Repair all existing calculation formulas on only these sheets; omission retains defect-row repair')
    a=p.parse_args(argv)
    try:
        r=run(a.circall,a.output_dir,a.adopt,sheets=a.sheets)
        print({k:len(v) for k,v in r['changes'].items()});print('Excel recalculation required; no numeric measurements changed')
        return 0
    except Exception as error:
        print(f'Formula repair unavailable ({type(error).__name__}); verify source and destination')
        return 1


if __name__=='__main__':raise SystemExit(main())
