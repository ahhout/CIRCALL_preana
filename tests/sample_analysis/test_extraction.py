import json
from pathlib import Path
import tempfile
import unittest

import pandas as pd

from analysis.sample_analysis import extraction


class ExtractionProtocolTests(unittest.TestCase):
    def setUp(self):
        self.config = extraction.load_protocols(Path(__file__).resolve().parents[2]/'configs/sample_analysis/extraction_protocols.json')

    def test_metadata_preserves_values_and_never_infers_wells(self):
        frame = pd.DataFrame({
            'cohort': ['circall','retrospective','control','circall'],
            'compartment': ['plasma','plasma','plasma','CSF'],
            'is_control': [False,False,True,False],
            'extraction_method': ['recorded A','recorded B','recorded C','recorded D'],
            'volume_ml': [7,7,2,1],
            'elution_volume_uL': [120,150,60,50],
            'dna_total_ng': [24,30,12,10],
        })
        annotated = extraction.annotate(frame, self.config)
        pd.testing.assert_frame_equal(annotated[frame.columns], frame)
        self.assertEqual(annotated.confirmed_plasma_workflow.tolist(), ['Maxwell','manual','unconfirmed','not applicable'])
        self.assertNotIn('well_count', annotated)
        self.assertNotIn('per_well_elution_volume_uL', annotated)
        self.assertNotIn('confirmed_plasma_workflow', frame)

    def test_report_records_manual_and_maxwell_scope(self):
        result = extraction.summary(self.config).set_index('cohort')
        self.assertEqual(result.loc['circall','max_plasma_per_well_ml'],5)
        self.assertEqual(result.loc['circall','per_well_elution_options_uL'],'50; 60')
        self.assertTrue(pd.isna(result.loc['retrospective','max_plasma_per_well_ml']))
        self.assertEqual(result.loc['retrospective','per_well_elution_options_uL'],'not applicable')

    def test_invalid_protocol_volume_fails_early(self):
        self.config['protocols']['circall']['per_well_elution_options_uL'] = [0]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'protocols.json'
            path.write_text(json.dumps(self.config))
            with self.assertRaisesRegex(ValueError, 'finite positive'):
                extraction.load_protocols(path)
