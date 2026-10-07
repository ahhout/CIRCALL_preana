"""Shared export layout: preserve plotted data and place legends below all content."""


def legends_below(figure, *, gap_points=8):
    """Place existing legends below axes, labels and notes; tight exports include them.

    Legends are stacked to avoid collisions in multi-panel figures. Existing labels,
    handles, fonts, titles and column counts are preserved. Repeated calls are safe.
    """
    legends = [ax.get_legend() for ax in figure.axes if ax.get_legend() is not None]
    legends += list(figure.legends)
    legends = [legend for legend in legends if legend.get_visible()]
    if not legends:
        return
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
