import json
from unittest.mock import patch

from analysis.cfdna_associations import worker as runner
from analysis.cfdna_associations import analyze_blast_cfdna as engine
from tests.fixtures.associations import row, toy_cohort


def settings(tmp_path, source):
    path = tmp_path / 'resolved_settings.json'
    path.write_text(json.dumps(dict(inventory=str(source), sheet='Inventaire', phase='diag',
        blood_tissue='Sang', marrow_tissue='Moelle', nucleic_acid='cfDNA', tube='Roche', log_level='INFO')))
    return path


def test_invalid_headers_have_safe_failure_metadata(tmp_path):
    source = tmp_path / 'invalid.csv'
    source.write_text('unrelated\nsynthetic name\n')
    assert runner.run(settings(tmp_path, source)) == 1
    details = (tmp_path / 'workflow_details.json').read_text()
    assert 'missing required columns' in details
    assert 'synthetic name' not in details
    assert not (tmp_path / 'cfdna_associations').exists()


def test_worker_success_and_private_failure(tmp_path):
    import pandas as pd
    source = tmp_path / 'synthetic.csv'
    pd.DataFrame([row('Synthetic', 'Sang', 'cfDNA', .2, 100)]).to_csv(source, index=False)
    config = settings(tmp_path, source)
    assert runner.run(config) == 0
    details = json.loads((tmp_path / 'workflow_details.json').read_text())
    assert details['status'] == 'complete'
    assert details['filtering_counts']['blood_patients'] == 1
    assert details['packages']['pandas']
    assert [p['variable'] for p in details['predictors']] == ['peripheral_blast_percent']
    assert (tmp_path / 'cfdna_associations/cohort_summary.csv').is_file()
    with patch.object(engine, 'load_dataset', side_effect=ValueError('synthetic private identity')):
        assert runner.run(config) == 1
    assert 'synthetic private identity' not in (tmp_path / 'workflow_details.json').read_text()


def test_all_regression_plot_labels(tmp_path):
    cohort = toy_cohort()
    captured = []
    def capture(figure, path):
        axis = figure.axes[0]
        captured.append((axis.get_xlabel(), axis.get_ylabel(), axis.get_title()))
        engine.plt.close(figure)
    for predictor in engine.PREDICTORS:
        data = engine.prepare_analysis_data(cohort, predictor)
        model, _ = engine.fit_regression(data, predictor)
        with patch.object(engine, '_save_figure', side_effect=capture):
            plot = engine.plot_categorical if predictor.kind == 'categorical' else engine.plot_continuous
            plot(data, predictor, model, tmp_path / 'unused.png')
        xlabel, ylabel, title = captured[-1]
        assert xlabel == predictor.label
        assert ylabel == 'log10(cfDNA yield [ng/mL plasma])'
        assert 'log10(cfDNA)' in title
