from copy import deepcopy
import hashlib

import numpy as np
import pytest

from analysis.sample_statistics.comparisons import compare, significance
from tests.fixtures.sample_statistics import D

FIELD='dna_ng_per_ml_plasma'


def row(subject,visit,value,cohort='circall'):
    return dict(subject_key=subject,visit=visit,control=visit=='control',cohort=cohort,
                specimen='plasma',receipt='received',measurements={FIELD:{'value':value}})


def selected(results,a,b):
    return next(r for r in results if r['visit_1']==a and r['visit_2']==b)


def test_exact_independent_and_paired_reference_values_with_repeat_medians():
    rows=[row(f'CONTROL-{i}','control',i) for i in (1,2,3)]
    rows += [row(f'PATIENT-{i}','diag',i+3) for i in (1,2,3)]
    rows += [row(f'PATIENT-{i}','tp1',2*i+3) for i in (1,2,3)]
    # An extra row must not become another independent participant.
    rows += [row('CONTROL-1','control',1)]
    result=compare(rows,D,'circall')
    independent=selected(result,'control','diag')
    assert independent['n_1']==independent['n_2']==3
    assert independent['statistic']==0
    assert independent['p_value']==pytest.approx(.1)
    assert independent['p_method']=='exact permutation'
    paired=selected(result,'diag','tp1')
    assert paired['paired_n']==3 and paired['statistic']==0
    assert paired['p_value']==pytest.approx(.25)
    assert len(result)==17 and all(r['family_size']==17 for r in result)
    assert independent['p_adjusted']==1
    assert 'PATIENT-' not in str(result) and 'CONTROL-' not in str(result)


def test_repeats_use_medians_and_pairing_uses_only_shared_participants():
    rows=[row('A','diag',0),row('A','diag',10),row('A','tp1',7),
          row('B','diag',100),row('C','tp1',200)]
    result=selected(compare(rows,D,'circall'),'diag','tp1')
    assert result['median_1']==5 and result['median_2']==7
    assert result['paired_n']==result['n_1']==result['n_2']==1
    assert result['available_n_1']==result['available_n_2']==2
    assert result['status']=='unavailable' and '2 matched pairs' in result['reason']


def test_missing_groups_and_all_zero_differences_are_explicit():
    rows=[row('A','diag',0),row('A','tp1',0),row('B','diag',0),row('B','tp1',0)]
    results=compare(rows,D,'circall')
    unavailable=selected(results,'control','diag')
    assert unavailable['status']=='unavailable' and unavailable['p_adjusted'] is None
    assert unavailable['significance']=='NA'
    paired=selected(results,'diag','tp1')
    assert paired['p_value']==paired['p_adjusted']==1
    assert paired['zero_differences']==2 and paired['significance']=='ns'


def test_pooled_participants_remain_cohort_qualified_and_controls_combine():
    rows=[row('SAME','diag',5,c) for c in ('circall','retrospective')]
    rows += [row('SAME','tp1',9,'circall'),row('SAME','control',1,'retrospective'),
             row('OTHER','control',2,'circall')]
    result=compare(rows,D,'pooled')
    assert selected(result,'control','diag')['n_1']==2
    assert selected(result,'control','diag')['n_2']==2
    assert selected(result,'diag','tp1')['paired_n']==1
    assert selected(compare(rows,D,'circall'),'control','diag')['n_1']==1


def test_permutation_results_survive_row_order_and_audit_hashing():
    d=deepcopy(D);d['inference']['resamples']=255
    rows=[row(f'C{i}','control',i%4) for i in range(12)]
    rows += [row(f'P{i}','diag',i+1) for i in range(12)]
    rows += [row(f'P{i}','tp1',i+2+(i%2)) for i in range(12)]
    before=deepcopy(rows)
    expected=compare(rows,d,'circall')
    for r in rows:r['subject_key']=hashlib.sha256(r['subject_key'].encode()).hexdigest()
    rows.reverse()
    assert compare(rows,d,'circall')==expected
    assert any(r['p_method']=='Monte Carlo permutation' for r in expected)
    assert compare(before,d,'circall')==expected


