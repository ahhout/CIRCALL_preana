"""Shared export layout: preserve plotted data and place legends below all content."""

FONT_FAMILY = 'Arial'
FONT_SIZE = 12
LEGEND_GAP_POINTS = 18


def prepare_figure(figure):
    """Apply consistent typography before measuring legend clearance."""
    from matplotlib.font_manager import findfont
    from matplotlib.text import Text
    # Require the requested font instead of silently substituting another family.
    findfont(FONT_FAMILY, fallback_to_default=False)
    remove_plot_text(figure)
    for text in figure.findobj(Text):
        # Arial lacks the Unicode superscript nine on supported Linux installs.
        text.set_text(text.get_text().replace('10⁹', r'10$^{9}$'))
        text.set_fontfamily(FONT_FAMILY)
        text.set_fontsize(FONT_SIZE)
        text.set_math_fontfamily('custom')
    legends_below(figure)


def remove_plot_text(figure):
    """Remove presentation titles/footnotes, retaining axes, legends and data labels."""
    for ax in figure.axes:
        for location in ('left', 'center', 'right'):
            ax.set_title('', loc=location)
    if figure._suptitle is not None:
        figure._suptitle.set_text('')
    axis_labels = (figure._supxlabel, figure._supylabel)
    for text in list(figure.texts):
        footers = getattr(figure, '_legend_footers', {}).values()
        if text not in axis_labels and text not in footers:
            text.remove()
    figure._suptitle = None


def legends_below(figure, *, gap_points=LEGEND_GAP_POINTS):
    """Place existing legends below axes, labels and notes; tight exports include them.

    Legends are stacked to avoid collisions in multi-panel figures. Existing labels,
    handles, fonts, titles and column counts are preserved. Repeated calls are safe.
    """
    legends = [ax.get_legend() for ax in figure.axes if ax.get_legend() is not None]
    legends += list(figure.legends)
    legends = [legend for legend in legends if legend.get_visible()]
    if not legends:
        return
    footers = getattr(figure, '_legend_footers', {})
    for footer in footers.values():
        footer.set_visible(False)
    for legend in legends:
        legend.set_visible(False)
    figure.canvas.draw()
    renderer = figure.canvas.get_renderer()
    boxes = [ax.get_tightbbox(renderer) for ax in figure.axes if ax.get_visible()]
    boxes += [label.get_window_extent(renderer) for label in figure.texts if label.get_visible()]
    bottom = min((box.y0 for box in boxes if box is not None), default=figure.bbox.y0)
    gap = gap_points * figure.dpi / 72
    for legend in legends:
        anchor = figure.transFigure.inverted().transform((figure.bbox.x0, bottom-gap))[1]
        legend.set_loc('upper center')
        legend.set_bbox_to_anchor((.5, anchor), transform=figure.transFigure)
        legend.borderaxespad = 0
        legend.set_in_layout(True)
        legend.set_visible(True)
        figure.canvas.draw()
        bottom = legend.get_window_extent(figure.canvas.get_renderer()).y0
        if legend in footers:
            footer = footers[legend]
            y = figure.transFigure.inverted().transform((figure.bbox.x0, bottom-6*figure.dpi/72))[1]
            footer.set_position((.5, y))
            footer.set_visible(True)
            figure.canvas.draw()
            bottom = footer.get_window_extent(figure.canvas.get_renderer()).y0


def legend_footer(figure, legend, text):
    """Attach an explicit explanatory line below one legend during every export."""
    footers = getattr(figure, '_legend_footers', {})
    if legend in footers:
        footers[legend].set_text(text)
    else:
        footers[legend] = figure.text(.5, 0, text, ha='center', va='top',
                                      fontfamily=FONT_FAMILY, fontsize=FONT_SIZE)
    figure._legend_footers = footers
    legends_below(figure)
    return footers[legend]
