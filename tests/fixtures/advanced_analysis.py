"""Synthetic Layer 3 workbook builders."""

from datetime import time
from types import SimpleNamespace
import json
from openpyxl import Workbook
from analysis.provenance import ROOT
from analysis.advanced_analysis import preparation as prep
D = prep.load_definitions(ROOT/"configs/definitions/advanced_analysis.json")

def row(pid='P1', outcome=10, **changes):
    result = dict(patient_id=pid, circall_id=pid if pid.startswith('001-') else '001-9999-X-Z', sample_id='PRIVATE_SAMPLE_'+pid,
                  timepoint='diag', specimen_type='plasma', tube='Roche', nucleic_acid='cfDNA',
                  cfdna_ng_per_ml_plasma=outcome, sex='F', age_diag=10, genetic_subtype='Subtype A',
                  cytology=.2, **{'cytospin_%': .3, 'diag_blood_wbc_max_x10*9/L':3,
                  'diag_blood_blast_pct':.2, 'diag_bm_blast_pct':.7})
    result.update(changes)
    return result


def fixture(path, cohort='retrospective', rows=None, *, controls=False, bad_controls=False, drop=(), duplicate=None):
    rules = json.loads((ROOT/'configs/definitions/data_integrity.json').read_text())
    headers = list(dict.fromkeys([*rules['required'], *row().keys(),
                                 *[key for record in rows or [] for key in record],
                                 'lastname', 'firstname', 'dob', 'private_note']))
    headers = [h for h in headers if h not in drop]
    if duplicate:
        headers.append(duplicate)
    book = Workbook()
    book.remove(book.active)
    names = ['Inventaire'] if cohort == 'retrospective' else ['cohorte_lal']+(['cohorte_control'] if controls else [])
    for name in names:
        sheet = book.create_sheet(name)
        sheet.append(headers)
        selected = [row('001-8888-X-Z', 999)] if name == 'cohorte_control' else rows or [row()]
        for record in selected:
            r = record.copy()
            r.update(lastname='PRIVATE_NAME_SENTINEL', firstname='PRIVATE_FIRST_SENTINEL', dob='PRIVATE_DOB_SENTINEL', private_note='PRIVATE_NOTE_SENTINEL')
            if bad_controls and name == 'cohorte_control':
                r['extraction_input_volume_ml'] = -1
            sheet.append([r.get(h) for h in headers])
    book.save(path)
    book.close()


def sources(tmp_path, **kwargs):
    retro = tmp_path/'retrospective.xlsx'
    circ = tmp_path/'circall.xlsx'
    data = [row(f'001-{i:04}-X-Z', 5+i**2, cytology=i/20,
                **{'diag_blood_blast_pct':i/20, 'diag_bm_blast_pct':.5+i/20, 'diag_blood_wbc_max_x10*9/L':i+1}) for i in range(1, 6)]
    fixture(retro, rows=[*data, row('001-0001-X-Z', 40, cytology=.7, sample_id='PRIVATE_REPEAT_SENTINEL')])
    fixture(circ, 'circall', data, controls=True, **kwargs)
    donor = tmp_path/'donors.xlsx'
    b = Workbook()
    w = b.active
    w.title = 'Feuil1'
    w.append(['Donor', 'Conc ng/mL  plasma'])
    w.append(['PRIVATE_DONOR_SENTINEL', 25])
    b.save(donor)
    b.close()
    return retro, circ, donor



def settings():
    return SimpleNamespace(predictors=['requested'], spearman_sensitivity=True,
                           retrospective_wbc_unit='x10^9/L')


def sample(i):
    return row(f'001-{i:04d}-X-Z', outcome=3+i**2, dna_total_ng=10+i**2,
               dna_ng_per_ml_plasma=5+i**2, cfdna_total_ng=4+i**2, cfdna_fraction=.1+i/100,
               sampling_time=time(11, 59, 59) if i % 2 else time(12),
               corticoide_pre_tt='yes' if i % 3 else 'no', genetic_subtype='A' if i % 2 else 'B',
               elution_volume_ul=40+10*(i % 3), extraction_input_volume_ml=1+i/10,
               dna_concentration_ng_per_ul=1+i/5, cytology=i/20,
               Hb_g_per_dL=8+i/10, platelets_10e9_per_L=100+i,
               diag_blood_blast_pct=i/20, diag_bm_blast_pct=.5+i/25)


