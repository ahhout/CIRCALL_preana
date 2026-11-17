"""Figure legends remain readable without covering data, axes labels, or notes."""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
import pytest

from analysis.utils.figure_layout import legends_below


@pytest.mark.parametrize('exporter', ['shared', 'diagnostics', 'disease'])
def test_all_exporters_use_arial_and_clear_axis_labels(tmp_path, exporter):
    from matplotlib.font_manager import findfont
    from matplotlib.text import Text
    from analysis.utils.figure_layout import FONT_FAMILY, FONT_SIZE, LEGEND_GAP_POINTS
    from analysis.utils.plot_style import save_figure
    fig, axes = plt.subplots(1, 2, figsize=(10, 5))
    for ax in axes:
        ax.plot([1, 2], [10, 100], label='Recorded samples')
        ax.set_yscale('log')
        ax.set_xlabel('Treatment visit\nwith a second label line', fontsize=8)
        ax.set_ylabel('DNA (ng/mL)', fontsize=14)
        ax.text(.1, .8, 'n=2', transform=ax.transAxes, fontsize=6)
        ax.legend(fontsize=7)
    fig.tight_layout()
    if exporter == 'shared':
        for suffix in ('png', 'pdf'):
            save_figure(fig, tmp_path/f'{exporter}.{suffix}')
    elif exporter == 'diagnostics':
        from analysis.association_methods import _save_figure
        _save_figure(fig, tmp_path/f'{exporter}.png')
    else:
        from analysis.disease_modeling.step_03_report import save
        save(fig, tmp_path/exporter)
    for text in fig.findobj(Text):
        assert text.get_fontfamily() == [FONT_FAMILY]
        assert text.get_fontsize() == FONT_SIZE
        assert findfont(text.get_fontproperties(), fallback_to_default=False) == findfont(FONT_FAMILY, fallback_to_default=False)
    renderer = fig.canvas.get_renderer()
    label_bottom = min(ax.xaxis.label.get_window_extent(renderer).y0 for ax in axes)
    legend_top = max(ax.get_legend().get_window_extent(renderer).y1 for ax in axes)
    assert (label_bottom-legend_top)*72/fig.dpi >= LEGEND_GAP_POINTS - .01
    if exporter != 'diagnostics':
        pdf = (tmp_path/f'{exporter}.pdf').read_bytes()
        assert pdf.startswith(b'%PDF')
        assert b'Arial' in pdf and b'/FontFile2' in pdf
    np.testing.assert_array_equal(axes[0].lines[0].get_ydata(), [10, 100])
    plt.close(fig)


def test_clean_export_preserves_observations_labels_legend_and_annotations(tmp_path):
    from analysis.utils.figure_layout import remove_plot_text
    from analysis.utils.plot_style import save_figure
    fig, ax = plt.subplots()
    ax.plot([1, 2], [3, 4], label='CIRCALL')
    ax.set(xlabel='Visit', ylabel='DNA (ng/mL)', title='Remove title')
    ax.set_title('Remove panel heading', loc='left')
    fig.suptitle('Remove overall title')
    fig.text(.5, .01, 'Remove descriptive footer')
    fig.supxlabel('Shared axis label')
    ax.text(.02, .98, 'n=2', transform=ax.transAxes)
    ax.legend()
    limits = (ax.get_xlim(), ax.get_ylim())
    remove_plot_text(fig)
    remove_plot_text(fig)
    fig.tight_layout()
    assert all(ax.get_title(loc=loc) == '' for loc in ('left', 'center', 'right'))
    assert [text.get_text() for text in fig.texts] == ['Shared axis label']
    assert ax.get_xlabel() == 'Visit' and ax.get_ylabel() == 'DNA (ng/mL)'
    assert [text.get_text() for text in ax.texts] == ['n=2']
    assert [text.get_text() for text in ax.get_legend().texts] == ['CIRCALL']
    np.testing.assert_array_equal(ax.lines[0].get_ydata(), [3, 4])
    assert (ax.get_xlim(), ax.get_ylim()) == limits
    for extension in ('png', 'pdf'):
        save_figure(fig, tmp_path/f'clean.{extension}')
        assert (tmp_path/f'clean.{extension}').stat().st_size > 1000
    plt.close(fig)


def test_legend_below_labels_and_notes_preserves_data_and_is_repeatable(tmp_path):
    fig,ax=plt.subplots(figsize=(7,5))
    x=np.array([1,2,3]); y=np.array([2,4,1])
    ax.plot(x,y,label='Recorded observations')
    ax.set_xticks(x,['Long visit label A','Long visit label B','Long visit label C'],rotation=35)
    ax.set_xlabel('Treatment phase with recorded patient counts')
    legend=ax.legend(loc='best')
    note=fig.text(.5,.02,'Explanatory note: no change in measurements',ha='center')
    fig.tight_layout(rect=(0,.1,1,1))
    limits=(ax.get_xlim(),ax.get_ylim())
    legends_below(fig)
    renderer=fig.canvas.get_renderer()
    bounds=legend.get_window_extent(renderer).bounds
    assert legend.get_window_extent(renderer).y1 < note.get_window_extent(renderer).y0
    assert legend.get_window_extent(renderer).y1 < ax.xaxis.label.get_window_extent(renderer).y0
    assert [t.get_text() for t in legend.get_texts()]==['Recorded observations']
    np.testing.assert_array_equal(ax.lines[0].get_ydata(),y)
    assert (ax.get_xlim(),ax.get_ylim())==limits
    legends_below(fig)
    np.testing.assert_allclose(legend.get_window_extent(fig.canvas.get_renderer()).bounds,bounds)
    assert fig.get_tightbbox(fig.canvas.get_renderer()).y0*fig.dpi <= bounds[1]
    fig.savefig(tmp_path/'preview.png',bbox_inches='tight')
    fig.savefig(tmp_path/'preview.pdf',bbox_inches='tight')
    assert (tmp_path/'preview.png').stat().st_size>1000
    assert (tmp_path/'preview.pdf').read_bytes().startswith(b'%PDF')
    plt.close(fig)


def test_panel_legends_are_stacked_below_all_panels():
    fig,axes=plt.subplots(1,2)
    for ax,label in zip(axes,['Retrospective','CIRCALL']):
        ax.plot([0,1],[1,2],label=label);ax.legend()
    fig.tight_layout(); legends_below(fig)
    renderer=fig.canvas.get_renderer()
    first,second=[ax.get_legend().get_window_extent(renderer) for ax in axes]
    assert second.y1 < first.y0
    assert first.y1 < min(ax.get_window_extent(renderer).y0 for ax in axes)
    plt.close(fig)
