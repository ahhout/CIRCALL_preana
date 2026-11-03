"""Kinetics rendering must not change the appearance of later workflows."""
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
import pandas as pd
import pytest

from analysis.blast_kinetics import plotting
from analysis.blast_kinetics.statistics import FittedTrend


def plot_case(kind, config):
    frame = pd.DataFrame({
        'subject_id': ['synthetic-a', 'synthetic-a', 'synthetic-b', 'synthetic-b'],
        'time': [1, 2, 1, 2],
        'analysis_value': [100., 50., 100., 40.],
        'group': ['HeH'] * 4,
    })
    config['bootstrap']['resamples'] = 20
    config['plots'][kind].update(enabled=True, width=6, height=4, dpi=40)
    if kind == 'scatter':
        return plotting.plot_scatter, frame
    trend = FittedTrend(None, frame, pd.DataFrame({'time': [1, 2], 'predicted': [100., 45.]}))
    return plotting.plot_model, trend


@pytest.mark.parametrize('kind', ['scatter', 'model'])
@pytest.mark.parametrize('outcome', ['success', 'save_failure', 'disabled'])
def test_plot_restores_callers_style(tmp_path, blast_config, monkeypatch, kind, outcome):
    plot, data = plot_case(kind, blast_config)
    output = tmp_path/f'{kind}.png'
    if outcome == 'disabled':
        blast_config['plots'][kind]['enabled'] = False
    elif outcome == 'save_failure':
        def fail(*args, **kwargs):
            raise OSError('synthetic save failure')
        monkeypatch.setattr(Figure, 'savefig', fail)
    # Choose a caller style different from the kinetics whitegrid style.
    with plt.rc_context({'axes.grid': False, 'axes.edgecolor': 'purple',
                         'font.sans-serif': ['DejaVu Sans']}):
        plt.get_backend()
        before = dict(plt.rcParams)
        existing_figures = set(plt.get_fignums())
        try:
            if outcome == 'save_failure':
                with pytest.raises(OSError, match='synthetic save failure'):
                    plot(data, blast_config, output)
            else:
                plot(data, blast_config, output)
            assert dict(plt.rcParams) == before
            assert output.is_file() == (outcome == 'success')
        finally:
            for number in set(plt.get_fignums()) - existing_figures:
                plt.close(number)
