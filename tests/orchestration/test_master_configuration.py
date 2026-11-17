"""Master selection, path ownership and configuration-input provenance."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from analysis import cli, pipeline
from analysis.layer_configuration import read_profile, select_layers
from analysis.provenance import ROOT


def master(tmp_path):
    config = json.loads((ROOT/'configs/pipeline_layers.json').read_text())
    config['sources'] = {k: str(tmp_path/(k+'.xlsx')) for k in config['sources']}
    config['defaults']['rules'] = str(ROOT/'configs/definitions/data_integrity.json')
    for layer in config['layers'].values():
        if 'definitions' in layer['options']:
            layer['options']['definitions'] = str(ROOT/'configs'/layer['options']['definitions'])
    return config


def write(path, config):
    path.write_text(json.dumps(config))
    return path


def test_shared_sources_defaults_and_full_references(tmp_path):
    config = master(tmp_path)
    config['sources']['circall'] = 'selected.xlsx'
    config['defaults']['pdf-output'] = True
    config['layers']['advanced_analysis']['options']['pdf-output'] = False
    path = write(tmp_path/'master.json', config)
    folder = tmp_path/'profiles'
    folder.mkdir()
    alias = write(folder/'full.json', {'schema_version': 2, 'profile': '../master.json', 'layers': [4, 2, 1, 3]})
    entries = pipeline.load_config(path)['workflows']
    assert all(e['options']['circall'] == str(tmp_path/'selected.xlsx') for e in entries)
    assert [e['options']['pdf-output'] for e in entries[1:]] == [True, False, True]
    assert pipeline.load_config(alias)['workflows'] == entries
    assert read_profile(alias)[3] == [alias, path]
    for layer in config['layers'].values():
        layer['enabled'] = True
    assert pipeline.load_config(write(path, config))['workflows'] == entries


def test_public_partial_selection_is_rejected_before_preflight(tmp_path, monkeypatch):
    import pytest
    with pytest.raises(SystemExit) as error:
        cli.arguments(['--layers', '4', '2', '--validate-only'])
    assert error.value.code == 2
    config = master(tmp_path)
    config['layers']['advanced_analysis']['enabled'] = False
    with pytest.raises(ValueError):
        pipeline.load_config(write(tmp_path/'master.json', config))
    with pytest.raises(ValueError, match='All four'):
        select_layers({'workflows': []}, [2, 2])


@pytest.mark.parametrize('change', [
    lambda c: c['layers']['advanced_analysis'].update(enabled='false'),
    lambda c: c['layers']['advanced_analysis']['options'].update(unknown=True),
    lambda c: c['layers']['advanced_analysis']['options'].update(inventory='override.xlsx'),
    lambda c: c['sources'].update(unrecognized='source.xlsx'),
    lambda c: c['defaults'].update(unknown=True),
    lambda c: c['defaults'].update({'pdf-output': 'false'}),
    lambda c: c['layers'].pop('data_integrity'),
    lambda c: [layer.update(enabled=False) for layer in c['layers'].values()],
])
def test_invalid_master_fails_before_execution(tmp_path, change):
    config = master(tmp_path)
    change(config)
    with pytest.raises(ValueError):
        pipeline.load_config(write(tmp_path/'invalid.json', config))


def test_comparison_switches_reach_engine_without_changing_rules(tmp_path):
    config = master(tmp_path)
    switches = config['layers']['advanced_analysis']['options']['comparison-switches']
    for outcomes in switches.values():
        for comparisons in outcomes.values():
            for predictor in comparisons:
                comparisons[predictor] = False
    entry = pipeline.load_config(write(tmp_path/'master.json', config))['workflows'][2]
    args = pipeline.workflow_args(entry)
    assert args.comparison_switches == switches
    from analysis.advanced_analysis.step_01_prepare import load_definitions
    from analysis.advanced_analysis.schema import with_comparison_switches, comparisons
    original = load_definitions(args.definitions)
    resolved = with_comparison_switches(original, args.comparison_switches)
    assert comparisons(resolved, 'pooled') == []
    assert {k: v for k, v in resolved.items() if k != 'comparisons'} == {
        k: v for k, v in original.items() if k != 'comparisons'}
    invalid = deepcopy(switches)
    invalid['circall']['dna_total_ng']['unapproved_predictor'] = True
    with pytest.raises(ValueError, match='approved matrix'):
        with_comparison_switches(original, invalid)


def test_reference_cycle_and_invalid_selection_fail(tmp_path):
    first, second = tmp_path/'a.json', tmp_path/'b.json'
    write(first, {'schema_version': 2, 'profile': 'b.json'})
    write(second, {'schema_version': 2, 'profile': 'a.json'})
    with pytest.raises(ValueError, match='Cyclic'):
        pipeline.load_config(first)
    for selection in ([], [True], [1, 1], [5]):
        write(first, {'schema_version': 2, 'profile': 'b.json', 'layers': selection})
        with pytest.raises(ValueError, match='All four'):
            pipeline.load_config(first)


def test_changed_referenced_master_invalidates_preflight(tmp_path, monkeypatch):
    path = write(tmp_path/'master.json', master(tmp_path))
    alias = write(tmp_path/'alias.json', {'schema_version': 2, 'profile': 'master.json'})
    def changed(config, output):
        path.write_text(path.read_text()+'\n')
        return {}
    monkeypatch.setattr(pipeline, 'preflight', changed)
    args = pipeline.arguments(['--config', str(alias), '--validate-only', '--output-dir', str(tmp_path/'output')])
    assert pipeline.run(args) == 1
    assert not args.output_dir.exists()


def test_shipped_profiles_contain_only_references():
    for path in (ROOT/'configs').glob('pipeline_*.json'):
        if path.name != 'pipeline_layers.json':
            assert set(json.loads(path.read_text())) <= {'schema_version', 'profile', 'layers'}


def test_master_execution_records_reference_chain_and_all_layers(tmp_path):
    from tests.fixtures.pipeline import full_entries
    config = dict(schema_version=1, workflows=full_entries(tmp_path))
    path = write(tmp_path/'master.json', config)
    alias = write(tmp_path/'full.json', {'schema_version': 2, 'profile': 'master.json'})
    output = tmp_path/'run'
    argv = ['--config', str(alias), '--output-dir', str(output)]
    assert pipeline.main([*argv, '--validate-only']) == 0
    assert not output.exists()
    assert pipeline.main(argv) == 0
    manifest = json.loads((output/'.audit/run_manifest.json').read_text())
    assert {Path(item['path']) for item in manifest['inputs'].values()} == {alias, path}
    resolved = json.loads((output/'.audit/resolved_config.json').read_text())
    assert [entry['name'] for entry in resolved['workflows']] == list(pipeline.LAYERED_WORKFLOWS)
    assert (output/'01_data_integrity/retrospective/integrity_report.xlsx').is_file()

def test_full_schema1_order_and_partial_schema1_rejection(tmp_path):
    from tests.fixtures.pipeline import full_entries
    entries=full_entries(tmp_path)
    path=write(tmp_path/'complete.json',dict(schema_version=1,workflows=list(reversed(entries))))
    assert [entry['name'] for entry in pipeline.load_config(path)['workflows']]==list(pipeline.LAYERED_WORKFLOWS)
    for invalid in (entries[:1],entries[:-1],entries+[entries[0]]):
        with pytest.raises(ValueError):
            pipeline.load_config(write(path,dict(schema_version=1,workflows=invalid)))
