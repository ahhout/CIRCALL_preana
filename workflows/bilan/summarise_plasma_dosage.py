#!/usr/bin/env python3
"""Compare plasma DNA concentration and plot both cohorts by timepoint."""

from __future__ import annotations

import argparse
import os
import statistics
import zipfile
from collections import defaultdict
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from pathlib import Path

from summarise_missing_samples import parse_arguments, parse_rows, resolve_workbook, write_csv


PROJECT_ROOT = Path(__file__).resolve().parents[2]
THREE_DECIMALS = Decimal("0.001")
DEFAULT_RETROSPECTIVE_WORKBOOK = (PROJECT_ROOT / "outputs/manual/retrospective/results/cfdna_analysis.xlsx")
OUTPUT_FIELDS = [
    "timepoint",
    "comparison_status",
    "circall_sample_count",
    "circall_invalid_count",
    "circall_mean_ng_per_mL",
    "circall_median_ng_per_mL",
    "retrospective_sample_count",
    "retrospective_invalid_count",
    "retrospective_mean_ng_per_mL",
    "retrospective_median_ng_per_mL",
    "mean_difference_ng_per_mL",
    "mean_ratio_circall_to_retrospective",
    "mean_percent_difference",
]
PLOT_TIMEPOINTS = ["diag", "d4", "d8", "d15", "tp1", "tp2"]
PLOT_LABELS = ["Diag", "J4", "J8", "J15", "TP1", "TP2"]
CIRCALL_COLOR = "#F4A6A6"
RETROSPECTIVE_COLOR = "#A7C7E7"
COMBINED_COLOR = "#C3B1E1"


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Compare CIRCALL and retrospective plasma dosage by timepoint."
    )
    parser.add_argument(
        "circall_workbook",
        type=Path,
        nargs="?",
        help="CIRCALL .xlsx file (defaults to the only .xlsx file in data/circall)",
    )
    parser.add_argument(
        "--retrospective-workbook",
        type=Path,
        default=DEFAULT_RETROSPECTIVE_WORKBOOK,
        help="Retrospective analysis workbook",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "outputs/manual/bilan/plasma_dosage_circall_vs_retrospective.csv",
        help="Output comparison CSV path",
    )
    parser.add_argument(
        "--plot-output",
        type=Path,
        default=PROJECT_ROOT / "outputs/manual/bilan/plasma_dosage_violin.png",
        help="Output paired violin plot path",
    )
    return parse_arguments(parser)


def normalized_timepoint(value: str) -> str:
    return value.replace("\u00a0", " ").strip().casefold()


def decimal_value(raw_value: str) -> Decimal | None:
    cleaned = raw_value.strip().replace(",", ".")
    try:
        value = Decimal(cleaned)
    except InvalidOperation:
        return None
    return value if value.is_finite() else None


def format_decimal(value: Decimal) -> str:
    return format(value.quantize(THREE_DECIMALS, rounding=ROUND_HALF_UP), "f")


def cohort_values(
    rows: list[dict[str, str]],
    dosage_column: str,
    require_plasma: bool,
) -> tuple[dict[str, list[Decimal]], dict[str, int], dict[str, str]]:
    columns = {name.strip(): column for column, name in rows[0].items()}
    required = {"sample_id", "timepoint", dosage_column}
    if require_plasma:
        required.add("compartment")
    missing_columns = required - columns.keys()
    if missing_columns:
        raise SystemExit(f"Missing columns: {', '.join(sorted(missing_columns))}")

    values: dict[str, list[Decimal]] = defaultdict(list)
    invalid_counts: dict[str, int] = defaultdict(int)
    labels: dict[str, str] = {}
    for row in rows[1:]:
        sample_id = row.get(columns["sample_id"], "").replace("\u00a0", "").strip()
        timepoint = row.get(columns["timepoint"], "").strip()
        if not sample_id or sample_id.casefold() == "na" or not timepoint:
            continue
        if require_plasma:
            compartment = row.get(columns["compartment"], "").strip()
            if compartment.casefold() != "plasma":
                continue

        key = normalized_timepoint(timepoint)
        labels.setdefault(key, timepoint)
        dosage = decimal_value(row.get(columns[dosage_column], ""))
        if dosage is None:
            invalid_counts[key] += 1
        else:
            values[key].append(dosage)

    return values, invalid_counts, labels


