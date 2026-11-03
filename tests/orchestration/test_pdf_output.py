"""PDF selection preserves PNG export and travels through layered configuration."""
from types import SimpleNamespace

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pytest

from analysis import cli, pipeline
from analysis.provenance import ROOT


@pytest.mark.parametrize('enabled', [True, False])
def test_cli_override_reaches_preflight(monkeypatch, enabled):
    config = pipeline.load_config(ROOT/'configs/pipeline_layers.json')
    for entry in config['workflows'][1:]:
        entry['options']['pdf-output'] = not enabled
    monkeypatch.setattr(pipeline, 'load_config', lambda _: config)
    seen = []
    def preflight(resolved, output):
        for entry in resolved['workflows'][1:]:
            seen.append(pipeline.workflow_args(entry).pdf_output)
        return {}
    monkeypatch.setattr(pipeline, 'preflight', preflight)
    args = cli.arguments(['--validate-only', '--pdf-output' if enabled else '--no-pdf-output'])
    assert pipeline.run(args) == 0
    assert seen == [enabled]*3


@pytest.mark.parametrize('enabled', [True, False])
@pytest.mark.parametrize('layer', ['sample_statistics', 'advanced_analysis', 'disease_modeling'])
def test_rendered_formats(tmp_path, monkeypatch, enabled, layer):
    if layer == 'disease_modeling':
        from analysis.disease_modeling import reporting
        fig, ax = plt.subplots()
        ax.plot([1, 2], [2, 3])
        reporting.save(fig, tmp_path/'example', pdf_output=enabled)
    elif layer == 'sample_statistics':
        from analysis.sample_statistics import reporting
        from tests.fixtures.sample_statistics import D
        field = 'dna_ng_per_ml_plasma'
        row = dict(cohort='circall', control=False, specimen='plasma', assay='cfdna',
                   visit='diag', receipt='received', subject_key='synthetic',
                   measurements={field: dict(value=10)})
        reporting.figures(tmp_path, [row], {**D, 'metrics': {field: D['metrics'][field]}},
                          pooled=True, pdf_output=enabled)
    else:
        from analysis.advanced_analysis import reporting
        monkeypatch.setattr(reporting, 'predictors', lambda _: [SimpleNamespace(variable='x', output_name='x')])
        monkeypatch.setattr(reporting, 'outcome_frame', lambda *a: None)
        monkeypatch.setattr(reporting, 'figure', lambda *a, **kw: plt.subplots()[0])
        result = dict(scope='circall', tables=dict(Coverage=[dict(outcome='y', predictor='x')], Associations=[]))
        reporting.figures(tmp_path, None, result, {}, SimpleNamespace(pdf_output=enabled), {})
    pngs = list(tmp_path.rglob('*.png'))
    pdfs = list(tmp_path.rglob('*.pdf'))
    assert pngs
    assert len(pdfs) == (len(pngs) if enabled else 0)
