"""Retired commands fail before execution; all retained layer interfaces remain explicit."""
import json

import pytest

from analysis.cli import arguments, main
from analysis.pipeline import load_config, LAYERED_WORKFLOWS
from analysis.provenance import ROOT


@pytest.mark.parametrize('name', ['canonical', 'cfdna_associations', 'blast_kinetics'])
def test_retired_workflow_is_absent_and_rejected(tmp_path, name):
    package = 'sample_analysis' if name == 'canonical' else name
    assert not (ROOT/'analysis'/package).exists()
    with pytest.raises(SystemExit) as error:
        arguments(['--workflow', name])
    assert error.value.code == 2
    profile=tmp_path/'retired.json'
    profile.write_text(json.dumps(dict(schema_version=1,workflows=[dict(name=name,options={})])))
    with pytest.raises(ValueError,match='retired workflow'):
        load_config(profile)


@pytest.mark.parametrize('name', ['pipeline_all', 'pipeline_longitudinal', 'pipeline_kinetics', 'pipeline_mrd', 'pipeline_cfdna_spearman'])
def test_retired_profile_fails_without_fallback_or_output(tmp_path, capsys, name):
    target=tmp_path/'must_not_exist'
    assert main(['--config',str(ROOT/'configs'/f'{name}.json'),'--output-dir',str(target)]) == 1
    assert 'Retired profile' in capsys.readouterr().err
    assert not target.exists()


@pytest.mark.parametrize('name', LAYERED_WORKFLOWS)
def test_private_worker_arguments_stay_available(name):
    flags=['--workflow',name,'--inventory','synthetic.xlsx','--cohort','retrospective']
    if name == 'disease_modeling':
        flags += ['--analysis','mrd']
    from analysis.pipeline import workflow_args
    options = dict(inventory="synthetic.xlsx", cohort="retrospective")
    if name == "disease_modeling":
        options["analysis"] = "mrd"
    args=workflow_args(dict(name=name, options=options))
    assert args.workflow == name


def test_unqualified_old_flags_do_not_select_another_workflow():
    with pytest.raises(SystemExit) as error:
        arguments(['--analysis','longitudinal','--circall','synthetic.xlsx'])
    assert error.value.code == 2

@pytest.mark.parametrize('name', LAYERED_WORKFLOWS)
def test_public_layer_module_fails_before_source_access(name, capsys):
    import runpy
    with pytest.raises(SystemExit) as error:
        runpy.run_module('analysis.'+name, run_name='__main__')
    assert error.value.code == 2
    assert 'Single-layer execution is retired' in capsys.readouterr().err


@pytest.mark.parametrize('name', ['pipeline_integrity', 'pipeline_sample_statistics',
                                  'pipeline_advanced_analysis', 'pipeline_disease_modeling'])
def test_single_layer_selector_is_retired(name, tmp_path, capsys):
    output=tmp_path/'must_not_exist'
    assert main(['--config', str(ROOT/'configs'/f'{name}.json'), '--output-dir', str(output)]) == 1
    assert 'Retired profile' in capsys.readouterr().err
    assert not output.exists()