def metrics(values: list[Decimal]) -> tuple[Decimal, Decimal, Decimal]:
    total = sum(values, Decimal())
    return total, total / len(values), statistics.median(values)


def write_violin_plot(
    path: Path,
    circall: dict[str, list[Decimal]],
    retrospective: dict[str, list[Decimal]],
) -> None:
    cache_root = Path("/tmp/bilan_plot_cache")
    cache_root.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str(cache_root / "matplotlib"))
    os.environ.setdefault("XDG_CACHE_HOME", str(cache_root))
    try:
        import matplotlib.pyplot as plt
        import numpy as np
        from matplotlib.patches import Patch
    except ImportError as exc:
        raise SystemExit(
            "Plotting requires matplotlib and numpy. Run this script with the "
            "pre_analysis conda environment."
        ) from exc

    # The reference project estimates densities in transformed space. log10(1+x)
    # retains the two valid zero measurements in CIRCALL while compressing outliers.
    def transformed(values: list[Decimal]) -> np.ndarray:
        numeric = np.asarray([float(value) for value in values], dtype=float)
        return np.log10(1.0 + numeric)

    figure, axis = plt.subplots(figsize=(10, 6))
    base_positions = np.arange(len(PLOT_TIMEPOINTS), dtype=float)
    combined = {
        key: circall.get(key, []) + retrospective.get(key, [])
        for key in PLOT_TIMEPOINTS
        if circall.get(key) and retrospective.get(key)
    }
    cohort_specs = [
        (circall, base_positions - 0.25, CIRCALL_COLOR, "CIRCALL"),
        (
            retrospective,
            base_positions,
            RETROSPECTIVE_COLOR,
            "Retrospective cohort",
        ),
        (combined, base_positions + 0.25, COMBINED_COLOR, "Combined"),
    ]
    rng = np.random.default_rng(42)
    all_values: list[float] = []

    for cohort, positions, color, _label in cohort_specs:
        violin_data = []
        violin_positions = []
        for key, position in zip(PLOT_TIMEPOINTS, positions):
            values = cohort.get(key, [])
            all_values.extend(float(value) for value in values)
            if len(values) >= 2:
                violin_data.append(transformed(values))
                violin_positions.append(position)

        if violin_data:
            parts = axis.violinplot(
                violin_data,
                positions=violin_positions,
                widths=0.22,
                showmeans=False,
                showmedians=True,
                showextrema=False,
            )
            for body in parts["bodies"]:
                body.set_facecolor(color)
                body.set_edgecolor(color)
                body.set_alpha(0.8)
                body.set_linewidth(1.0)
            parts["cmedians"].set_color("black")
            parts["cmedians"].set_linewidth(1.2)

        for key, position in zip(PLOT_TIMEPOINTS, positions):
            values = cohort.get(key, [])
            if not values:
                continue
            y_values = transformed(values)
            x_values = position + rng.uniform(-0.055, 0.055, size=len(values))
            axis.scatter(
                x_values,
                y_values,
                color="black",
                s=15,
                alpha=0.72,
                linewidths=0,
                zorder=5,
            )

    max_value = max(all_values, default=1.0)
    tick_candidates = [0, 1, 3, 10, 30, 100, 300, 1_000, 3_000, 10_000]
    tick_values = [value for value in tick_candidates if value <= max_value * 1.2]
    if tick_values[-1] < max_value:
        tick_values.append(10 ** len(str(int(max_value))))
    axis.set_yticks(
        [np.log10(1.0 + value) for value in tick_values],
        [f"{value:,}" for value in tick_values],
    )
    axis.set_ylim(-0.08, np.log10(1.0 + max(tick_values)) * 1.03)
    axis.set_xticks(base_positions, PLOT_LABELS)
    axis.set_xlabel("Timepoint")
    axis.set_ylabel("ng/mL plasma (log1p scale)")
    axis.set_title("Plasma DNA concentration by cohort and timepoint")
    axis.grid(True, which="major", axis="y", linestyle="--", alpha=0.35)
    axis.spines["top"].set_visible(False)
    axis.spines["right"].set_visible(False)
    axis.legend(
        handles=[
            Patch(facecolor=CIRCALL_COLOR, label="CIRCALL"),
            Patch(facecolor=RETROSPECTIVE_COLOR, label="Retrospective cohort"),
            Patch(facecolor=COMBINED_COLOR, label="Combined"),
        ],
        frameon=False,
    )
    figure.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=600, bbox_inches="tight")
    plt.close(figure)


