#!/usr/bin/env python3
"""Analyse relationships among plasma volume, elution volume, and DNA dosage."""

from __future__ import annotations

import argparse
import math
import os
import zipfile
from pathlib import Path

from summarise_missing_samples import parse_rows, resolve_workbook, write_csv


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_RETROSPECTIVE_WORKBOOK = Path(
    "/home/arnohoutman/projects/cfDNA_inventory/outputs/results/cfdna_analysis.xlsx"
)
VARIABLES = {
    "volume": "Plasma volume (mL)",
    "elution_uL": "Elution volume (µL)",
    "dosage_ng/uL": "DNA dosage (ng/µL)",
    "dosage_ng_total": "Total DNA dosage (ng)",
    "dosage_ng/mL_plasma": "DNA per mL plasma (ng/mL)",
}
PAIRS = [
    ("volume", "dosage_ng/uL"),
    ("elution_uL", "dosage_ng/uL"),
    ("elution_uL", "dosage_ng/mL_plasma"),
    ("volume", "dosage_ng_total"),
    ("elution_uL", "dosage_ng_total"),
]
RETROSPECTIVE_PAIRS = [
    ("volume", "dosage_ng/uL"),
    ("volume", "dosage_ng_total"),
]
TIMEPOINT_ORDER = ["diag", "d4", "d8", "d15", "tp1", "tp2"]
TIMEPOINT_LABELS = {
    "diag": "Diag",
    "d4": "J4",
    "d8": "J8",
    "d15": "J15",
    "tp1": "TP1",
    "tp2": "TP2",
}
TIMEPOINT_COLORS = {
    "diag": "#4E79A7",
    "d4": "#F28E2B",
    "d8": "#59A14F",
    "d15": "#E15759",
    "tp1": "#B07AA1",
    "tp2": "#76B7B2",
}
RETROSPECTIVE_TIMEPOINT_ORDER = [
    "diag",
    "tp0,5",
    "tp1",
    "tp2",
    "tp1,5",
    "tp3",
]
RETROSPECTIVE_TIMEPOINT_LABELS = {
    "diag": "Diag",
    "tp0,5": "TP0.5",
    "tp1": "TP1",
    "tp2": "TP2",
    "tp1,5": "TP1.5",
    "tp3": "TP3",
}
RETROSPECTIVE_TIMEPOINT_COLORS = {
    "diag": TIMEPOINT_COLORS["diag"],
    "tp0,5": "#F28E2B",
    "tp1": TIMEPOINT_COLORS["tp1"],
    "tp2": TIMEPOINT_COLORS["tp2"],
    "tp1,5": "#59A14F",
    "tp3": "#E15759",
}
OUTPUT_FIELDS = [
    "variable_x",
    "variable_y",
    "correlation_scale",
    "timepoint",
    "paired_sample_count",
    "unique_patient_count",
    "pearson_r",
    "pearson_p_value",
    "spearman_rho",
    "spearman_p_value",
]


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Analyse pairwise correlations among plasma volume, elution volume, "
            "and DNA dosage for CIRCALL plasma samples."
        )
    )
    parser.add_argument(
        "workbook",
        type=Path,
        nargs="?",
        help="CIRCALL .xlsx file (defaults to the only local .xlsx file)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "output/plasma_volume_elution_dosage_correlations.csv",
        help="Output correlation CSV path",
    )
    parser.add_argument(
        "--plot-output-dir",
        type=Path,
        default=PROJECT_ROOT / "output",
        help="Directory for one PNG per correlation comparison",
    )
    parser.add_argument(
        "--retrospective-workbook",
        type=Path,
        default=DEFAULT_RETROSPECTIVE_WORKBOOK,
        help="Retrospective analysis workbook",
    )
    return parser.parse_args()


def numeric_value(raw_value: str) -> float | None:
    try:
        value = float(raw_value.strip().replace(",", "."))
    except ValueError:
        return None
    return value if value == value and abs(value) != float("inf") else None


def valid_for_plot_scale(variable_y: str, value: float) -> bool:
    if variable_y in {"dosage_ng/uL", "dosage_ng/mL_plasma"}:
        return value > 0
    if variable_y == "dosage_ng_total":
        return value >= 0
    return True


