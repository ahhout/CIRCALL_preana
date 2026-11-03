"""The sole public launcher discovers and enters Conda without shell activation."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

import run as launcher
from analysis.provenance import ROOT
from analysis.pipeline import LAYERED_WORKFLOWS, load_config


def fake_conda(tmp_path, status=0):
    executable=tmp_path/'conda'
    executable.write_text('#!'+sys.executable+'\n'
        'import json,os,sys\n'
        'from pathlib import Path\n'
        'Path(os.environ["LAUNCHER_TEST_LOG"]).write_text(json.dumps(dict(argv=sys.argv[1:],cwd=os.getcwd(),path=os.environ["PATH"])))\n'
        f'raise SystemExit({status})\n')
    executable.chmod(0o755)
    return executable


@pytest.mark.parametrize('arguments',[[],['--validate-only'],['--no-pdf-output'],
    ['--pdf-output'],['--output-dir','outputs/path with spaces'],
    ['--config','profile with spaces.json','--validate-only']])
def test_automatic_conda_launch_preserves_arguments_and_caller_directory(tmp_path,arguments):
    conda=fake_conda(tmp_path)
    log=tmp_path/'command.json'
    env=dict(os.environ,CONDA_DEFAULT_ENV='base',CONDA_EXE=str(conda),LAUNCHER_TEST_LOG=str(log))
    env.pop(launcher.BOOTSTRAP_MARKER,None)
    result=subprocess.run([sys.executable,str(ROOT/'run.py'),*arguments],cwd=tmp_path,
                          env=env,text=True,capture_output=True,check=False)
    assert result.returncode==0,result.stderr
    record=json.loads(log.read_text())
    assert record['argv']==['run','--no-capture-output','-n','pre_analysis','python','-B',str(ROOT/'run.py'),*arguments]
    assert record['cwd']==str(tmp_path)
    assert record['path'].split(os.pathsep)[0]==str(conda.parent)


def test_exit_status_is_preserved(tmp_path):
    conda=fake_conda(tmp_path,status=7)
    env=dict(os.environ,CONDA_DEFAULT_ENV='base',CONDA_EXE=str(conda),LAUNCHER_TEST_LOG=str(tmp_path/'log'))
    env.pop(launcher.BOOTSTRAP_MARKER,None)
    result=subprocess.run([sys.executable,str(ROOT/'run.py')],env=env,cwd=tmp_path,check=False)
    assert result.returncode==7


def test_already_in_correct_environment_does_not_relaunch(monkeypatch):
    from analysis import cli
    monkeypatch.setattr(launcher,'in_environment',lambda:True)
    seen=[]
    monkeypatch.setattr(cli,'main',lambda argv:seen.append(argv) or 9)
    monkeypatch.setattr(launcher.os,'execvpe',lambda *a:pytest.fail('must not relaunch'))
    assert launcher.main(['--validate-only'])==9
    assert seen==[['--validate-only']]


def test_environment_label_alone_is_not_sufficient(monkeypatch,tmp_path):
    monkeypatch.setenv('CONDA_DEFAULT_ENV','pre_analysis')
    monkeypatch.setenv('CONDA_PREFIX',str(tmp_path))
    assert not launcher.in_environment()
    monkeypatch.setenv('CONDA_PREFIX',sys.prefix)
    assert launcher.in_environment()


def test_executable_discovery_precedence_and_home_fallback(tmp_path,monkeypatch):
    selected=fake_conda(tmp_path)
    home=tmp_path/'home'
    home_conda=home/'miniconda3/bin/conda'
    home_conda.parent.mkdir(parents=True)
    home_conda.write_text('#!/bin/sh\nexit 0\n')
    home_conda.chmod(0o755)
    monkeypatch.setattr(launcher.Path,'home',classmethod(lambda cls:home))
    monkeypatch.setenv('CONDA_EXE',str(selected))
    monkeypatch.setattr(launcher.shutil,'which',lambda _:None)
    assert launcher.conda_executable()==selected
    monkeypatch.delenv('CONDA_EXE')
    assert launcher.conda_executable()==home_conda


def test_missing_conda_fails_without_importing_pipeline(monkeypatch,capsys):
    monkeypatch.setattr(launcher,'in_environment',lambda:False)
    monkeypatch.setattr(launcher,'conda_executable',lambda:None)
    monkeypatch.delenv(launcher.BOOTSTRAP_MARKER,raising=False)
    assert launcher.main([])==1
    assert 'Conda is required' in capsys.readouterr().err


def test_wrong_environment_cannot_recurse(monkeypatch,capsys):
    monkeypatch.setattr(launcher,'in_environment',lambda:False)
    monkeypatch.setenv(launcher.BOOTSTRAP_MARKER,'1')
    monkeypatch.setattr(launcher.os,'execvpe',lambda *a:pytest.fail('must not recurse'))
    assert launcher.main([])==1
    assert 'did not select' in capsys.readouterr().err


def test_exec_failure_is_reported_without_traceback(monkeypatch,tmp_path,capsys):
    monkeypatch.setattr(launcher,'in_environment',lambda:False)
    monkeypatch.delenv(launcher.BOOTSTRAP_MARKER,raising=False)
    monkeypatch.setattr(launcher,'conda_executable',lambda:tmp_path/'conda')
    def fail(*args):
        raise OSError('private sentinel')
    monkeypatch.setattr(launcher.os,'execvpe',fail)
    assert launcher.main([])==1
    assert 'could not be launched' in capsys.readouterr().err


def test_combined_profile_has_all_layers_and_no_execution_switches():
    profile=json.loads((ROOT/'configs/pipeline_layers.json').read_text())
    assert all(set(layer)=={'options'} for layer in profile['layers'].values())
    assert tuple(e['name'] for e in load_config(ROOT/'configs/pipeline_layers.json')['workflows'])==LAYERED_WORKFLOWS

