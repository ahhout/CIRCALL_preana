"""Synthetic Layer 3 source contracts and intentionally revised preparation."""
import json

import numpy as np
from openpyxl import Workbook
import pytest

from analysis.advanced_analysis import preparation as prep
from analysis.provenance import ROOT
from analysis.sample_io import SourceCell

D = prep.load_definitions(ROOT/'configs/definitions/advanced_analysis.json')


def row(pid='P1', outcome=10, **changes):
    result = dict(patient_id=pid, circall_id=pid if pid.startswith('001-') else '001-9999-X-Z', sample_id='PRIVATE_SAMPLE_'+pid,
                  timepoint='diag', specimen_type='plasma', tube='Roche', nucleic_acid='cfDNA',
                  cfdna_ng_per_ml_plasma=outcome, sex='F', age_diag=10, genetic_subtype='Subtype A',
                  GB_per_L=3, cytology=.2, **{'cytospin_%': .3, 'diag_blood_wbc_x10*9/L':3,
                  'diag_blood_blast_pct':.2, 'diag_bm_blast_pct':.7})
    result.update(changes)
    return result


def fixture(path, cohort='retrospective', rows=None, *, controls=False, bad_controls=False, drop=(), duplicate=None):
    rules = json.loads((ROOT/'configs/definitions/data_integrity.json').read_text())
    headers = list(dict.fromkeys([*rules['required'], *row().keys(), 'lastname', 'firstname', 'dob', 'private_note']))
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


def test_patient_id_diagnosis_receipt_filters_and_matching(tmp_path):
    path = tmp_path/'retro.xlsx'
    fixture(path, rows=[row(outcome=0, sample_id='SAMPLE_A'), row(outcome=20, cytology=.4, age_diag=14, sample_id='SAMPLE_B'),
        row(outcome=999, timepoint='TP1'), row(outcome=999, tube='EDTA'), row(outcome=999, nucleic_acid='DNA'),
        row(outcome=999, sample_id='?'), row(outcome=None, specimen_type='bone marrow', cytology=None, **{'cytospin_%':.8}),
        row('P2', 0), row('P3', None)])
    frame, counts, evidence, issues = prep.prepare(path, 'retrospective', D)
    assert not issues
    assert len(frame) == 3
    p = frame.loc[frame.available_outcome_sample_n.eq(2)].iloc[0]
    assert (p.cfdna_ng_per_ml, p.peripheral_blast_percent, p.age_diag) in [(0, 20, 10), (20, 40, 14)]
    assert p.tumor_fraction_percent == pytest.approx(80)
    assert p.outcome_sample_n == 1
    assert counts['patients_with_nonpositive_outcome'] == 1 + int(p.cfdna_ng_per_ml == 0)
    assert counts['unselected_numeric_outcome_samples'] == 1
    assert counts['patients_with_missing_outcome'] == 1
    assert counts['outcome_zero'] == 2
    assert counts['excluded_outcome_missing_sample_id'] == 1
    assert counts['excluded_not_diagnosis'] == 1
    assert not any(marker in json.dumps(evidence) for marker in ('PRIVATE_', 'P1', 'P2'))
    assert all(len(r['subject_hash']) == 64 for r in evidence)


@pytest.mark.parametrize('sample', [None, '', 'na', 'NA', '?', 'sk', 'n/a'])
def test_receipt_missing_tokens(tmp_path, sample):
    path = tmp_path/'source.xlsx'
    fixture(path, rows=[row(sample_id=sample)])
    frame, counts, _, issues = prep.prepare(path, 'retrospective', D)
    assert frame.empty and not issues
    assert counts['excluded_outcome_missing_sample_id'] == 1