def main() -> None:
    args = arguments()
    circall_workbook = resolve_workbook(args.circall_workbook)
    if not args.retrospective_workbook.is_file():
        raise SystemExit(
            f"Retrospective workbook not found: {args.retrospective_workbook}"
        )

    with zipfile.ZipFile(circall_workbook) as archive:
        circall_rows = parse_rows(archive, "cohorte_lal")
    with zipfile.ZipFile(args.retrospective_workbook) as archive:
        retrospective_rows = parse_rows(archive, "Detailed")

    circall, circall_invalid, circall_labels = cohort_values(
        circall_rows, "dosage_ng/mL_plasma", require_plasma=True
    )
    retrospective, retrospective_invalid, retrospective_labels = cohort_values(
        retrospective_rows, "ng_per_ml", require_plasma=False
    )

    ordered_timepoints = list(circall_labels)
    ordered_timepoints.extend(
        key for key in retrospective_labels if key not in circall_labels
    )
    output_rows = []
    matched_count = 0
    for key in ordered_timepoints:
        circall_values = circall.get(key, [])
        retrospective_values = retrospective.get(key, [])
        has_circall = bool(circall_values) or bool(circall_invalid.get(key))
        has_retrospective = bool(retrospective_values) or bool(
            retrospective_invalid.get(key)
        )
        if has_circall and has_retrospective:
            status = "matched"
            matched_count += 1
        elif has_circall:
            status = "CIRCALL only"
        else:
            status = "retrospective only"

        circall_stats = metrics(circall_values) if circall_values else None
        retrospective_stats = (
            metrics(retrospective_values) if retrospective_values else None
        )
        mean_difference = mean_ratio = mean_percent_difference = None
        if circall_stats and retrospective_stats:
            mean_difference = circall_stats[1] - retrospective_stats[1]
            if retrospective_stats[1] != 0:
                mean_ratio = circall_stats[1] / retrospective_stats[1]
                mean_percent_difference = (mean_ratio - 1) * 100

        output_rows.append(
            {
                "timepoint": circall_labels.get(key, retrospective_labels.get(key, key)),
                "comparison_status": status,
                "circall_sample_count": len(circall_values),
                "circall_invalid_count": circall_invalid.get(key, 0),
                "circall_mean_ng_per_mL": (
                    format_decimal(circall_stats[1]) if circall_stats else ""
                ),
                "circall_median_ng_per_mL": (
                    format_decimal(circall_stats[2]) if circall_stats else ""
                ),
                "retrospective_sample_count": len(retrospective_values),
                "retrospective_invalid_count": retrospective_invalid.get(key, 0),
                "retrospective_mean_ng_per_mL": (
                    format_decimal(retrospective_stats[1])
                    if retrospective_stats
                    else ""
                ),
                "retrospective_median_ng_per_mL": (
                    format_decimal(retrospective_stats[2])
                    if retrospective_stats
                    else ""
                ),
                "mean_difference_ng_per_mL": (
                    format_decimal(mean_difference)
                    if mean_difference is not None
                    else ""
                ),
                "mean_ratio_circall_to_retrospective": (
                    format_decimal(mean_ratio) if mean_ratio is not None else ""
                ),
                "mean_percent_difference": (
                    format_decimal(mean_percent_difference)
                    if mean_percent_difference is not None
                    else ""
                ),
            }
        )

    write_csv(args.output, OUTPUT_FIELDS, output_rows)
    write_violin_plot(args.plot_output, circall, retrospective)
    print(f"Matched timepoints: {matched_count}")
    print(f"Total timepoints reported: {len(output_rows)}")
    print(f"Wrote: {args.output}")
    print(f"Wrote: {args.plot_output}")


if __name__ == "__main__":
    main()