def transform_y(variable_y: str, values: list[float]) -> list[float]:
    if variable_y in {"dosage_ng/uL", "dosage_ng/mL_plasma"}:
        return [math.log10(value) for value in values]
    if variable_y == "dosage_ng_total":
        return [math.log10(1.0 + value) for value in values]
    return values


def correlation_scale(variable_y: str) -> str:
    if variable_y in {"dosage_ng/uL", "dosage_ng/mL_plasma"}:
        return "X raw; Y log10"
    if variable_y == "dosage_ng_total":
        return "X raw; Y log10(1+Y)"
    return "X raw; Y raw"



def qualifying_records(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    columns = {name.strip(): column for column, name in rows[0].items()}
    required = {"circall_id", "sample_id", "timepoint", "compartment", *VARIABLES}
    missing_columns = required - columns.keys()
    if missing_columns:
        raise SystemExit(f"Missing columns: {', '.join(sorted(missing_columns))}")

    records = []
    for row in rows[1:]:
        sample_id = row.get(columns["sample_id"], "").replace("\u00a0", "").strip()
        timepoint = row.get(columns["timepoint"], "").strip().casefold()
        compartment = row.get(columns["compartment"], "").strip()
        if (
            not sample_id
            or sample_id.casefold() == "na"
            or not timepoint
            or compartment.casefold() != "plasma"
        ):
            continue

        record: dict[str, object] = {
            "circall_id": row.get(columns["circall_id"], "")
            .replace("\u00a0", "")
            .strip(),
            "timepoint": timepoint,
        }
        for variable in VARIABLES:
            record[variable] = numeric_value(row.get(columns[variable], ""))
        records.append(record)
    return records


def retrospective_records(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    columns = {name.strip(): column for column, name in rows[0].items()}
    required = {
        "patient_key",
        "sample_id",
        "timepoint",
        "ml_plasma",
        "dosage_ng_per_uL",
        "total_ng_dna",
    }
    missing_columns = required - columns.keys()
    if missing_columns:
        raise SystemExit(
            f"Missing retrospective columns: {', '.join(sorted(missing_columns))}"
        )

    records = []
    for row in rows[1:]:
        sample_id = row.get(columns["sample_id"], "").strip()
        timepoint = row.get(columns["timepoint"], "").strip().casefold()
        if (
            not sample_id
            or sample_id.casefold() == "na"
            or not timepoint
            or timepoint == "après inotuzumab"
        ):
            continue
        records.append(
            {
                "circall_id": row.get(columns["patient_key"], "").strip(),
                "timepoint": timepoint,
                "volume": numeric_value(row.get(columns["ml_plasma"], "")),
                "dosage_ng/uL": numeric_value(
                    row.get(columns["dosage_ng_per_uL"], "")
                ),
                "dosage_ng_total": numeric_value(
                    row.get(columns["total_ng_dna"], "")
                ),
            }
        )
    return records


def paired_values(
    records: list[dict[str, object]], variable_x: str, variable_y: str
) -> tuple[list[float], list[float], list[str], set[str]]:
    x_values = []
    y_values = []
    timepoints = []
    patients = set()
    for record in records:
        x_value = record[variable_x]
        y_value = record[variable_y]
        if x_value is None or y_value is None:
            continue
        numeric_y = float(y_value)
        if not valid_for_plot_scale(variable_y, numeric_y):
            continue
        x_values.append(float(x_value))
        y_values.append(numeric_y)
        timepoints.append(str(record["timepoint"]))
        patients.add(str(record["circall_id"]))
    return x_values, y_values, timepoints, patients


def format_statistic(value: float) -> str:
    return f"{value:.2f}"


def calculate_correlations(
    records: list[dict[str, object]],
    pairs: list[tuple[str, str]] = PAIRS,
    timepoint_order: list[str] = TIMEPOINT_ORDER,
    timepoint_labels: dict[str, str] = TIMEPOINT_LABELS,
) -> tuple[
    list[dict[str, object]],
    dict[tuple[str, str], tuple[list[float], list[float], list[str]]],
]:
    try:
        from scipy.stats import pearsonr, spearmanr
    except ImportError as exc:
        raise SystemExit("Correlation analysis requires scipy.") from exc

    output_rows = []
    plot_values = {}
    for variable_x, variable_y in pairs:
        x_values, y_values, timepoints, patients = paired_values(
            records, variable_x, variable_y
        )
        if len(x_values) < 3:
            raise SystemExit(
                f"Too few paired numeric observations for {variable_x} vs {variable_y}"
            )
        groups = [("Overall", x_values, y_values, timepoints, patients)]
        for timepoint in timepoint_order:
            selected = [
                index for index, value in enumerate(timepoints) if value == timepoint
            ]
            if len(selected) < 5:
                continue
            group_x = [x_values[index] for index in selected]
            group_y = [y_values[index] for index in selected]
            group_patients = {
                str(record["circall_id"])
                for record in records
                if record["timepoint"] == timepoint
                and record[variable_x] is not None
                and record[variable_y] is not None
                and valid_for_plot_scale(variable_y, float(record[variable_y]))
            }
            groups.append(
                (
                    timepoint_labels[timepoint],
                    group_x,
                    group_y,
                    [timepoint] * len(selected),
                    group_patients,
                )
            )

        for group_name, group_x, group_y, _group_timepoints, group_patients in groups:
            transformed_y = transform_y(variable_y, group_y)
            pearson = pearsonr(group_x, transformed_y)
            spearman = spearmanr(group_x, transformed_y)
            output_rows.append(
                {
                    "variable_x": variable_x,
                    "variable_y": variable_y,
                    "correlation_scale": correlation_scale(variable_y),
                    "timepoint": group_name,
                    "paired_sample_count": len(group_x),
                    "unique_patient_count": len(group_patients),
                    "pearson_r": format_statistic(float(pearson.statistic)),
                    "pearson_p_value": format_statistic(float(pearson.pvalue)),
                    "spearman_rho": format_statistic(float(spearman.statistic)),
                    "spearman_p_value": format_statistic(float(spearman.pvalue)),
                }
            )
        plot_values[(variable_x, variable_y)] = (x_values, y_values, timepoints)
    return output_rows, plot_values


def write_scatterplot(
    path: Path,
    correlation_rows: list[dict[str, object]],
    plot_values: dict[tuple[str, str], tuple[list[float], list[float], list[str]]],
    pairs: list[tuple[str, str]] = PAIRS,
    timepoint_order: list[str] = TIMEPOINT_ORDER,
    timepoint_labels: dict[str, str] = TIMEPOINT_LABELS,
    timepoint_colors: dict[str, str] = TIMEPOINT_COLORS,
    title: str = "CIRCALL plasma measurements: pairwise relationships",
    concentration_min_tick: float = 0.01,
    x_limits: dict[str, tuple[float, float]] | None = None,
) -> None:
    cache_root = Path("/tmp/bilan_plot_cache")
    cache_root.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str(cache_root / "matplotlib"))
    os.environ.setdefault("XDG_CACHE_HOME", str(cache_root))
    try:
        import matplotlib.pyplot as plt
        import numpy as np
        from matplotlib.lines import Line2D
    except ImportError as exc:
        raise SystemExit(
            "Plotting requires matplotlib. Run this script with the "
            "cfDNA_inventory conda environment."
        ) from exc

    plot_columns = min(2, len(pairs))
    plot_rows = (len(pairs) + plot_columns - 1) // plot_columns
    figure = plt.figure(figsize=(7 * plot_columns, 6 * plot_rows))
    grid = figure.add_gridspec(
        plot_rows * 2,
        plot_columns,
        height_ratios=[4, 1.05] * plot_rows,
        hspace=0.55,
        wspace=0.25,
        top=0.80,
        bottom=0.05,
    )
    axes = []
    table_axes = []
    for index in range(len(pairs)):
        plot_row = (index // 2) * 2
        column = index % plot_columns
        axes.append(figure.add_subplot(grid[plot_row, column]))
        table_axes.append(figure.add_subplot(grid[plot_row + 1, column]))
    for axis, table_axis, (variable_x, variable_y) in zip(
        axes, table_axes, pairs
    ):
        x_values, y_values, timepoints = plot_values[(variable_x, variable_y)]
        x_array = np.asarray(x_values, dtype=float)
        y_array = np.asarray(y_values, dtype=float)
        timepoint_array = np.asarray(timepoints)
        dosage_axis = variable_y in {"dosage_ng/uL", "dosage_ng_total", "dosage_ng/mL_plasma"}
        if variable_y in {"dosage_ng/uL", "dosage_ng/mL_plasma"}:
            displayed_y = np.asarray(transform_y(variable_y, y_values), dtype=float)
            scale_label = "log scale"
        elif variable_y == "dosage_ng_total":
            displayed_y = np.asarray(transform_y(variable_y, y_values), dtype=float)
            scale_label = "log1p scale"
        else:
            displayed_y = y_array
            scale_label = ""
        for timepoint in timepoint_order:
            selected = timepoint_array == timepoint
            axis.scatter(
                x_array[selected],
                displayed_y[selected],
                color=timepoint_colors[timepoint],
                s=24,
                alpha=0.78,
                linewidths=0,
            )
            if selected.sum() >= 5 and np.unique(x_array[selected]).size >= 2:
                group_slope, group_intercept = np.polyfit(
                    x_array[selected], displayed_y[selected], 1
                )
                group_x_line = np.linspace(
                    x_array[selected].min(), x_array[selected].max(), 100
                )
                axis.plot(
                    group_x_line,
                    group_slope * group_x_line + group_intercept,
                    color=timepoint_colors[timepoint],
                    linewidth=1.6,
                    alpha=0.9,
                    zorder=3,
                )
        if dosage_axis:
            slope, intercept = np.polyfit(x_array, displayed_y, 1)
            x_line = np.linspace(x_array.min(), x_array.max(), 200)
            y_line = slope * x_line + intercept
            axis.plot(
                x_line,
                y_line,
                color="#333333",
                linewidth=2,
                zorder=4,
            )
            if variable_y in {"dosage_ng/uL", "dosage_ng/mL_plasma"}:
                tick_values = [
                    value
                    for value in [0.01, 0.1, 1, 10, 100, 300]
                    if value >= concentration_min_tick
                ]
                tick_positions = [np.log10(value) for value in tick_values]
                lower_limit = min(
                    np.log10(tick_values[0]) - 0.08,
                    float(displayed_y.min()) - 0.05,
                )
            else:
                tick_values = [0, 1, 10, 100, 1_000, 10_000, 100_000]
                tick_positions = [np.log10(1.0 + value) for value in tick_values]
                lower_limit = -0.08
            upper_tick = tick_values[-1]
            axis.set_yticks(
                tick_positions,
                [f"{value:g}" for value in tick_values],
            )
            upper_limit = (
                np.log10(upper_tick)
                if variable_y in {"dosage_ng/uL", "dosage_ng/mL_plasma"}
                else np.log10(1.0 + upper_tick)
            )
            axis.set_ylim(lower_limit, upper_limit * 1.02)
        axis.set_xlabel(VARIABLES[variable_x])
        if x_limits and variable_x in x_limits:
            axis.set_xlim(*x_limits[variable_x])
        axis.set_ylabel(
            f"{VARIABLES[variable_y]} ({scale_label})"
            if dosage_axis
            else VARIABLES[variable_y]
        )
        axis.grid(True, which="both", linestyle="--", alpha=0.3)
        axis.spines["top"].set_visible(False)
        axis.spines["right"].set_visible(False)

        table_results = [
            row
            for row in correlation_rows
            if row["variable_x"] == variable_x
            and row["variable_y"] == variable_y
        ]
        column_labels = ["Statistic"] + [
            str(row["timepoint"]) for row in table_results
        ]
        table_data = [
            ["Pearson r"] + [str(row["pearson_r"]) for row in table_results],
            ["p-value"]
            + [str(row["pearson_p_value"]) for row in table_results],
        ]
        table_axis.axis("off")
        table_axis.set_title(
            "Pearson correlations on plotted scale (timepoints require n ≥ 5)",
            fontsize=9,
            pad=3,
        )
        result_table = table_axis.table(
            cellText=table_data,
            colLabels=column_labels,
            cellLoc="center",
            loc="center",
            bbox=[0, 0.05, 1, 0.82],
        )
        result_table.auto_set_font_size(False)
        result_table.set_fontsize(8)
        for column, row in enumerate(table_results, start=1):
            label = str(row["timepoint"])
            header_color = "#333333"
            if label != "Overall":
                normalized = next(
                    key for key, display in timepoint_labels.items() if display == label
                )
                header_color = timepoint_colors[normalized]
            result_table[(0, column)].set_facecolor(header_color)
            result_table[(0, column)].get_text().set_color("white")

    eligible_labels = {
        str(row["timepoint"])
        for row in correlation_rows
        if row["timepoint"] != "Overall"
    }
    legend_handles = [
        Line2D(
            [0],
            [0],
            marker="o",
            linestyle=("-" if timepoint_labels[timepoint] in eligible_labels else ""),
            color=timepoint_colors[timepoint],
            label=timepoint_labels[timepoint],
            markersize=6,
        )
        for timepoint in timepoint_order
    ]
    legend_handles.append(
        Line2D([0], [0], color="#333333", linewidth=2, label="Overall best fit")
    )
    figure.suptitle(title, fontsize=14)
    figure.legend(
        handles=legend_handles,
        loc="upper center",
        bbox_to_anchor=(0.5, 0.91),
        ncol=min(len(legend_handles), 4 if plot_columns == 1 else 8),
        frameon=False,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=600, bbox_inches="tight")
    plt.close(figure)


def comparison_plot_path(
    output_dir: Path, cohort: str, variable_x: str, variable_y: str
) -> Path:
    slugs = {
        "volume": "plasma_volume",
        "elution_uL": "elution_volume",
        "dosage_ng/uL": "dosage_ng_per_uL",
        "dosage_ng_total": "dosage_ng_total",
        "dosage_ng/mL_plasma": "dosage_ng_per_mL_plasma",
    }
    return output_dir / f"{cohort}_{slugs[variable_x]}_vs_{slugs[variable_y]}.png"


def main() -> None:
    args = arguments()
    workbook = resolve_workbook(args.workbook)
    if not args.retrospective_workbook.is_file():
        raise SystemExit(
            f"Retrospective workbook not found: {args.retrospective_workbook}"
        )
    with zipfile.ZipFile(workbook) as archive:
        rows = parse_rows(archive, "cohorte_lal")
    with zipfile.ZipFile(args.retrospective_workbook) as archive:
        retrospective_rows = parse_rows(archive, "Detailed")

    records = qualifying_records(rows)
    correlation_rows, plot_values = calculate_correlations(records)
    write_csv(args.output, OUTPUT_FIELDS, correlation_rows)
    plot_paths = []
    for variable_x, variable_y in PAIRS:
        plot_path = comparison_plot_path(
            args.plot_output_dir, "circall", variable_x, variable_y
        )
        write_scatterplot(
            plot_path,
            correlation_rows,
            plot_values,
            pairs=[(variable_x, variable_y)],
            title=f"CIRCALL: {VARIABLES[variable_x]} vs {VARIABLES[variable_y]}",
            x_limits={"volume": (1, 11)},
        )
        plot_paths.append(plot_path)

    retrospective = retrospective_records(retrospective_rows)
    retrospective_correlations, retrospective_plot_values = calculate_correlations(
        retrospective,
        pairs=RETROSPECTIVE_PAIRS,
        timepoint_order=RETROSPECTIVE_TIMEPOINT_ORDER,
        timepoint_labels=RETROSPECTIVE_TIMEPOINT_LABELS,
    )
    for variable_x, variable_y in RETROSPECTIVE_PAIRS:
        plot_path = comparison_plot_path(
            args.plot_output_dir, "retrospective", variable_x, variable_y
        )
        write_scatterplot(
            plot_path,
            retrospective_correlations,
            retrospective_plot_values,
            pairs=[(variable_x, variable_y)],
            timepoint_order=RETROSPECTIVE_TIMEPOINT_ORDER,
            timepoint_labels=RETROSPECTIVE_TIMEPOINT_LABELS,
            timepoint_colors=RETROSPECTIVE_TIMEPOINT_COLORS,
            title=(
                f"Retrospective cohort: {VARIABLES[variable_x]} "
                f"vs {VARIABLES[variable_y]}"
            ),
            concentration_min_tick=0.1,
            x_limits={"volume": (1, 11)},
        )
        plot_paths.append(plot_path)
    print(f"Qualifying CIRCALL plasma samples: {len(records)}")
    print(f"Correlation result rows: {len(correlation_rows)}")
    print(f"Wrote: {args.output}")
    print(f"Qualifying retrospective samples: {len(retrospective)}")
    for plot_path in plot_paths:
        print(f"Wrote: {plot_path}")


if __name__ == "__main__":
    main()
