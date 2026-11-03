from analysis.figure_layout import remove_plot_text
from analysis.figure_layout import legends_below
from pathlib import Path

import matplotlib.colors as mcolors
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
from matplotlib.ticker import FixedLocator, FuncFormatter
import numpy as np
import seaborn as sns

from analysis.blast_kinetics.statistics import bootstrap_daily_median_ci


class PlotError(ValueError):
    """Raised when configured plotting choices are incompatible with the data."""


def _time_points(config):
    time = config["time"]
    return np.arange(
        time["minimum"],
        time["maximum"] + time["tick_step"] / 2,
        time["tick_step"],
    )


def _palette(data, config):
    configured = dict(config["grouping"]["colors"])
    groups = sorted(data["group"].unique())
    missing = [group for group in groups if group not in configured]
    if missing:
        generated = sns.color_palette("tab10", len(missing))
        configured.update({
            group: mcolors.to_hex(color) for group, color in zip(missing, generated)
        })
    return {group: configured[group] for group in groups}


def _display_values(data, settings):
    values = data["analysis_value"].copy()
    if settings["y_scale"] == "log":
        if values.lt(0).any():
            raise PlotError("Log-scale plots cannot display negative analysis values")
        values = values.mask(values.eq(0), settings["detection_limit"])
    return values


def _format_label(value, config, subject_count):
    return value.format(
        measurement_name=config["measurement"]["name"],
        unit=config["measurement"]["unit"],
        n_subjects=subject_count,
        run_name=config["run"]["name"],
    )


def _apply_axes(ax, settings, time_points, config, subject_count):
    ax.set_yscale(settings["y_scale"])
    y_limits = settings.get("y_limits")
    if y_limits:
        ax.set_ylim(*y_limits)
    ax.set_xlim(time_points[0] - 0.5, time_points[-1] + 0.5)
    ax.set_xticks(time_points)
    ax.set_xlabel(
        _format_label(settings["x_label"], config, subject_count),
        fontsize=settings["label_fontsize"],
    )
    ax.set_ylabel(
        _format_label(settings["y_label"], config, subject_count),
        fontsize=settings["label_fontsize"],
    )
    ax.set_title(
        _format_label(settings["title"], config, subject_count),
        fontsize=settings["title_fontsize"],
    )
    custom_ticks = settings.get("y_ticks")
    if custom_ticks:
        values = custom_ticks["values"]
        labels = custom_ticks["labels"]
        label_map = dict(zip(values, labels))
        ax.yaxis.set_major_locator(FixedLocator(values))
        ax.yaxis.set_major_formatter(
            FuncFormatter(lambda value, _: label_map.get(value, ""))
        )


@plt.rc_context()
def plot_scatter(data, config, output_path):
    """Plot observed values by group with the daily median bootstrap interval."""
    settings = config["plots"]["scatter"]
    if not settings["enabled"]:
        return
    sns.set_style("whitegrid")
    figure, ax = plt.subplots(figsize=(settings["width"], settings["height"]))
    plot_data = data.copy()
    plot_data["display_value"] = _display_values(plot_data, settings)
    rng = np.random.default_rng(settings["jitter_seed"])
    plot_data["display_time"] = plot_data["time"] + rng.uniform(
        -settings["jitter"], settings["jitter"], len(plot_data)
    )
    palette = _palette(plot_data, config)
    counts = plot_data.groupby("group")["subject_id"].nunique()
    for group in sorted(plot_data["group"].unique()):
        subset = plot_data[plot_data["group"].eq(group)]
        ax.scatter(
            subset["display_time"],
            subset["display_value"],
            s=settings["marker_size"],
            alpha=settings["marker_alpha"],
            edgecolors=settings["marker_edge_color"],
            linewidths=settings["marker_edge_width"],
            color=palette[group],
            label=f"{group} (n={counts[group]})",
        )

    time_points = _time_points(config)
    lower, upper = bootstrap_daily_median_ci(data, time_points, config)
    if settings["y_scale"] == "log":
        lower = lower.clip(lower=settings["detection_limit"])
        upper = upper.clip(lower=settings["detection_limit"])
    confidence_label = f"{config['bootstrap']['confidence']:.0%} bootstrap CI of daily median"
    ax.fill_between(
        time_points,
        lower.to_numpy(),
        upper.to_numpy(),
        color=settings["ci_color"],
        alpha=settings["ci_alpha"],
        linewidth=0,
        label=confidence_label,
    )
    _apply_axes(
        ax, settings, time_points, config, int(plot_data["subject_id"].nunique())
    )
    ax.yaxis.grid(True, which="major", linestyle="--", alpha=0.4)
    ax.yaxis.grid(True, which="minor", linestyle=":", alpha=0.4)
    ax.set_axisbelow(True)
    ax.legend(
        title=settings["legend_title"],
        bbox_to_anchor=(1.02, 1),
        loc="upper left",
        fontsize=settings["legend_fontsize"],
    )
    remove_plot_text(figure)
    figure.tight_layout()
    legends_below(figure)
    figure.savefig(Path(output_path), dpi=settings["dpi"], facecolor="white", bbox_inches="tight")
    plt.close(figure)


@plt.rc_context()
def plot_model(trend, config, output_path):
    """Plot model input observations and the configured mixed-model trend."""
    settings = config["plots"]["model"]
    if not settings["enabled"]:
        return
    sns.set_style("whitegrid")
    figure, ax = plt.subplots(figsize=(settings["width"], settings["height"]))
    data = trend.frame.copy()
    data["display_value"] = _display_values(data, settings)
    rng = np.random.default_rng(settings["jitter_seed"])
    data["display_time"] = data["time"] + rng.normal(0, settings["jitter"], len(data))
    palette = _palette(data, config)
    counts = data.groupby("group")["subject_id"].nunique()
    for group in sorted(data["group"].unique()):
        subset = data[data["group"].eq(group)]
        ax.scatter(
            subset["display_time"],
            subset["display_value"],
            color=palette[group],
            alpha=settings["marker_alpha"],
            s=settings["marker_size"],
            edgecolors=settings["marker_edge_color"],
            linewidth=settings["marker_edge_width"],
        )
    ax.plot(
        trend.predictions["time"],
        trend.predictions["predicted"],
        color=settings["trend_color"],
        marker=settings["trend_marker"],
        markersize=settings["trend_marker_size"],
        label=settings["trend_label"],
    )
    time_points = _time_points(config)
    _apply_axes(ax, settings, time_points, config, int(data["subject_id"].nunique()))
    group_handles = [
        mpatches.Patch(color=palette[group], label=f"{group} (n={counts[group]})")
        for group in sorted(data["group"].unique())
    ]
    trend_handle = plt.Line2D(
        [0], [0],
        color=settings["trend_color"],
        marker=settings["trend_marker"],
        markersize=settings["trend_marker_size"],
        label=settings["trend_label"],
    )
    ax.legend(
        handles=group_handles + [trend_handle],
        bbox_to_anchor=(0.5, -0.2),
        loc="upper center",
        ncol=settings["legend_columns"],
        fontsize=settings["legend_fontsize"],
    )
    remove_plot_text(figure)
    figure.tight_layout()
    legends_below(figure)
    figure.savefig(Path(output_path), dpi=settings["dpi"], facecolor="white", bbox_inches="tight")
    plt.close(figure)
