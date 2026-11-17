"""Save disease figures using the established layout and export settings."""
from pathlib import Path

import matplotlib.pyplot as plt
from analysis.utils.figure_layout import remove_plot_text, legends_below


def save(fig, destination, pdf_output=True):
    from analysis.utils.plot_style import save_figure
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    remove_plot_text(fig)
    fig.tight_layout()
    legends_below(fig)
    try:
        for ext in (('png', 'pdf') if pdf_output else ('png',)):
            remove_plot_text(fig)
            save_figure(fig, destination.with_suffix('.'+ext), dpi=200)
    finally:
        plt.close(fig)

