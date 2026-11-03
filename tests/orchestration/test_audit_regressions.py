"""Regressions for the audit's quality, scope, artifact-population and font findings."""
import importlib
import json
import warnings

import matplotlib.pyplot as plt
from openpyxl import load_workbook
from PIL import Image
import pytest

from analysis.provenance import digest, write_json
from analysis.outputs import finish_run
from tests.fixtures.execution import layer_main


def test_layer2_review_is_not_reported_as_clean(tmp_path, monkeypatch):
    from tests.fixtures.sample_statistics import fixture, ASOF
    from analysis.sample_statistics import runner
    source=tmp_path/'review.xlsx'
    fixture(source)
    book=load_workbook(source)
    sheet=book['cohorte_lal']
    headers=[cell.value for cell in sheet[1]]
    column=headers.index('extraction_date')+1 if 'extraction_date' in headers else len(headers)+1
    sheet.cell(1,column,'extraction_date')
    sheet.cell(2,column,'needs_review')
    book.save(source)
    book.close()
    monkeypatch.setattr(runner,'figures',lambda *a,**kw:None)
    output=tmp_path/'native'
    args=runner.arguments(['--circall',str(source),'--cohort','circall','--no-include-controls',
                           '--assessment-time',ASOF,'--output-dir',str(output)])
    assert runner.run(args)==0
    record=json.loads((output/'run_manifest.json').read_text())
    assert record['cohorts'][0]['integrity_reviews']>0
    assert record['quality_status']=='review_needed'
    runner.validate_results(output,record)


@pytest.fixture(params=['advanced_analysis','disease_modeling'])
def comparison_pair(request,tmp_path,monkeypatch):
    name=request.param
    if name=='advanced_analysis':
        from tests.fixtures.advanced_analysis import sources
        from analysis.advanced_analysis.runner import load_definitions
        from analysis.provenance import ROOT
        retro,circ,donors=sources(tmp_path)
        definition=load_definitions(ROOT/'configs/definitions/advanced_analysis.json')
        switches={c:{o:dict.fromkeys(v,False) for o,v in outcomes.items()}
                  for c,outcomes in definition['comparisons'].items()}
        args=['--inventory',str(retro),'--cohort','retrospective','--no-pool-cohorts',
              '--no-include-controls','--comparison-switches',json.dumps(switches)]
        directory='03_advanced_analysis'
    else:
        from tests.disease_modeling.fixtures import sources
        paths=sources(tmp_path)
        args=['--inventory',str(paths['inventory']),'--cohort','retrospective',
              '--no-include-controls','--analysis','mrd']
        monkeypatch.setattr('analysis.disease_modeling.reporting.figures',lambda *a,**kw:None)
        directory='04_disease_modeling'
    left,right=tmp_path/'left',tmp_path/'right'
    for root in (left,right):
        assert layer_main(name,[*args,'--no-pdf-output','--output-dir',str(root)])==0
    module=importlib.import_module('analysis.validation.validate_'+name)
    return name,left,right,directory,module.compare


def refresh(root,directory):
    native=root/'.audit/workflows'/directory
    manifest=native/'run_manifest.json'
    record=json.loads(manifest.read_text())
    outer=json.loads((root/'.audit/run_manifest.json').read_text())
    outer['provenance']=record
    finish_run(root,outer)


def test_comparator_supports_selected_historical_scope(comparison_pair):
    name,left,right,directory,compare=comparison_pair
    result=compare(left,right)
    assert result['status']=='passed'
    assert result['identical_workbooks']==1


@pytest.mark.parametrize('side',['left','right'])
def test_comparator_rejects_extra_indexed_figure_on_either_side(comparison_pair,side):
    name,left,right,directory,compare=comparison_pair
    root=left if side=='left' else right
    native=root/'.audit/workflows'/directory
    path=native/'retrospective/figures/extra.png'
    path.parent.mkdir(parents=True,exist_ok=True)
    Image.new('RGB',(2,2),'white').save(path)
    manifest=native/'run_manifest.json'
    record=json.loads(manifest.read_text())
    record['artifacts'].append(dict(path=str(path.relative_to(native)),sha256=digest(path)))
    write_json(manifest,record)
    refresh(root,directory)
    with pytest.raises(ValueError,match='Figure artifact populations'):
        compare(left,right)


def test_comparator_rejects_unindexed_file(comparison_pair):
    name,left,right,directory,compare=comparison_pair
    (right/'unexpected.json').write_text('{}')
    with pytest.raises(ValueError,match='Indexed artifact population'):
        compare(left,right)


def test_comparator_rejects_scope_state_mismatch(comparison_pair):
    name,left,right,directory,compare=comparison_pair
    path=right/'.audit/workflows'/directory/'run_manifest.json'
    record=json.loads(path.read_text())
    record['cohorts']=[]
    write_json(path,record)
    refresh(right,directory)
    with pytest.raises(ValueError,match='scopes or completion states'):
        compare(left,right)


def test_count_unit_exponent_exports_without_missing_glyph(tmp_path):
    from analysis.plot_style import save_figure
    fig,ax=plt.subplots()
    ax.plot([1,2],[3,4])
    ax.set_ylabel('WBC count (×10⁹/L)')
    with warnings.catch_warnings():
        warnings.filterwarnings('error',message='Glyph .*missing from font')
        save_figure(fig,tmp_path/'units.png')
        save_figure(fig,tmp_path/'units.pdf')
    assert ax.get_ylabel()=='WBC count (×10$^{9}$/L)'
    plt.close(fig)


def test_comparator_rejects_relabelled_artifact_ownership(comparison_pair):
    name,left,right,directory,compare=comparison_pair
    path=right/'.audit/artifact_index.json'
    index=json.loads(path.read_text())
    item=next(item for item in index['artifacts'] if item['workflow']==name)
    item['workflow']='sample_statistics'
    write_json(path,index)
    with pytest.raises(ValueError,match='Indexed artifact mismatch'):
        compare(left,right)
