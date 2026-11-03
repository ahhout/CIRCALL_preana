from pathlib import Path
from copy import deepcopy
import json
import tempfile
import unittest
from analysis.validation.compare_integrated import compare_tables, compare, scientific_settings


class ComparisonTests(unittest.TestCase):
    def test_missingness_numeric_tolerance_and_identifier_text(self):
        with tempfile.TemporaryDirectory() as temp:
            a, b = Path(temp) / 'a.csv', Path(temp) / 'b.csv'
            a.write_text('sample_id,value\n001,1.0\nna,\n')
            b.write_text('sample_id,value\n001,1.00000000001\nna,\n')
            compare_tables(a, b, 1e-9, 1e-12)
            b.write_text('sample_id,value\n1,1.0\nna,\n')
            with self.assertRaises(AssertionError):
                compare_tables(a, b, 1e-9, 1e-12)

    def test_changed_missingness_does_not_compare_equal(self):
        with tempfile.TemporaryDirectory() as temp:
            a, b = Path(temp) / 'a.csv', Path(temp) / 'b.csv'
            a.write_text('sample_id,value\nsynthetic,\n')
            b.write_text('sample_id,value\nsynthetic,0\n')
            with self.assertRaises(AssertionError):
                compare_tables(a, b, 1e-9, 1e-12)

    def test_relocated_paths_compare_equal_but_changed_science_does_not(self):
        before = {'workflow': 'canonical', 'inputs': {'inventory': {'path': '/old/source', 'sha256': 'same'}},
                  'resolved_settings': {'arguments': {'inventory': '/old/source', 'output_dir': '/old/run',
                                                     'baseline_day_max': 1}}}
        after = deepcopy(before)
        after['inputs']['inventory']['path'] = '/new/source'
        after['resolved_settings']['arguments'].update(inventory='/new/source', output_dir='/new/run')
        self.assertEqual(scientific_settings(before), scientific_settings(after))
        after['resolved_settings']['arguments']['baseline_day_max'] = 2
        self.assertNotEqual(scientific_settings(before), scientific_settings(after))

    def test_retired_cli_fields_compare_equal_only_when_unused(self):
        before = {'workflow': 'canonical', 'inputs': {},
                  'resolved_settings': {'arguments': {'stage': None, 'retrospective_workbook': None}}}
        after = deepcopy(before)
        after['resolved_settings']['arguments'] = {}
        self.assertEqual(scientific_settings(before), scientific_settings(after))
        before['resolved_settings']['arguments']['stage'] = 'bilan'
        self.assertNotEqual(scientific_settings(before), scientific_settings(after))

    def test_comparison_checks_hidden_prepared_tables(self):
        with tempfile.TemporaryDirectory() as temp:
            before, after = Path(temp) / 'before', Path(temp) / 'after'
            left, right = before / 'canonical', after / '.audit/workflows/sample_analysis'
            metadata = {'status': 'complete', 'workflow': 'canonical', 'inputs': {},
                        'resolved_settings': {'arguments': {}}}
            for root in (left, right):
                (root / 'prepared').mkdir(parents=True)
                (root / 'run_manifest.json').write_text(json.dumps(metadata))
                (root / 'prepared/synthetic.csv').write_text('value\n1\n')
            (after / '.audit/run_manifest.json').write_text(json.dumps(
                {'status': 'complete', 'workflow': 'pipeline', 'workflows': [{'name': 'canonical'}]}))
            self.assertTrue(compare(before, after)['passed'])
            (right / 'prepared/synthetic.csv').write_text('value\n2\n')
            result = compare(before, after)
            self.assertFalse(result['passed'])
            self.assertEqual(result['workflows']['canonical']['failures'], ['prepared/synthetic.csv'])