def test_circall_zero_selection_no_tube_filter_unavailable_age(tmp_path):
    path = tmp_path/'circall.xlsx'
    fixture(path, 'circall', [row('001-1234-X-Z', 0, tube='EDTA'), row('001-1234-X-Z', 20)])
    frame, _, _, issues = prep.prepare(path, 'circall', D)
    assert not issues and frame.cfdna_ng_per_ml.iat[0] in (0, 20)
    assert frame.outcome_sample_n.iat[0] == 1
    assert np.isnan(frame.age_diag.iat[0]) and np.isnan(frame.sex.iat[0])
    assert frame.peripheral_blast_percent.iat[0] == 20


def test_retrospective_discordance_and_circall_conflicts(tmp_path):
    path = tmp_path/'retro.xlsx'
    fixture(path, rows=[row(sex='F'), row(sex='M', genetic_subtype='Subtype B')])
    frame, counts, _, issues = prep.prepare(path, 'retrospective', D)
    assert not issues and frame.sex.iat[0] in ('F', 'M')
    assert counts['discordant_sex_patients'] == counts['discordant_genetic_subtype_patients'] == 1
    fixture(tmp_path/'circ.xlsx', 'circall', [row(), row(genetic_subtype='Subtype B')])
    assert prep.prepare(tmp_path/'circ.xlsx', 'circall', D)[3][0]['reason'] == 'conflicting_diagnosis_metadata'


@pytest.mark.parametrize('changes', [dict(cytology=20), dict(cytology='malformed'), dict(GB_per_L=-1), dict(age_diag='bad'), dict(cfdna_ng_per_ml_plasma=-1)])
def test_invalid_selected_measurements_rejected(tmp_path, changes):
    path = tmp_path/'source.xlsx'
    fixture(path, rows=[row(**changes)])
    assert prep.prepare(path, 'retrospective', D)[3]


def test_unknown_clinical_annotations_and_unused_fallback(tmp_path):
    path = tmp_path/'source.xlsx'
    fixture(path, rows=[row(cytology='?', GB_per_L='?', genetic_subtype='?', **{'cytospin_%': .4}),
                       row(cytology=.2, **{'cytospin_%': 'unused qualified annotation'})])
    frame, _, _, issues = prep.prepare(path, 'retrospective', D)
    assert not issues and frame.peripheral_blast_percent.iat[0] in (20, 40)
    assert frame.gb_per_l.iat[0] == 3 if frame.peripheral_blast_percent.iat[0] == 20 else np.isnan(frame.gb_per_l.iat[0])


@pytest.mark.parametrize('options,reason', [({'drop': ['patient_id']}, 'missing_header'), ({'duplicate':'sample_id'}, 'duplicate_header')])
def test_structure_failures(tmp_path, options, reason):
    path = tmp_path/'source.xlsx'
    fixture(path, **options)
    assert any(i['reason'] == reason for i in prep.prepare(path, 'retrospective', D)[3])


def test_invalid_identity_no_names_fallback(tmp_path):
    path = tmp_path/'source.xlsx'
    fixture(path, rows=[row(patient_id='?')])
    frame, _, _, issues = prep.prepare(path, 'retrospective', D)
    assert frame.empty and issues[0]['reason'] == 'invalid_participant_id'


@pytest.mark.parametrize('raw,value,kind,state', [('=A1', None, 'n', 'cache_unavailable'), ('=A1', None, 'str', 'intentional_empty'), ('<2', '<2', 's', 'qualified_text'), (0, 0, 'n', 'zero')])
def test_raw_cached_measurement_states(raw, value, kind, state):
    cell = SourceCell('A2', 2, 1, raw, value, 'f' if isinstance(raw,str) and raw.startswith('=') else kind, kind, 'General', raw if isinstance(raw,str) and raw.startswith('=') else None)
    assert prep.measurement(cell, D)[1] == state


def test_cohort_qualified_case_sensitive_identity_and_optional_fields(tmp_path):
    path = tmp_path/'source.xlsx'
    fixture(path, rows=[row('P1'), row('p1')], drop=['sex', 'GB_per_L'])
    frame, _, _, issues = prep.prepare(path, 'retrospective', D)
    assert not issues and len(frame) == 2 and frame.sex.isna().all() and frame.gb_per_l.isna().all()


