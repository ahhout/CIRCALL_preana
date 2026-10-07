"""Explicit retrospective donor source; legacy endpoint mapping, no patient pooling."""
from copy import deepcopy
from pathlib import Path

from analysis.sample_io import read_sheet

SHEET='Feuil1'
ENDPOINT='Conc ng/mL  plasma'
NUMERIC={'Conc ng/mL  plasma':'ng/mL plasma','Conc ng':'ng','Conc ng / ul':'ng/µL',
         'Conc pg':'pg','Conc pg /ul':'pg/µL','% cfDNA':'recorded percentage (scale unconfirmed)'}


def inspect_with_controls(path,cohort,include_controls,rules,donors=None):
    from analysis.data_integrity.checks import inspect_cohort, group_findings, summarize
    result=inspect_cohort(path,cohort,include_controls,rules)
    if cohort!='retrospective' or not include_controls or donors is None:return result
    configured=deepcopy(rules)
    configured.update(required=['Donor',ENDPOINT],patient_required=[],identifier_fields=['Donor'],calculations=[],extraction_dependent_fields=[],
                      fields={name:{'type':'number','unit':unit,'description':'Recorded donor workbook field; no inferred protocol metadata','minimum':0} for name,unit in NUMERIC.items()})
    control=inspect_cohort(donors,'retrospective',True,configured,sheets_override=[SHEET])
    control['coverage'].append({'sheet':SHEET,'field':'(donor calculations)','check':'arithmetic','assessed':0,'unavailable':4,
                               'reason':'Fixed-volume conversion formulas lack independent extraction-volume metadata; only reference/cache checks performed'})
    control['coverage'].append({'sheet':SHEET,'field':'(clinical metadata)','check':'semantic_validation','assessed':0,'unavailable':1,
                               'reason':'Visit, center, specimen volume, extraction status and fraction interpretation unavailable; not inferred'})
    for key in ('findings','coverage','sheets'):result[key].extend(control[key])
    result['groups']=group_findings(result['findings']);result['summary']=summarize(result['findings'])
    result['additional_sources']=[{'source':str(Path(donors).resolve()),'sheet':SHEET,'population':'retrospective controls'}]
    return result


def observations(path,d):
    from analysis.sample_statistics.core import measurement, token
    sheet=read_sheet(path,SHEET)
    headers=[str(c.value).strip() if c.value is not None else '' for c in sheet.headers]
    if any(headers.count(f)!=1 for f in ('Donor',ENDPOINT)):raise ValueError('Donor headers unavailable or duplicated')
    result=[];issues=[]
    for row in sheet.rows:
        cells={h:c for h,c in zip(headers,row) if h}
        identity=cells['Donor'].value
        if token(identity) in d['missing_tokens']+d['unknown_tokens']:
            issues.append({'sheet':SHEET,'row':row[0].row,'field':'Donor','reason':'control_identity_unavailable'})
            continue
        metrics={f:{'value':None,'state':'field_unavailable'} for f in d['metrics']}
        metrics['dna_ng_per_ml_plasma']=measurement(cells[ENDPOINT],'unclassified',d)
        result.append(dict(cohort='retrospective',sheet=SHEET,row=row[0].row,patient_id='',
                           subject_key='retrospective:donor:'+str(identity).strip(),center='unknown',visit='control',
                           specimen='plasma',assay='not_recorded',control=True,extraction_status='unclassified',
                           receipt='received',receipt_basis='control_inventory',receipt_reason='control_record_with_supplied_endpoint',
                           id_state='not_recorded',measurements=metrics))
    return result,issues
