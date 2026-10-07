"""Only explicitly synthetic clinical fixtures; no old workflow test helpers."""
import json
from pathlib import Path

from openpyxl import Workbook

from analysis.provenance import ROOT


def inventory(path, cohort, rows=None, *, controls=True, bad_control=False, drop=(), duplicate=None):
    rules = json.loads((ROOT/'configs/definitions/data_integrity.json').read_text())
    extra = ['patient_id', 'circall_id', 'timepoint', 'MRD_IgTCR', 'MRD_TP1', 'MRD_TP2', 'lastname', 'firstname', 'dob', 'source_note']
    headers = [h for h in dict.fromkeys(rules['required']+extra) if h not in drop]
    if duplicate:
        headers.append(duplicate)
    b = Workbook()
    b.remove(b.active)
    sheets = ['Inventaire'] if cohort == 'retrospective' else ['cohorte_lal']+(['cohorte_control'] if controls else [])
    defaults = [dict(patient_id='PATIENT-1', circall_id='001-9001-X-Z', sample_id='na', timepoint='tp1',
                     specimen_type='bone marrow', MRD_IgTCR=.001, MRD_TP1=.001, MRD_TP2='negative'),
                dict(patient_id='PATIENT-1', circall_id='001-9001-X-Z', sample_id=None, timepoint='tp2',
                     specimen_type='bone marrow', MRD_IgTCR='negative', MRD_TP1=.001, MRD_TP2='negative')]
    for name in sheets:
        w = b.create_sheet(name)
        w.append(headers)
        selected = [dict(circall_id='001-9999-X-Z', specimen_type='plasma', sample_id='PRIVATE_CONTROL_SAMPLE',
                         extraction_input_volume_ml=-1 if bad_control else None)] if name == 'cohorte_control' else defaults if rows is None else rows
        for r in selected:
            record = dict(lastname='PRIVATE_NAME_SENTINEL', firstname='PRIVATE_FIRST_SENTINEL', dob='PRIVATE_DOB_SENTINEL', source_note='PRIVATE_NOTE_SENTINEL')
            record.update(r)
            w.append([record.get(h) for h in headers])
    b.save(path)
    b.close()


def count_source(path, cohort, rows=None, *, duplicate=False, invalid=False):
    identity = 'lastname' if cohort == 'retrospective' else 'circall_id'
    b = Workbook()
    b.remove(b.active)
    for sheet, field in ({'blast':'blast_count_x10*9/L'} if cohort == 'retrospective' else {'blast':'blast_count_x10*9/L', 'wbc':'wbc_count_x10*9/L'}).items():
        w = b.create_sheet(sheet)
        headers = [identity, 'day', field, 'tt_d1_date', 'num_date', 'source_note']
        w.append(headers)
        identifier = 'PRIVATE_COUNT_NAME_SENTINEL' if cohort == 'retrospective' else '001-9001-X-Z'
        data = [(identifier, day, value) for day, value in [(-2, 9.), (1, 8.), (2, 0.), (8, 1.), (15, .5), (29, .1)]] if rows is None else rows
        if duplicate:
            data = [*data, data[1]]
        if invalid:
            data = [*data, (identifier, 30, -1)]
        for identifier, day, value in data:
            w.append([identifier, day, value, None, None, 'PRIVATE_NOTE_SENTINEL'])
    b.save(path)
    b.close()


def sources(root, *, bad_control=False):
    root = Path(root)
    paths = {name: root/(name+'.xlsx') for name in ('inventory', 'circall', 'blood_counts', 'retrospective_blasts', 'donors')}
    inventory(paths['inventory'], 'retrospective')
    inventory(paths['circall'], 'circall', bad_control=bad_control)
    count_source(paths['blood_counts'], 'circall')
    count_source(paths['retrospective_blasts'], 'retrospective')
    b = Workbook()
    w = b.active
    w.title = 'Feuil1'
    w.append(['Donor', 'Conc ng/mL  plasma'])
    w.append(['PRIVATE_DONOR_SENTINEL', 10])
    b.save(paths['donors'])
    b.close()
    return paths


def cli(paths, output=None):
    result = []
    for name, path in paths.items():
        result.extend(['--'+name.replace('_', '-'), str(path)])
    result += ['--blood-count-unit', 'x10^9/L', '--retrospective-blast-unit', 'x10^9/L']
    if output is not None:
        result += ['--output-dir', str(output)]
    return result
