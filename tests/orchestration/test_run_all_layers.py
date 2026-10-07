"""The Bash entrypoint delegates one invocation to the integrated runner."""
import json
import os
import subprocess

import pytest

from analysis.provenance import ROOT
from analysis.pipeline import LAYERED_WORKFLOWS, load_config


def run_script(tmp_path, *arguments, status=0):
    executable = tmp_path/'conda'
    executable.write_text('''#!/usr/bin/env bash
set -euo pipefail
printf '%s\\0' "$@" > "$LAYER_TEST_COMMANDS"
exit "$LAYER_TEST_STATUS"
''')
    executable.chmod(0o755)
    log = tmp_path/'commands.txt'
    env = dict(os.environ, PATH=str(tmp_path)+os.pathsep+os.environ['PATH'],
               LAYER_TEST_COMMANDS=str(log), LAYER_TEST_STATUS=str(status))
    result = subprocess.run(['bash', str(ROOT/'run_all_layers.sh'), *arguments],
                            cwd=tmp_path, env=env, text=True, capture_output=True, check=False)
    return result, log.read_bytes().decode().rstrip('\0').split('\0') if log.exists() else []


@pytest.mark.parametrize('arguments', [[], ['--validate-only'], ['--output-dir', 'outputs/path with spaces'],
                                      ['--output-dir', 'outputs/fresh', '--validate-only']])
def test_one_integrated_invocation_and_argument_boundaries(tmp_path, arguments):
    result, command = run_script(tmp_path, *arguments)
    assert result.returncode == 0
    assert command == ['run', '--no-capture-output', '-n', 'pre_analysis', 'python', 'run.py',
                       '--config', 'configs/pipeline_layers.json', *arguments]


def test_exit_status_is_preserved(tmp_path):
    result, command = run_script(tmp_path, status=7)
    assert result.returncode == 7 and command


@pytest.mark.parametrize('arguments', [['--output-dir'], ['--unknown'], ['unexpected'], ['--output-dir', '--validate-only']])
def test_invalid_arguments_do_not_launch_conda(tmp_path, arguments):
    result, command = run_script(tmp_path, *arguments)
    assert result.returncode == 2 and not command


def test_help_does_not_launch_conda(tmp_path):
    result, command = run_script(tmp_path, '--help')
    assert result.returncode == 0 and not command
    assert 'one manifest' in result.stdout


def test_combined_profile_preserves_each_single_layer_settings():
    profiles = ['pipeline_integrity.json', 'pipeline_sample_statistics.json',
                'pipeline_advanced_analysis.json', 'pipeline_disease_modeling.json']
    combined = load_config(ROOT/'configs/pipeline_layers.json')
    expected = [load_config(ROOT/'configs'/p)['workflows'][0] for p in profiles]
    assert combined['workflows'] == expected
    assert tuple(e['name'] for e in expected) == LAYERED_WORKFLOWS
    assert [e['name'] for e in load_config(ROOT/'configs/pipeline_all.json')['workflows']] == ['canonical', 'cfdna_associations']
