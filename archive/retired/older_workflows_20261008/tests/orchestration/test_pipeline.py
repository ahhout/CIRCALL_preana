"""Integrated runner safety and failure propagation, with synthetic sources only."""
from contextlib import redirect_stdout, redirect_stderr
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from analysis import pipeline
from analysis import provenance
from analysis import artifacts
from analysis.cli import arguments, main
from analysis.worker import completion
from analysis.outputs import audit_directory


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'synthetic.xlsx'
        self.source.write_text('synthetic source')
        self.config = self.root / 'pipeline.json'
        self.entries = [{'name': 'canonical', 'options': {'circall': 'synthetic.xlsx', 'analysis': 'inventory'}},
                        {'name': 'cfdna_associations', 'options': {'inventory': 'synthetic.xlsx'}}]
        self.write_config()
        self.output = self.root / 'fresh'
        self.evidence = {e['name']: {'status': 'complete', 'workflow': e['name'], 'schema_version': 1,
                          'environment_name': pipeline.REGISTRY[e['name']],
                          'inputs': {'synthetic': {'path': str(self.source), 'sha256': provenance.digest(self.source)}}}
                         for e in self.entries}

    def write_config(self, entries=None):
        self.config.write_text(json.dumps({'schema_version': 1, 'workflows': entries if entries is not None else self.entries}))

    def run_quiet(self, *options):
        args = pipeline.arguments(['--config', str(self.config), '--output-dir', str(self.output), *options])
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            return pipeline.run(args)

    def test_options_and_config_paths_are_explicit(self):
        loaded = pipeline.load_config(self.config)
        self.assertEqual(loaded['workflows'][0]['options']['circall'], str(self.source))
        self.assertEqual(pipeline.worker_command('blast_kinetics')[:5], ['conda', 'run', '--no-capture-output', '-n', 'pre_analysis'])
        argv = pipeline.option_argv({'pool-cohorts': False, 'mixed-random-slope-sensitivity': False})
        self.assertEqual(argv, ['--no-pool-cohorts'])

    def test_default_dispatch_uses_layered_profile(self):
        for argv in ([], ['--validate-only'], ['--no-validate-only'], ['--output-dir', str(self.output)]):
            with self.subTest(argv=argv):
                args = arguments(argv)
                self.assertEqual(args.config, pipeline.ROOT / 'configs/pipeline_layers.json')
        config = pipeline.load_config(arguments([]).config)
        self.assertEqual([entry['name'] for entry in config['workflows']],
                         list(pipeline.LAYERED_WORKFLOWS))
        with patch.object(pipeline, 'run', return_value=0) as run, patch('sys.argv', ['run.py']):
            self.assertEqual(main(), 0)
        self.assertEqual(run.call_args.args[0].config, pipeline.ROOT / 'configs/pipeline_layers.json')

    def test_compatibility_profile_and_direct_flags_remain_selectable(self):
        args = arguments(['--config', str(pipeline.ROOT/'configs/pipeline_all.json')])
        self.assertEqual([e['name'] for e in pipeline.load_config(args.config)['workflows']],
                         ['canonical', 'cfdna_associations'])
        for flags in (['--workflow', 'canonical', '--circall', str(self.source)],
                      ['--circall', str(self.source), '--analysis', 'inventory']):
            self.assertEqual(arguments(flags).workflow, 'canonical')
        self.assertEqual(arguments(['--workflow', 'cfdna_associations']).workflow, 'cfdna_associations')

    def test_consolidated_kinetics_profiles_select_counts_and_mrd_once(self):
        from analysis.sample_analysis.runner import selection
        full = pipeline.load_config(pipeline.ROOT / 'configs/pipeline_all.json')
        focused = pipeline.load_config(pipeline.ROOT / 'configs/pipeline_kinetics.json')
        self.assertEqual([entry['name'] for entry in focused['workflows']], ['canonical'])
        full_args = pipeline.workflow_args(full['workflows'][0])
        focused_args = pipeline.workflow_args(focused['workflows'][0])
        cohorts, tasks, inputs = selection(focused_args)
        self.assertEqual(cohorts, ['retrospective', 'circall'])
        self.assertEqual(tasks, ['kinetics', 'mrd'])
        self.assertEqual(inputs['retrospective_blasts'], pipeline.ROOT / 'input/retrospective_blast_count_01102026.xlsx')
        self.assertEqual(focused_args.retrospective_blast_unit, 'x10^9/L')
        self.assertEqual(inputs['blood_counts'], pipeline.ROOT / 'input/CIRCALL_wbc_blast_count_01102026.xlsx')
        self.assertEqual(inputs['circall'], pipeline.ROOT / 'input/inventaire_CIRCALL_01102026.xlsx')
        for args in (full_args, focused_args):
            selected = selection(args)[1]
            self.assertEqual(selected.count('kinetics'), 1)
            self.assertEqual(selected.count('mrd'), 1)
        for field in ('baseline_day_max', 'baseline_selection', 'overlay_max_day',
                      'mrd_unknown_level', 'mrd_negative_level'):
            self.assertEqual(getattr(focused_args, field), getattr(full_args, field))

    def test_normalized_kinetics_remains_explicitly_selectable(self):
        profile = pipeline.ROOT / 'configs/blast_kinetics/blast_kinetics.yml'
        self.write_config([{'name': 'blast_kinetics', 'profile': str(profile)}])
        self.assertEqual(pipeline.load_config(self.config)['workflows'],
                         [{'name': 'blast_kinetics', 'profile': str(profile)}])

    def test_config_execution_settings_and_cli_override(self):
        config = {'schema_version': 1, 'workflows': self.entries,
                  'output-dir': 'configured-run', 'validate-only': True}
        self.config.write_text(json.dumps(config))
        args = pipeline.arguments(['--config', str(self.config)])
        with patch.object(pipeline, 'preflight', return_value=self.evidence) as preflight, \
                patch.object(pipeline, 'run_worker') as worker, redirect_stdout(io.StringIO()):
            self.assertEqual(pipeline.run(args), 0)
        self.assertEqual(preflight.call_args.args[1], self.root / 'configured-run')
        worker.assert_not_called()
        self.assertFalse((self.root / 'configured-run').exists())
        args = pipeline.arguments(['--config', str(self.config), '--output-dir', str(self.output),
                                   '--no-validate-only'])
        with patch.object(pipeline, 'preflight', side_effect=ValueError('stop after resolution')), \
                redirect_stderr(io.StringIO()):
            self.assertEqual(pipeline.run(args), 1)
        self.assertEqual(args.output_dir, self.output)
        self.assertFalse(args.validate_only)
        for key, value in [('output-dir', ''), ('output-dir', 1), ('validate-only', 'false')]:
            with self.subTest(key=key, value=value):
                invalid = dict(config, **{key: value})
                self.config.write_text(json.dumps(invalid))
                with self.assertRaises(ValueError):
                    pipeline.load_config(self.config)

    def test_worker_cache_does_not_occupy_atomic_destination(self):
        destination = self.output / 'blast_kinetics'
        environment = pipeline.worker_environment(destination)
        self.assertFalse(Path(environment['MPLCONFIGDIR']).is_relative_to(destination))
        self.assertTrue(Path(environment['MPLCONFIGDIR']).is_relative_to(self.output))

    def test_invalid_configuration_and_option_types(self):
        invalid = [[], [self.entries[0], self.entries[0]], [{'name': 'unknown', 'options': {}}], [{'name': 'legacy', 'options': {}}],
                   [{'name': 'canonical', 'options': {}}],
                   [{'name': 'canonical', 'options': {'circall': 'synthetic.xlsx', 'overwrite': True}}],
                   [{'name': 'canonical', 'options': {'circall': 'synthetic.xlsx', 'mixed-outlier-drop-n': True}}],
                   [{'name': 'cfdna_associations', 'options': {'phase': 7}}],
                   [{'name': 'canonical', 'options': {'circall': 'synthetic.xlsx', 'pool-cohorts': 'false'}}]]
        for entries in invalid:
            with self.subTest(entries=entries):
                self.write_config(entries)
                with self.assertRaises(ValueError):
                    pipeline.load_config(self.config)
        self.config.write_text('{"schema_version":1,"schema_version":1,"workflows":[]}')
        with self.assertRaises(ValueError):
            pipeline.load_config(self.config)

    def test_rejects_integrated_and_single_workflow_flags(self):
        for flag in ('--workflow', '--analysis', '--circall', '--overwrite'):
            with self.subTest(flag=flag), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                arguments(['--config', str(self.config), flag, 'canonical'])

    def test_preflight_calls_every_selected_environment(self):
        def child(command, **kwargs):
            name = command[command.index('--workflow') + 1]
            return subprocess.CompletedProcess(command, 0, stdout=json.dumps(self.evidence[name]))
        with patch.object(pipeline.subprocess, 'run', side_effect=child) as worker:
            evidence = pipeline.preflight(pipeline.load_config(self.config), self.output)
        self.assertEqual(set(evidence), set(self.evidence))
        self.assertEqual(len(worker.call_args_list), 2)
        self.assertTrue(all(call.kwargs['cwd'] == pipeline.ROOT for call in worker.call_args_list))

    def test_preflight_failure_publishes_nothing(self):
        with patch.object(pipeline.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1, stdout='private source text')):
            self.assertEqual(self.run_quiet(), 1)
        self.assertFalse(self.output.exists())

    def test_validate_only_does_not_create_outputs(self):
        with patch.object(pipeline, 'preflight', return_value=self.evidence), patch.object(pipeline, 'run_worker') as worker:
            self.assertEqual(self.run_quiet('--validate-only'), 0)
        self.assertFalse(self.output.exists())
        self.assertEqual(worker.call_count, 0)

    def test_failure_continues_independent_workflow(self):
        results = [subprocess.CompletedProcess([], 1), subprocess.CompletedProcess([], 0)]
        with patch.object(pipeline, 'preflight', return_value=self.evidence), \
             patch.object(pipeline, 'run_worker', side_effect=results) as worker, \
             patch('analysis.worker.completion', return_value={'inputs': {}}), \
             patch.object(pipeline, 'publish', return_value=[]):
            self.assertEqual(self.run_quiet(), 1)
        record = json.loads((self.output / '.audit/run_manifest.json').read_text())
        self.assertEqual([s['status'] for s in record['workflows']], ['failed', 'complete'])
        self.assertEqual([call.args[2] for call in worker.call_args_list], [audit_directory(self.output, e['name']) for e in self.entries])
        self.assertNotIn('private source', (self.output / '.audit/run_manifest.json').read_text())

    def test_zero_exit_without_completion_artifacts_fails(self):
        with patch.object(pipeline, 'preflight', return_value=self.evidence), \
             patch.object(pipeline, 'run_worker', return_value=subprocess.CompletedProcess([], 0)):
            self.assertEqual(self.run_quiet(), 1)
        record = json.loads((self.output / '.audit/run_manifest.json').read_text())
        self.assertTrue(all(s['status'] == 'failed' for s in record['workflows']))

    def test_interruption_marks_pending_workflows_not_run(self):
        with patch.object(pipeline, 'preflight', return_value=self.evidence), \
             patch.object(pipeline, 'run_worker', side_effect=KeyboardInterrupt):
            self.assertEqual(self.run_quiet(), 1)
        record = json.loads((self.output / '.audit/run_manifest.json').read_text())
        self.assertEqual([s['status'] for s in record['workflows']], ['interrupted', 'not_run'])

    def test_worker_interruption_terminates_child_process_group(self):
        from unittest.mock import Mock
        worker = Mock(pid=12345)
        worker.communicate.side_effect = KeyboardInterrupt
        worker.poll.return_value = None
        with patch.object(pipeline.subprocess, 'Popen', return_value=worker), patch.object(pipeline.os, 'killpg') as terminate:
            with self.assertRaises(KeyboardInterrupt):
                pipeline.run_worker(['synthetic-command'], self.entries[0], self.output / 'canonical', io.StringIO())
        self.assertEqual(terminate.call_args.args, (12345, pipeline.signal.SIGTERM))
        worker.wait.assert_called_once_with(timeout=5)

    def test_input_change_invalidates_success(self):
        def child(*args):
            self.source.write_text('changed synthetic source')
            return subprocess.CompletedProcess([], 0)
        with patch.object(pipeline, 'preflight', return_value=self.evidence), patch.object(pipeline, 'run_worker', side_effect=child), \
             patch('analysis.worker.completion', return_value={'inputs': {}}), \
             patch.object(pipeline, 'publish', return_value=[]):
            self.assertEqual(self.run_quiet(), 1)
        self.assertEqual(json.loads((self.output / '.audit/run_manifest.json').read_text())['status'], 'failed')

    def test_existing_destination_is_preserved(self):
        self.output.mkdir()
        keep = self.output / 'keep.txt'
        keep.write_text('keep')
        self.assertEqual(self.run_quiet(), 1)
        self.assertEqual(keep.read_text(), 'keep')

    def test_artifact_headers_and_image_structure(self):
        self.output.mkdir()
        (self.output / 'table.csv').write_text('wrong\nsynthetic\n')
        with self.assertRaises(ValueError):
            artifacts.validate_files(self.output, {'table.csv': ['required']})
        (self.output / 'plot.png').write_text('not a PNG')
        with self.assertRaises(ValueError):
            artifacts.validate_files(self.output, {'plot.png': []})

    def test_index_hashes_published_files_and_ignores_cache(self):
        self.output.mkdir()
        folder = self.output / 'canonical'
        folder.mkdir()
        (folder / 'result.json').write_text('{}')
        (folder / '.cache').mkdir()
        (folder / '.cache/temp').write_text('cache')
        index = provenance.artifact_index(self.output, ['canonical'])
        self.assertEqual(len(index['artifacts']), 1)
        self.assertEqual(index['artifacts'][0]['workflow'], 'canonical')
        self.assertEqual(index['artifacts'][0]['sha256'], provenance.digest(folder / 'result.json'))

    def test_metadata_atomic_write_preserves_old_file_on_serialization_error(self):
        path = self.root / 'metadata.json'
        provenance.write_json(path, {'status': 'running'})
        with self.assertRaises(ValueError):
            provenance.write_json(path, {'value': float('nan')})
        self.assertEqual(json.loads(path.read_text()), {'status': 'running'})


if __name__ == '__main__':
    unittest.main()


def test_catalog_hash_failure_is_actionable_without_relaying_raw_output(tmp_path):
    import subprocess
    from unittest.mock import patch
    import pytest
    from analysis import pipeline
    result=subprocess.CompletedProcess([],1,stdout='{"error_code":"CatalogHashMismatch"}',stderr='private source content')
    with patch.object(pipeline.subprocess,'run',return_value=result):
        with pytest.raises(ValueError,match='workbook hash differs from configs/source_catalog.json') as error:
            pipeline.preflight({'workflows':[{'name':'cfdna_associations','options':{}}]},tmp_path/'fresh')
    assert 'private source content' not in str(error.value)