def test_star_thresholds_and_holm_family():
    assert [significance(p) for p in (None,1,.05,.049,.009,.0009,.00009)]==['NA','ns','ns','*','**','***','****']
    from statsmodels.stats.multitest import multipletests
    rows=[row(f'C{i}','control',i) for i in range(4)]
    rows += [row(f'P{i}','diag',i+4) for i in range(4)]
    results=compare(rows,D,'circall')
    expected=multipletests([r['p_value'] if r['p_value'] is not None else 1 for r in results],method='holm')[1]
    for r,p in zip(results,expected):
        if r['p_value'] is not None:assert r['p_adjusted']==pytest.approx(p)


@pytest.mark.parametrize('differences', [[0,1,-1,2,2,-3],[0,0,1],[1,2,3,4],[-2,-2,1,1]])
def test_vectorized_signed_rank_matches_scipy_with_ties_and_zeros(differences):
    from scipy.stats import wilcoxon, PermutationMethod
    from analysis.sample_statistics.comparisons import signed_rank_permutation
    expected=wilcoxon(differences,zero_method='wilcox',method=PermutationMethod(n_resamples=9999),alternative='two-sided')
    actual,_=signed_rank_permutation(differences,D['inference'],42)
    assert actual.statistic==expected.statistic
    assert actual.pvalue==pytest.approx(expected.pvalue)


def test_annotations_show_only_two_control_star_brackets():
    from analysis.sample_statistics.reporting import grant_figure
    import matplotlib.pyplot as plt
    definition=D['metrics'][FIELD]
    rows=[row('C','control',1),row('R','control',2,'retrospective'),row('P','diag',20),row('P','tp1',5)]
    for r in rows:
        if r['control']:r['visit']='control'
    records=[dict(field=FIELD,specimen='plasma',display=True,cohort='pooled',visit_2=v,significance=s,test='Mann–Whitney U')
             for v,s in [('diag','**'),('tp1','*')]]
    records.append(dict(records[0],display=False,visit_2='tp2',significance='****'))
    visits=['control',*definition['plot_visits']]
    fig=grant_figure(rows,FIELD,definition,visits,True,False,42,records)
    assert [t.get_text() for t in fig.axes[0].texts]==['**','*  Mann–Whitney U']
    assert fig.axes[0].get_title()==''
    assert not fig.texts
    assert fig.axes[0].get_xticklabels()[0].get_text()=='Controls\nn=2'
    assert fig.axes[0].lines[-2].get_xdata()[0]==0  # Combined control-group anchor.
    assert not any('p=' in t.get_text() for t in fig.texts)
    plt.close(fig)


def test_comparison_workbook_preserves_numeric_p_values_and_hides_no_tests(tmp_path):
    from openpyxl import load_workbook
    from analysis.sample_statistics.reporting import workbook,validate_workbook
    from tests.fixtures.sample_statistics import saved_result
    result=saved_result()
    rows=[row(f'C{i}','control',i) for i in (1,2,3)]
    rows += [row(f'P{i}','diag',i+3) for i in (1,2,3)]
    result['comparisons']=compare(rows,D,'circall')
    target=tmp_path/'synthetic.xlsx'
    workbook(target,result,D);validate_workbook(target,result,D)
    book=load_workbook(target)
    sheet=book['Comparaisons']
    assert sheet.sheet_state=='visible' and sheet.max_row==22
    assert sheet.cell(6,11).value==pytest.approx(.1)
    assert sheet.cell(6,12).value==1
    assert sheet.cell(6,11).number_format=='0.00E+00'
    assert all('PATIENT-' not in str(c.value) for ws in book for r in ws for c in r)
    book.close()
