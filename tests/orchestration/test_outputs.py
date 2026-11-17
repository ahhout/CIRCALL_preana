from tests.fixtures.execution import start_run, run_standalone, prepare_output
"""Layer publication preserves reviewed artifacts, audit evidence and output safety."""
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from analysis import outputs, provenance


class OutputTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / 'run'
        self.details = dict(inputs={}, artifacts=[], quality_status='no_issues_detected', report_generation_status='complete',
                            cohorts=[dict(cohort='circall', report_status='complete')])

    def initialized(self):
        record = start_run(self.root, 'data_integrity', {})
        source = outputs.audit_directory(self.root, 'data_integrity')
        source.mkdir()
        return record, source

    def write(self, source, relative, content='synthetic'):
        path = source / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        self.details['artifacts'].append(dict(path=relative, sha256=provenance.digest(path)))
        return path

    def test_single_layer_integrity_publishes_cohorts_directly(self):
        record, source = self.initialized()
        self.write(source, 'circall/integrity_report.xlsx')
        mappings = outputs.publish(self.root, 'data_integrity', source, self.details)
        self.assertEqual(mappings[0]['path'], 'circall/integrity_report.xlsx')
        self.assertFalse((self.root/'01_data_integrity').exists())
        record.update(status='complete', publications=mappings)
        outputs.finish_run(self.root, record)
        index=json.loads((self.root/'.audit/artifact_index.json').read_text())
        self.assertEqual(next(a['workflow'] for a in index['artifacts'] if a['path']=='circall/integrity_report.xlsx'),'data_integrity')
        with self.assertRaises(ValueError):
            outputs.publish(self.root, 'data_integrity', source, self.details)

    def test_mixed_workflow_keeps_layer_directory(self):
        record, source = self.initialized()
        record.update(workflow='pipeline', workflows=[{'name':'data_integrity'},{'name':'sample_statistics'}])
        provenance.write_json(self.root/'.audit/run_manifest.json',record)
        self.assertEqual(outputs.publication_directory(self.root,'data_integrity'),self.root/'01_data_integrity')

    def test_only_reviewed_results_are_published_and_sources_retained(self):
        _, source = self.initialized()
        for name in ('circall/integrity_report.xlsx', 'circall/findings.json', 'circall/unreviewed.png'):
            self.write(source, name)
        mapping = outputs.publish(self.root, 'data_integrity', source, self.details)
        self.assertEqual({m['path'] for m in mapping}, {'circall/integrity_report.xlsx'})
        self.assertTrue((source/'circall/findings.json').is_file())
        for item in mapping:
            self.assertEqual(provenance.digest(self.root/item['source']),provenance.digest(self.root/item['path']))

    def test_copy_failure_never_publishes_partial_results(self):
        _, source = self.initialized()
        self.write(source, 'circall/integrity_report.xlsx')
        with patch.object(outputs.shutil, 'copyfile', side_effect=OSError('synthetic copy failure')):
            with self.assertRaises(OSError):
                outputs.publish(self.root, 'data_integrity', source, self.details)
        self.assertFalse((self.root/'circall').exists())
        self.assertEqual(list((self.root/'.audit/publication').iterdir()), [])
        self.assertTrue((source/'circall/integrity_report.xlsx').is_file())

    def test_selected_file_disappears_while_another_remains(self):
        _, source = self.initialized()
        self.write(source, 'circall/integrity_report.xlsx')
        lost = self.write(source, 'retrospective/integrity_report.xlsx')
        self.details['cohorts'].append(dict(cohort='retrospective', report_status='complete'))
        lost.unlink()
        with self.assertRaises(ValueError):
            outputs.publish(self.root, 'data_integrity', source, self.details)
        self.assertFalse((self.root/'circall').exists())

    def test_source_replaced_before_staging(self):
        _, source = self.initialized()
        path = self.write(source, 'circall/integrity_report.xlsx')
        path.write_text('replacement')
        with self.assertRaises(ValueError):
            outputs.publish(self.root, 'data_integrity', source, self.details)
        self.assertFalse((self.root/'circall').exists())

    def test_source_changed_during_copy(self):
        _, source = self.initialized()
        path = self.write(source, 'circall/integrity_report.xlsx')
        original_copy = outputs.shutil.copyfile

        def changing_copy(origin, destination):
            original_copy(origin, destination)
            path.write_text('replacement')

        with patch.object(outputs.shutil, 'copyfile', side_effect=changing_copy):
            with self.assertRaises(ValueError):
                outputs.publish(self.root, 'data_integrity', source, self.details)
        self.assertFalse((self.root/'circall').exists())

    def test_index_includes_audit_evidence_and_excludes_cache(self):
        record, source = self.initialized()
        self.write(source, 'circall/integrity_report.xlsx')
        self.write(source, '.cache/temp', 'cache')
        self.write(source, 'run.log')
        record.update(status='complete',publications=outputs.publish(self.root,'data_integrity',source,self.details))
        outputs.finish_run(self.root,record)
        index=json.loads((self.root/'.audit/artifact_index.json').read_text())
        indexed={a['path']:a for a in index['artifacts']}
        relative='.audit/workflows/01_data_integrity/run.log'
        self.assertEqual(indexed[relative]['workflow'],'data_integrity')
        self.assertNotIn('.audit/workflows/01_data_integrity/.cache/temp',indexed)
        self.assertNotIn('.audit/artifact_index.json',indexed)

    def test_changed_visible_copy_invalidates_completion(self):
        record, source=self.initialized()
        self.write(source,'circall/integrity_report.xlsx')
        record.update(status='complete',publications=outputs.publish(self.root,'data_integrity',source,self.details))
        (self.root/'circall/integrity_report.xlsx').write_text('changed')
        with self.assertRaises(ValueError): outputs.finish_run(self.root,record)
        self.assertEqual(json.loads((self.root/'.audit/run_manifest.json').read_text())['status'],'failed')

    def test_symlinks_are_rejected_for_output_publication_and_index(self):
        _,source=self.initialized()
        other=self.write(source,'prepared/source.xlsx')
        (source/'circall').mkdir()
        (source/'circall/integrity_report.xlsx').symlink_to(other)
        with self.assertRaises(ValueError): outputs.publish(self.root,'data_integrity',source,self.details)
        with self.assertRaises(ValueError): provenance.artifact_index(self.root,outputs.DIRECTORIES)
        alias=self.root.parent/'alias'
        alias.symlink_to(self.root,target_is_directory=True)
        with self.assertRaises(ValueError): prepare_output(alias)

    def test_standalone_retains_failed_evidence(self):
        def fail(source):
            source.mkdir()
            self.write(source,'run.log','synthetic failure')
            return 1
        with redirect_stdout(io.StringIO()):
            code=run_standalone('data_integrity',self.root,{},fail,lambda _:self.fail('must not complete'))
        self.assertEqual(code,1)
        self.assertFalse((self.root/'circall').exists())
        self.assertTrue((outputs.audit_directory(self.root,'data_integrity')/'run.log').is_file())
        self.assertEqual(json.loads((self.root/'.audit/run_manifest.json').read_text())['status'],'failed')

    def test_standalone_uses_same_publication_as_integrated_runner(self):
        def execute(source):
            source.mkdir()
            self.write(source,'circall/integrity_report.xlsx')
            return 0
        with redirect_stdout(io.StringIO()):
            code=run_standalone('data_integrity',self.root,{},execute,lambda _:self.details)
        self.assertEqual(code,0)
        self.assertEqual({p.name for p in self.root.iterdir()},{'.audit','circall'})
