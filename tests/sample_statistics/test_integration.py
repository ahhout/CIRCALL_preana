from tests.fixtures.pipeline import full_entries
from tests.fixtures.execution import layer_main
"""Actual standalone/master publication equivalence on synthetic inputs."""
from contextlib import redirect_stdout, redirect_stderr
from io import StringIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from analysis.provenance import digest
from analysis.sample_statistics import runner
from analysis.pipeline import main as integrated
from tests.fixtures.sample_statistics import fixture,ASOF


class IntegratedStatisticsTests(unittest.TestCase):
    def test_standalone_master_equivalence_and_publication(self):
        with TemporaryDirectory() as tmp:
            root=Path(tmp);source=root/'synthetic.xlsx';fixture(source,controls=False)
            profile=root/'profile.json'
            options={'circall':str(source),'cohort':'circall','include-controls':False,'assessment-time':ASOF}
            profile.write_text(json.dumps({'schema_version':1,'workflows':full_entries(root,[{'name':'sample_statistics','options':options}])}))
            standalone=root/'standalone';master=root/'master'
            with redirect_stdout(StringIO()),redirect_stderr(StringIO()):
                self.assertEqual(integrated(['--config',str(profile),'--output-dir',str(master),'--validate-only']),0)
                self.assertEqual(layer_main('sample_statistics', ['--circall',str(source),'--cohort','circall','--no-include-controls','--assessment-time',ASOF,'--output-dir',str(standalone)]),0)
                self.assertEqual(integrated(['--config',str(profile),'--output-dir',str(master)]),0)
            for relative in ('circall/statistics.json','circall/observations.json','circall/integrity_findings.json'):
                a=standalone/'.audit/workflows/02_sample_statistics'/relative
                b=master/'.audit/workflows/02_sample_statistics'/relative
                self.assertEqual(json.loads(a.read_text()),json.loads(b.read_text()))
            for directory in (standalone,master):
                index=json.loads((directory/'.audit/artifact_index.json').read_text())
                for artifact in index['artifacts']:
                    self.assertEqual(digest(directory/artifact['path']),artifact['sha256'])
                for artifact in index['publications']:
                    self.assertEqual(digest(directory/artifact['path']),digest(directory/artifact['source']))
            for a in (standalone/'circall').rglob('*.png'):
                self.assertEqual(digest(a),digest(master/'02_sample_statistics'/a.relative_to(standalone)))


if __name__=='__main__':unittest.main()
