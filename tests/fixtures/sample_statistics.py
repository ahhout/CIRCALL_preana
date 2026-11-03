"""Synthetic receipt and measurement sources."""
from datetime import datetime
from openpyxl import Workbook
from analysis.provenance import ROOT
from analysis.sample_statistics import core
D = core.load_definitions(ROOT/"configs/definitions/sample_statistics.json")
ASOF = "2026-10-05T12:00:00+02:00"

def fixture(path,cohort='circall',controls=True,bad=False,names=False):
    from analysis.data_integrity.checks import load_rules
    rules=load_rules(ROOT/'configs/definitions/data_integrity.json')
    headers=list(dict.fromkeys(rules['required']+['timepoint','sampling_plan','extraction_status','dna_id','patient_id','circall_id','nucleic_acid','row']))
    if names:
        headers.remove('patient_id');headers+=['anonymization','lastname','firstname','dob','private_note']
    book=Workbook();book.remove(book.active)
    sheets=['Inventaire'] if cohort=='retrospective' else ['cohorte_lal']+(['cohorte_control'] if controls else [])
    for name in sheets:
        ws=book.create_sheet(name);ws.append(headers)
        records=[dict(sample_id='SYNTHETIC-SAMPLE',specimen_type='plasma',timepoint='diag',patient_id='RETRO-0001',circall_id='001-9999-X-Z',
                      dna_id='SYNTHETIC-DNA',nucleic_acid='cfDNA',sampling_plan=datetime(2026,10,1),dna_concentration_ng_per_ul=2,
                      elution_volume_ul=50,dna_total_ng=100,dna_ng_per_ml_plasma=50,extraction_input_volume_ml=2,
                      cfdna_fraction=.5,cfdna_concentration_ng_per_ul=1,cfdna_total_ng=50,cfdna_ng_per_ml_plasma=25,cfdna_avg_size_bp=170)]
        if name!='cohorte_control':
            records.append(dict(sample_id='na',specimen_type='plasma',timepoint='tp1',patient_id='RETRO-0001',circall_id='001-9999-X-Z',sampling_plan=datetime(2026,9,1)))
        if bad:records[0]['dna_total_ng']=999
        for i,record in enumerate(records,2):
            if names:record.update(anonymization='PRIVATE-OLD',lastname='PRIVATE_SURNAME_SENTINEL',firstname='PRIVATE_FIRST_SENTINEL',dob=datetime(1990,1,1),private_note=None)
            ws.append([record.get(h) for h in headers])
        ws.cell(40,headers.index('row')+1,40)
        ws.cell(50,1).number_format='@'
    book.save(path);book.close()


def saved_result():
    summary = dict(view='overall', samples=10, patients=3, received_samples=7, received_patients=3)
    receipt = [dict(view='overall', basis='deadline', status=status, samples=count, patients=3,
                    overdue_samples=2 if status == 'marked_missing' else 0,
                    classified_samples=classified, classified_denominator=7,
                    classified_percentage=classified / 7 if classified else None)
               for status, count, classified in [('received', 5, 5), ('marked_missing', 2, 2), ('unassessed', 1, 0)]]
    receipt.append(dict(view='overall', basis='manual', status='received', samples=2, patients=1,
                        overdue_samples=0, classified_samples=None, classified_denominator=None,
                        classified_percentage=None))
    measurement = dict(view='visit', field='dna_total_ng', unit='ng', specimen='plasma', assay='plasma DNA',
                       visit='diag', received_samples=7, available_patients=3, unavailable_samples=2,
                       n=5, mean=4., sd=1.5811388300841898, median=4., q1=3., q3=5., minimum=2., maximum=6., total=20.)
    return dict(scope='circall', status='complete', include_controls=True, blocking=[],
                metadata=dict(cohort='circall', assessment_time='2026-10-07T12:00:00+00:00'),
                tables=dict(summary=[summary], receipt=receipt, measurements=[measurement],
                            availability=[dict(view='overall', field='extraction_status', state='yes', count=6),
                                          dict(view='overall', field='extraction_status', state='no', count=4)],
                            missed=[dict(patient_id='=SYNTHETIC_PSEUDONYM', center='RDB', visit='diag',
                                         specimen='plasma', sheet='synthetic', row=2, receipt_reason='deadline_elapsed', status='marked_missing')],
                            audit_detail={'summary': [dict(summary,view='center',center='RDB'),dict(summary,view='center',center='TRS',samples=0,patients=0,received_samples=0,received_patients=0)],
                                          'receipt': [dict(r,view='center',center='RDB') for r in receipt],
                                          'availability': [dict(view='center',center='RDB',field='extraction_status',state='yes',count=6),
                                                           dict(view='center',center='RDB',field='extraction_status',state='no',count=4)]}),
                controls=dict(summary=[dict(summary, samples=2, patients=2, received_samples=2)],
                              measurements=[dict(measurement, n=2)], receipt=[], availability=[]))


