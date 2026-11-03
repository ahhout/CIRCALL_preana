import unittest
from analysis.validation.validate_canonical import check_baseline


class BaselineTests(unittest.TestCase):
    def test_baseline_requires_exact_reviewed_inputs(self):
        manifest = {'inputs': {'synthetic': {'sha256': 'first'}}}
        expected = {'schema_version': 1, 'input_sha256': {'synthetic': 'first'}, 'counts': {'pooled_controls': 2}}
        check_baseline(manifest, {'pooled_controls': 2}, expected)
        manifest['inputs']['synthetic']['sha256'] = 'changed'
        with self.assertRaisesRegex(ValueError, 'Unfamiliar source revision'):
            check_baseline(manifest, {'pooled_controls': 2}, expected)

    def test_known_source_count_drift_fails(self):
        with self.assertRaisesRegex(ValueError, 'count changed'):
            check_baseline({'inputs': {}}, {'pooled_controls': 3},
                           {'schema_version': 1, 'input_sha256': {}, 'counts': {'pooled_controls': 2}})