def test_missing_formula_cache_qualified_outcome_and_future_receipt(tmp_path):
    path = tmp_path/'source.xlsx'
    fixture(path, rows=[row('P1', '=1+1'), row('P2', '<5'), row('P3', 10, sampling_date='2099-01-01')])
    frame, counts, rows, issues = prep.prepare(path, 'retrospective', D)
    assert not issues
    assert counts['outcome_cache_unavailable'] == counts['outcome_qualified_text'] == 1
    assert counts['patients_with_positive_outcome'] == 1
    assert frame.loc[frame.cfdna_ng_per_ml.eq(10), 'outcome_sample_n'].iat[0] == 1


def test_seeded_selection_reproducibility_row_order_and_unrelated_patients(tmp_path):
    path = tmp_path/'source.xlsx'
    samples = [row(outcome=5, cytology=.1, sample_id='SAMPLE_A'),
               row(outcome=50, cytology=.9, sample_id='SAMPLE_B')]
    fixture(path, rows=samples)
    original, _, evidence, issues = prep.prepare(path, 'retrospective', D, sample_selection_seed=37)
    assert not issues and sum(r['selected_sample'] for r in evidence) == 1
    again = prep.prepare(path, 'retrospective', D, sample_selection_seed=37)[0]
    assert original.equals(again)
    fixture(path, rows=[row('OTHER', 70), *reversed(samples)])
    reordered = prep.prepare(path, 'retrospective', D, sample_selection_seed=37)[0]
    selected = reordered.loc[reordered.subject_hash.eq(original.subject_hash.iat[0])].reset_index(drop=True)
    assert original.equals(selected)
    assert (original.cfdna_ng_per_ml.iat[0], original.peripheral_blast_percent.iat[0]) in [(5, 10), (50, 90)]


def test_zero_candidates_and_missing_selected_predictors_are_not_redrawn(tmp_path):
    path = tmp_path/'source.xlsx'
    fixture(path, rows=[row(outcome=0, cytology='na', sample_id='SAMPLE_A', **{'cytospin_%':'na'}),
                       row(outcome=20, cytology=.4, sample_id='SAMPLE_B')])
    outcomes = set()
    for seed in range(20):
        frame, _, evidence, issues = prep.prepare(path, 'retrospective', D, sample_selection_seed=seed)
        assert not issues and frame.outcome_sample_n.iat[0] == 1
        outcomes.add(frame.cfdna_ng_per_ml.iat[0])
        if frame.cfdna_ng_per_ml.iat[0] == 0:
            assert np.isnan(frame.peripheral_blast_percent.iat[0])
            assert sum(r['selected_sample'] for r in evidence) == 1
    assert outcomes == {0, 20}


def test_missing_outcome_does_not_replace_available_numeric_candidate(tmp_path):
    path = tmp_path/'source.xlsx'
    fixture(path, rows=[row(outcome='na', cytology=.9, sample_id='SAMPLE_A'),
                       row(outcome=5, cytology=.1, sample_id='SAMPLE_B')])
    frame, counts, evidence, issues = prep.prepare(path, 'retrospective', D)
    assert not issues and frame.cfdna_ng_per_ml.iat[0] == 5
    assert frame.peripheral_blast_percent.iat[0] == 10
    assert counts['outcome_missing'] == 1
    assert [r['outcome'] for r in evidence if r['selected_sample']] == [5]


@pytest.mark.parametrize('seed', [-1, True, 1.5])
def test_invalid_selection_seed_rejected(tmp_path, seed):
    with pytest.raises(ValueError, match='nonnegative integer'):
        prep.prepare(tmp_path/'unused.xlsx', 'retrospective', D, sample_selection_seed=seed)
