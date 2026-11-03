"""Runner contracts tested without clinical inputs or a second Conda process."""
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from analysis.cfdna_associations import runner as workflow
from analysis.cli import arguments, main


class AssociationDispatchTests(unittest.TestCase):
    def setUp(self):
        provenance = patch.object(workflow, 'git_state', return_value={'code_revision': 'synthetic', 'code_dirty': False})
        provenance.start()
        self.addCleanup(provenance.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'synthetic.csv'
        self.source.write_text('synthetic\n1\n')
        self.output = self.root / 'run'

    def args(self, *extra):
        return arguments(['--workflow', 'cfdna_associations', '--inventory', str(self.source),
                          '--output-dir', str(self.output), *extra])

    def run_quiet(self, args):
        with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
            return workflow.run(args)

    def manifest(self):
        return json.loads((self.output / 'run_manifest.json').read_text())

    def test_rejects_foreign_and_destructive_options(self):
        for options in (['--analysis', 'all'], ['--cohort', 'all'],
                        ['--stage', 'all'], ['--baseline-day-max', '1'],
                        ['--overwrite'], ['--donors', 'donors.xlsx'], ['--mixed-outlier-drop-n', '0']):
            with self.subTest(options=options), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                self.args(*options)
        with redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            arguments(['--workflow', 'canonical', '--circall', 'a.xlsx', '--tube', 'Roche'])

    def test_main_dispatch_and_relative_override(self):
        with patch.object(workflow, 'run', return_value=7) as run:
            self.assertEqual(main(['--workflow', 'cfdna_associations', '--inventory', 'other.csv', '--output-dir', str(self.output)]), 7)
        self.assertEqual(run.call_args.args[0].inventory, Path('other.csv').resolve())

    def test_catalog_hash_and_explicit_override(self):
        catalog = self.root / 'catalog.json'
        catalog.write_text(json.dumps({'sources': [{'workflow': 'cfdna_associations',
                            'path': str(self.source), 'sha256': 'wrong'}]}))
        args = self.args(); args.inventory = None
        with patch.object(workflow, 'CATALOG', catalog), patch.object(workflow.subprocess, 'run') as child:
            self.assertEqual(self.run_quiet(args), 1)
            child.assert_not_called()
            self.assertIn('hash mismatch', self.manifest()['error'])
            path, source = workflow.resolve_source(self.source)
        self.assertEqual(path, self.source)
        self.assertEqual(source['selection'], 'explicit')
        self.assertIsNone(source['expected_sha256'])
        self.assertEqual(source['sha256'], workflow.digest(self.source))

    def test_missing_source_and_existing_output(self):
        args = self.args(); args.inventory = self.root / 'missing.csv'
        self.assertEqual(self.run_quiet(args), 1)
        self.assertEqual(self.manifest()['status'], 'failed')
        before = (self.output / 'run_manifest.json').read_bytes()
        self.assertEqual(self.run_quiet(self.args()), 1)
        self.assertEqual((self.output / 'run_manifest.json').read_bytes(), before)

    def test_missing_environment_actionable_and_no_fallback(self):
        with patch.object(workflow.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1)) as child:
            self.assertEqual(self.run_quiet(self.args()), 1)
        child.assert_called_once()
        self.assertIn('conda create -n pre_analysis --file', self.manifest()['error'])

    def test_dispatch_records_settings_failure_and_actual_hash(self):
        def failed_child(command, **kwargs):
            (self.output / 'workflow_details.json').write_text(json.dumps({'status': 'failed', 'error': 'safe failure'}))
            return subprocess.CompletedProcess(command, 1)
        with patch.object(workflow.subprocess, 'run', side_effect=failed_child) as child:
            self.assertEqual(self.run_quiet(self.args('--tube', 'Test', '--sheet', 'Sheet1')), 1)
        self.assertEqual(child.call_args.args[0][:7], ['conda', 'run', '--no-capture-output', '-n',
                                                      'pre_analysis', 'python', '-m'])
        saved = self.manifest()
        self.assertEqual(saved['settings']['tube'], 'Test')
        self.assertEqual(saved['settings']['sheet'], 'Sheet1')
        self.assertEqual(saved['inputs']['inventory']['sha256'], workflow.digest(self.source))
        self.assertEqual(saved['error'], 'safe failure')


if __name__ == '__main__':
    unittest.main()
