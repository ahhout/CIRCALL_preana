"""Figure legends remain readable without covering data, axes labels, or notes."""
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

from analysis.figure_layout import legends_below


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
