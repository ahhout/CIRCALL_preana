#!/usr/bin/env python3
"""Summarise and plot CIRCALL CSF sample volumes."""

from __future__ import annotations

import argparse
import os
import statistics
import zipfile
from collections import Counter
from pathlib import Path

from summarise_missing_samples import parse_rows, resolve_workbook, write_csv


PROJECT_ROOT = Path(__file__).resolve().parent
OUTPUT_FIELDS = [
    "compartment",
    "csf_row_count",
    "numeric_volume_count",
    "blank_volume_count",
    "non_numeric_volume_count",
    "unique_patient_count",
    "total_volume_ml",
    "mean_volume_ml",
    "standard_deviation_ml",
    "minimum_volume_ml",
    "q1_volume_ml",
    "median_volume_ml",
    "q3_volume_ml",
    "maximum_volume_ml",
]


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Summarise and plot numeric CSF volumes from the CIRCALL workbook."
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
        default=PROJECT_ROOT / "output/csf_volume_summary.csv",
        help="Output summary CSV path",
    )
    parser.add_argument(
        "--plot-output",
        type=Path,
        default=PROJECT_ROOT / "output/csf_volume_violin.png",
        help="Output violin plot path",
    )
    return parser.parse_args()


def numeric_value(raw_value: str) -> float | None:
    try:
        value = float(raw_value.strip().replace(",", "."))
    except ValueError:
        return None
    return value if value == value and abs(value) != float("inf") else None


def extract_csf_volumes(
    rows: list[dict[str, str]],
) -> tuple[list[float], set[str], int, Counter[str]]:
    columns = {name.strip(): column for column, name in rows[0].items()}
    required = {"circall_id", "compartment", "volume"}
    missing_columns = required - columns.keys()
    if missing_columns:
        raise SystemExit(f"Missing columns: {', '.join(sorted(missing_columns))}")

    values = []
    patients = set()
    raw_invalid_values: Counter[str] = Counter()
    csf_row_count = 0
    for row in rows[1:]:
        compartment = row.get(columns["compartment"], "").strip()
        if compartment.casefold() != "csf":
            continue
        csf_row_count += 1
        raw_volume = row.get(columns["volume"], "").strip()
        volume = numeric_value(raw_volume)
        if volume is None:
            raw_invalid_values[raw_volume.casefold()] += 1
            continue
        values.append(volume)
        patient = row.get(columns["circall_id"], "").replace("\u00a0", "").strip()
        if patient:
            patients.add(patient)
    return values, patients, csf_row_count, raw_invalid_values


def format_value(value: float) -> str:
    return f"{value:.3f}"


def summary_row(
    values: list[float],
    patients: set[str],
    csf_row_count: int,
    invalid_values: Counter[str],
) -> dict[str, object]:
    if not values:
        raise SystemExit("No numeric CSF volumes found")
    q1, _q2, q3 = statistics.quantiles(values, n=4, method="inclusive")
    blank_count = invalid_values.get("", 0)
    non_numeric_count = sum(invalid_values.values()) - blank_count
    return {
        "compartment": "CSF",
        "csf_row_count": csf_row_count,
        "numeric_volume_count": len(values),
        "blank_volume_count": blank_count,
        "non_numeric_volume_count": non_numeric_count,
        "unique_patient_count": len(patients),
        "total_volume_ml": format_value(sum(values)),
        "mean_volume_ml": format_value(statistics.mean(values)),
        "standard_deviation_ml": format_value(statistics.stdev(values)),
        "minimum_volume_ml": format_value(min(values)),
        "q1_volume_ml": format_value(q1),
        "median_volume_ml": format_value(statistics.median(values)),
        "q3_volume_ml": format_value(q3),
        "maximum_volume_ml": format_value(max(values)),
    }


def write_violin_plot(path: Path, values: list[float]) -> None:
    cache_root = Path("/tmp/bilan_plot_cache")
    cache_root.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("MPLCONFIGDIR", str(cache_root / "matplotlib"))
    os.environ.setdefault("XDG_CACHE_HOME", str(cache_root))
    try:
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError as exc:
        raise SystemExit(
            "Plotting requires matplotlib and numpy. Run this script with the "
            "cfDNA_inventory conda environment."
        ) from exc

    numeric = np.asarray(values, dtype=float)
    figure, axis = plt.subplots(figsize=(5.5, 6))
    parts = axis.violinplot(
        [numeric],
        positions=[0],
        widths=0.7,
        showmeans=False,
        showmedians=False,
        showextrema=False,
    )
    for body in parts["bodies"]:
        body.set_facecolor("#A7C7E7")
        body.set_edgecolor("#6E9CC7")
        body.set_alpha(0.85)
        body.set_linewidth(1.1)

    q1, median, q3 = np.percentile(numeric, [25, 50, 75])
    axis.vlines(0, q1, q3, color="black", linewidth=2, zorder=4)
    axis.hlines(median, -0.16, 0.16, color="black", linewidth=2, zorder=5)
    rng = np.random.default_rng(42)
    x_values = rng.uniform(-0.09, 0.09, size=numeric.size)
    axis.scatter(
        x_values,
        numeric,
        color="black",
        s=22,
        alpha=0.75,
        linewidths=0,
        zorder=6,
    )
    axis.set_xticks([0], [f"CSF (n={len(values)})"])
    axis.set_ylabel("CSF volume (mL)")
    axis.set_title("CIRCALL CSF volume distribution")
    axis.grid(True, axis="y", linestyle="--", alpha=0.35)
    axis.spines["top"].set_visible(False)
    axis.spines["right"].set_visible(False)
    figure.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, dpi=600, bbox_inches="tight")
    plt.close(figure)


def main() -> None:
    args = arguments()
    workbook = resolve_workbook(args.workbook)
    with zipfile.ZipFile(workbook) as archive:
        rows = parse_rows(archive, "cohorte_lal")

    values, patients, csf_row_count, invalid_values = extract_csf_volumes(rows)
    summary = summary_row(values, patients, csf_row_count, invalid_values)
    write_csv(args.output, OUTPUT_FIELDS, [summary])
    write_violin_plot(args.plot_output, values)
    print(f"CSF rows: {csf_row_count}")
    print(f"Numeric CSF volumes: {len(values)}")
    print(f"Wrote: {args.output}")
    print(f"Wrote: {args.plot_output}")


if __name__ == "__main__":
    main()
