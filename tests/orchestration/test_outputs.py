"""Publication, retained evidence, and historical-reader contracts using synthetic files."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from analysis import outputs, provenance
from analysis.sample_analysis.stats_workbooks import build


class OutputTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / 'run'

    def initialized(self, workflow='canonical'):
        record = outputs.start_run(self.root, workflow, {})
        source = outputs.audit_directory(self.root, workflow)
        source.mkdir()
        return record, source

    def write(self, source, relative, content='synthetic'):
        path = source / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return path

    def test_single_layer_integrity_publishes_cohorts_directly(self):
        record, source = self.initialized('data_integrity')
        self.write(source, 'circall/integrity_report.xlsx')
        details = {'cohorts':[{'cohort':'circall','report_status':'complete'}]}
        mappings = outputs.publish(self.root, 'data_integrity', source, details)
        self.assertEqual(mappings[0]['path'], 'circall/integrity_report.xlsx')
        self.assertFalse((self.root/'01_data_integrity').exists())
        record.update(status='complete', publications=mappings)
        outputs.finish_run(self.root, record)
        index=json.loads((self.root/'.audit/artifact_index.json').read_text())
        self.assertEqual(next(a['workflow'] for a in index['artifacts'] if a['path']=='circall/integrity_report.xlsx'),'data_integrity')
        with self.assertRaises(ValueError):
            outputs.publish(self.root, 'data_integrity', source, details)

    def test_mixed_workflow_keeps_layer_directory(self):
        record, source = self.initialized()
        record['workflow']='pipeline'
        record['workflows']=[{'name':'data_integrity'},{'name':'sample_statistics'}]
        provenance.write_json(self.root/'.audit/run_manifest.json',record)
        self.assertEqual(outputs.publication_directory(self.root,'data_integrity'),self.root/'01_data_integrity')

    def test_only_reviewed_results_are_published_and_sources_retained(self):
        record, source = self.initialized()
        for name in ('spreadsheet/circall_statistics.xlsx', 'inventory/missing_samples_list.csv',
                     'longitudinal/boxplots.png', 'prepared/inventory.csv', 'yield/summary.csv',
                     'longitudinal/circall/diagnostics/model.png', 'yield/new_unreviewed.png'):
            self.write(source, name)
        mapping = outputs.publish(self.root, 'canonical', source, {})
        visible = self.root / 'sample_analysis'
        self.assertEqual({str(p.relative_to(visible)) for p in visible.rglob('*') if p.is_file()},
                         {'circall_statistics.xlsx', 'inventory/missing_samples_list.csv', 'longitudinal/boxplots.png'})
        self.assertTrue((source / 'prepared/inventory.csv').is_file())
        for item in mapping:
            self.assertEqual(provenance.digest(self.root / item['source']), provenance.digest(self.root / item['path']))

    def test_association_publication_flattens_engine_wrapper(self):
        _, source = self.initialized('cfdna_associations')
        for name in ('cohort_summary.csv', 'cfDNA_age_diag/results.csv', 'cfDNA_age_diag/log10_cfDNA_vs_age_diag.png',
                     'cfDNA_age_diag/analysis_data.csv', 'cfDNA_age_diag/assumptions/qq_plot.png'):
            self.write(source / 'cfdna_associations', name)
        record = {'details': {'predictors': [{'output_name': 'cfDNA_age_diag', 'variable': 'age_diag'}]}}
        mappings = outputs.publish(self.root, 'cfdna_associations', source, record)
        self.assertEqual(len(mappings), 3)
        self.assertTrue((self.root / 'cfdna_associations/cfDNA_age_diag/results.csv').is_file())

    def test_copy_failure_never_publishes_partial_results(self):
        _, source = self.initialized()
        self.write(source, 'spreadsheet/circall_statistics.xlsx')
        with patch.object(outputs.shutil, 'copyfile', side_effect=OSError('synthetic copy failure')):
            with self.assertRaises(OSError):
                outputs.publish(self.root, 'canonical', source, {})
        self.assertFalse((self.root / 'sample_analysis').exists())
        self.assertEqual(list((self.root / '.audit/publication').iterdir()), [])
        self.assertTrue((source / 'spreadsheet/circall_statistics.xlsx').exists())

    def test_index_includes_audit_evidence_and_excludes_cache(self):
        record, source = self.initialized('blast_kinetics')
        self.write(source, 'scatter.png')
        self.write(source, 'cohort_summary.json', '{}')
        self.write(source, '.cache/temp', 'cache')
        self.write(source, 'run.log')
        record.update(status='complete', publications=outputs.publish(self.root, 'blast_kinetics', source, {}))
        outputs.finish_run(self.root, record)
        index = json.loads((self.root / '.audit/artifact_index.json').read_text())
        indexed = {a['path']: a for a in index['artifacts']}
        self.assertIn('.audit/workflows/blast_kinetics/run.log', indexed)
        self.assertEqual(indexed['.audit/workflows/blast_kinetics/run.log']['workflow'], 'blast_kinetics')
        self.assertNotIn('.audit/workflows/blast_kinetics/.cache/temp', indexed)
        self.assertNotIn('.audit/artifact_index.json', indexed)
        outputs.validate_owned_run(self.root, 'blast_kinetics')
        self.write(source, 'notes.txt', 'keep')
        with self.assertRaisesRegex(ValueError, 'not owned'):
            outputs.validate_owned_run(self.root, 'blast_kinetics')

    def test_changed_visible_copy_invalidates_completion(self):
        record, source = self.initialized('blast_kinetics')
        self.write(source, 'scatter.png')
        record.update(status='complete', publications=outputs.publish(self.root, 'blast_kinetics', source, {}))
        (self.root / 'blast_kinetics/scatter.png').write_text('changed')
        with self.assertRaises(ValueError):
            outputs.finish_run(self.root, record)
        self.assertEqual(json.loads((self.root / '.audit/run_manifest.json').read_text())['status'], 'failed')

    def test_symlinks_are_rejected_for_output_publication_and_index(self):
        _, source = self.initialized()
        other = self.write(source, 'prepared/source.xlsx')
        (source / 'spreadsheet').mkdir()
        (source / 'spreadsheet/circall_statistics.xlsx').symlink_to(other)
        with self.assertRaises(ValueError):
            outputs.publish(self.root, 'canonical', source, {})
        with self.assertRaises(ValueError):
            provenance.artifact_index(self.root, outputs.DIRECTORIES)
        alias = self.root.parent / 'alias'
        alias.symlink_to(self.root, target_is_directory=True)
        with self.assertRaises(ValueError):
            outputs.prepare_output(alias)

    def test_standalone_retains_failed_evidence(self):
        def fail(source):
            source.mkdir()
            self.write(source, 'run.log', 'synthetic failure')
            return 1
        with redirect_stdout(io.StringIO()):
            code = outputs.run_standalone('canonical', self.root, {}, fail, lambda _: self.fail('must not complete'))
        self.assertEqual(code, 1)
        self.assertFalse((self.root / 'sample_analysis').exists())
        self.assertTrue((outputs.audit_directory(self.root, 'canonical') / 'run.log').is_file())
        self.assertEqual(json.loads((self.root / '.audit/run_manifest.json').read_text())['status'], 'failed')

    def test_standalone_uses_same_publication_as_integrated_runner(self):
        def execute(source):
            source.mkdir()
            self.write(source, 'scatter.png')
            self.write(source, 'cohort_summary.json', '{}')
            return 0
        with redirect_stdout(io.StringIO()):
            code = outputs.run_standalone('blast_kinetics', self.root, {}, execute, lambda _: {'inputs': {}})
        self.assertEqual(code, 0)
        self.assertEqual({p.name for p in self.root.iterdir()}, {'.audit', 'blast_kinetics'})
        outputs.validate_owned_run(self.root, 'blast_kinetics')

    def test_rebuild_reads_old_and_new_layouts_without_overwriting(self):
        _, source = self.initialized()
        self.write(source, 'analysis_status.csv', 'analysis,cohort,status,reason\ninventory,circall,complete,\n')
        self.write(source, 'inventory/availability.csv', 'cohort,count\ncircall,2\n')
        for requested in (self.root, self.root / 'sample_analysis', source):
            destination = self.root.parent / ('report_' + str(len(list(self.root.parent.glob('report_*')))))
            paths = build(requested, destination)
            self.assertEqual(len(paths), 3)
            self.assertTrue(all(p.is_file() for p in paths))
            with self.assertRaises(FileExistsError):
                build(requested, destination)
        historical = self.root.parent / 'historical'
        self.write(historical, 'analysis_status.csv', 'analysis,cohort,status,reason\ninventory,circall,complete,\n')
        self.assertEqual(outputs.engine_directory(historical, 'canonical'), historical)
        self.assertTrue(all(p.is_file() for p in build(historical)))


if __name__ == '__main__':
    unittest.main()
