from contextlib import redirect_stderr
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from analysis.sample_analysis import runner as canonical
from analysis.cli import arguments
from tests.fixtures.sample_analysis import fixture
import pandas as pd


class CanonicalRunnerTests(unittest.TestCase):
    def test_mode_option_validation(self):
        for args in [
            ['--workflow','canonical','--stage','all'],
            ['--workflow','legacy'],
            ['--workflow','canonical','--retrospective-workbook','a.xlsx'],
            ['--workflow','canonical','--analysis','inventory','--mixed-outlier-drop-n','2'],
        ]:
            with self.subTest(args=args), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                arguments(args)

    def test_circall_flag_selects_canonical(self):
        args = arguments(['--circall', 'input/explicit.xlsx'])
        root = Path(__file__).resolve().parents[2]
        self.assertEqual(args.workflow,'canonical')
        for path in (args.inventory, args.circall, args.donors):
            self.assertEqual(path.parent, root/'input')
        self.assertEqual(args.output_dir.parent, root/'output')

    def test_canonical_defaults_and_relative_overrides(self):
        args=arguments(['--workflow','canonical','--inventory','my.xlsx','--circall','explicit.xlsx'])
        self.assertEqual(args.inventory,Path('my.xlsx').resolve())
        self.assertEqual(args.cohort,'all')
        self.assertEqual(args.circall,Path('explicit.xlsx').resolve())

    def test_circall_is_explicit_even_for_retrospective_controls(self):
        for options in (['--workflow', 'canonical'], ['--cohort', 'retrospective'], ['--analysis', 'kinetics']):
            with self.subTest(options=options), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                arguments(options)

    def test_missing_input_writes_failed_manifest(self):
        with tempfile.TemporaryDirectory() as temp:
            args=arguments(['--workflow','canonical','--inventory',str(Path(temp)/'missing.xlsx'),'--circall',str(Path(temp)/'missing.xlsx'),'--output-dir',str(Path(temp)/'run')])
            with redirect_stderr(io.StringIO()):result=canonical.run(args)
            self.assertEqual(result,1)
            manifest=json.loads((args.output_dir/'run_manifest.json').read_text())
            self.assertEqual(manifest['status'],'failed')

    def test_existing_output_refused(self):
        with tempfile.TemporaryDirectory() as temp:
            (Path(temp)/'keep').write_text('original')
            args=arguments(['--workflow','canonical','--circall','explicit.xlsx','--output-dir',temp])
            with redirect_stderr(io.StringIO()):self.assertEqual(canonical.run(args),1)
            self.assertEqual((Path(temp)/'keep').read_text(),'original')

    def test_model_failure_is_not_unavailable(self):
        from analysis.sample_analysis.preparation import MEASUREMENTS
        frame=fixture()
        frame['source']=frame.cohort
        frame['source_sheet']='synthetic'
        frame['mrd_status']=''
        frame['genetic_subtype']=''
        frame['dna_total_ng_status']=''
        for metric in MEASUREMENTS:
            if metric not in frame:frame[metric]=float('nan')
            frame[metric+'_status']=''
        with tempfile.TemporaryDirectory() as temp:
            source=Path(temp)/'dummy.xlsx';source.write_text('synthetic mocked source')
            args=arguments(['--workflow','canonical','--analysis','longitudinal','--inventory',str(source),
                            '--circall',str(source),'--donors',str(source),'--output-dir',str(Path(temp)/'run')])
            with patch('analysis.sample_analysis.adapters.prepare',return_value=(frame,pd.DataFrame(),{})), \
                 patch('analysis.sample_analysis.analyses.longitudinal',side_effect=RuntimeError('synthetic model failure')), \
                 patch('analysis.sample_analysis.reporting.timepoint_plot'):
                result=canonical.run(args)
            self.assertEqual(result,1)
            manifest=json.loads((args.output_dir/'run_manifest.json').read_text())
            failures=[x for x in manifest['analysis_status'] if x['status']=='failed']
            self.assertEqual({x['cohort'] for x in failures},{'retrospective','circall'})


if __name__=='__main__':unittest.main()
