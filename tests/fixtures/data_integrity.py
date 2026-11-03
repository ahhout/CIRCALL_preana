"""Synthetic workbook cells and explicit formula caches."""
import re
from zipfile import ZipFile
from openpyxl import Workbook
from analysis.provenance import ROOT
from analysis.data_integrity.checks import load_rules

def fixture(path, overrides=None, sheets=('Inventaire',), caches=None):
    rules=load_rules(ROOT/'configs/definitions/data_integrity.json')
    headers=rules['required']+['timepoint','dna_id','extraction_date','unknown_extra','extraction_status']
    good={'sample_id':'SYNTHETIC-1','specimen_type':'plasma','extraction_input_volume_ml':2,
          'elution_volume_ul':50,'dna_concentration_ng_per_ul':2,'dna_total_ng':100,
          'dna_ng_per_ml_plasma':50,'cfdna_fraction':.5,'cfdna_concentration_ng_per_ul':1,
          'cfdna_total_ng':50,'cfdna_ng_per_ml_plasma':25,'cfdna_avg_size_bp':170,
          'timepoint':'diag','dna_id':'SYNTHETIC-DNA','unknown_extra':'PRIVATE_SENTINEL'}
    wb=Workbook();wb.remove(wb.active)
    for name in sheets:
        ws=wb.create_sheet(name);ws.append(headers)
        for changes in overrides or [{}]:
            data={**good,**changes};ws.append([data.get(h) for h in headers])
        ws.cell(50,1).number_format='@'  # formatting only, never a sample
    if caches is None:
        wb.save(path)
    else:
        from io import BytesIO
        data=BytesIO();wb.save(data)
        with ZipFile(data) as zin,ZipFile(path,'w') as zout:
            for item in zin.infolist():
                raw=zin.read(item.filename)
                if item.filename=='xl/worksheets/sheet1.xml':
                    for coordinate,(kind,value) in caches.items():
                        pattern=rb'<c\b[^>]*\br="'+coordinate.encode()+rb'"[^>]*>.*?</c>'
                        def repl(m):
                            cell=m.group(0)
                            if kind=='str':cell=cell.replace(b'>',b' t="str">',1)
                            return re.sub(rb'<v\s*(?:/>|>.*?</v>)',b'<v>'+str(value).encode()+b'</v>',cell)
                        raw,n=re.subn(pattern,repl,raw,flags=re.S)
                        assert n==1
                zout.writestr(item,raw)
    return {h:__import__('openpyxl').utils.get_column_letter(i) for i,h in enumerate(headers,1)}


