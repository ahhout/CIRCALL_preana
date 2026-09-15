#!/usr/bin/env python3
"""Summarize statistical outputs under an outputs root.

Creates a compact report workbook that matches our agreed analysis plan:
- Categorical MixedLM contrasts are primary.
- Welch tests are descriptive; we provide an additional patient-median variant.
- Reduced hypothesis family is highlighted (Control vs diag; diag vs post-treatment).
- TP0.5 contrasts are labeled exploratory.
- Sensitivity analyses (outlier-drop and random-slope) are included side-by-side.

Data safety note:
This script avoids writing patient identifiers into the report. It only outputs
aggregate counts and contrast-level results.
"""

from __future__ import annotations

import argparse
import re
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd

import stats_reporting


def _norm(s: str) -> str:
    s = str(s).strip().lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"[^a-z0-9% ]+", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s


def find_col(cols: list[str], patterns: list[list[str]]) -> str:
    ncols = {c: _norm(c) for c in cols}

    def and_match(nc: str, toks: list[str]) -> bool:
        return all(_norm(t) in nc for t in toks)

    for c, nc in ncols.items():
        for toks in patterns:
            if and_match(nc, toks):
                return c

    best, best_score = None, -1
    for c, nc in ncols.items():
        score = max(sum(_norm(t) in nc for t in toks) for toks in patterns)
        if score > best_score:
            best, best_score = c, score

    if best is None or best_score <= 0:
        raise KeyError("Could not find a matching donors concentration column")

    return best


def _parse_timepoints_arg(s: str) -> list[str]:
    # Use ';' as primary separator because some timepoints contain commas.
    parts = [p.strip() for p in str(s).split(";") if p.strip()]
    return parts


def paired_patient_counts(df_patients: pd.DataFrame, timepoints: list[str]) -> pd.DataFrame:
    df = df_patients.copy()
    df["timepoint"] = df["timepoint"].astype(str).str.strip().str.lower()
    df = df[df["timepoint"].isin([t.lower() for t in timepoints])].copy()

    pres = df.pivot_table(
        index="lastname",
        columns="timepoint",
        values="ng_per_ml",
        aggfunc="size",
        fill_value=0,
    )
    b = pres > 0

    rows: list[dict] = []
    for i in range(len(timepoints)):
        for j in range(i + 1, len(timepoints)):
            a, c = timepoints[i].lower(), timepoints[j].lower()
            if a not in b.columns or c not in b.columns:
                n = 0
            else:
                n = int((b[a] & b[c]).sum())
            rows.append({"timepoint_a": timepoints[i], "timepoint_b": timepoints[j], "paired_patients": n})

    return pd.DataFrame(rows)


def main() -> None:
    p = argparse.ArgumentParser(description="Summarize cfDNA statistical outputs from an outputs directory.")
    p.add_argument("--parsed", default="outputs/results/cfdna_parsed.csv", help="patient parsed CSV")
    p.add_argument("--donors", default="cfDNA_donors.xlsx", help="donors Excel")
    p.add_argument(
        "--outputs_dir",
        default="outputs",
        help="output root directory (expects CSVs in <root>/results and diagnostics in <root>/diagnostics)",
    )
    p.add_argument(
        "--test_outputs_dir",
        default=None,
        help="DEPRECATED alias for --outputs_dir (kept for backward compatibility)",
    )
    p.add_argument(
        "--timepoints",
        default="diag;tp0,5;tp1;tp2",
        help="patient timepoints of interest (semicolon-separated)",
    )
    p.add_argument(
        "--out_xlsx",
        default=None,
        help="output report workbook path (default: <outputs_dir>/results/final_stats_report.xlsx)",
    )
    args = p.parse_args()

    outputs_dir = Path(args.outputs_dir)
    if args.test_outputs_dir:
        outputs_dir = Path(args.test_outputs_dir)

    if not outputs_dir.exists():
        raise SystemExit(f"outputs_dir does not exist: {outputs_dir}")

    # Allow passing either the root (outputs/) or the results folder directly.
    results_dir = outputs_dir / "results" if (outputs_dir / "results").exists() else outputs_dir
    if not results_dir.exists():
        raise SystemExit(f"results directory does not exist: {results_dir}")

    out_xlsx = Path(args.out_xlsx) if args.out_xlsx else (results_dir / "final_stats_report.xlsx")

    timepoints = _parse_timepoints_arg(args.timepoints)
    bins = ["Control"] + timepoints

    # ---- Load primary outputs (if present) ----
    mixed_path = results_dir / "cfDNA_mixedlm_timepoint_contrasts_log10_bh.csv"
    pairwise_path = results_dir / "cfDNA_pairwise_bins_stats_log10_bh.csv"
    outlier_cmp_path = results_dir / "cfDNA_mixedlm_outlier_drop2_contrasts_vs_base.csv"
    random_slope_path = results_dir / "cfDNA_mixedlm_random_slope_time_contrasts_log10_bh.csv"

    if not mixed_path.exists():
        raise SystemExit(f"Missing primary MixedLM output: {mixed_path}")
    if not pairwise_path.exists():
        raise SystemExit(f"Missing pairwise output: {pairwise_path}")

    mixed = pd.read_csv(mixed_path)
    pairwise_sample = pd.read_csv(pairwise_path)

    outlier_cmp = pd.read_csv(outlier_cmp_path) if outlier_cmp_path.exists() else None
    random_slope = pd.read_csv(random_slope_path) if random_slope_path.exists() else None

    # ---- Load raw data for counts and descriptive patient-median Welch tests ----
    parsed_path = Path(args.parsed)
    if not parsed_path.exists() and parsed_path.name == "cfdna_parsed.csv":
        # Backward-compatible fallback for old default location
        parsed_path = Path("cfdna_parsed.csv")
    df_patients = pd.read_csv(parsed_path)
    required = {"lastname", "timepoint", "ng_per_ml"}
    missing = required - set(df_patients.columns)
    if missing:
        raise SystemExit(f"Parsed file missing columns: {missing}")

    donors = pd.read_excel(args.donors, decimal=",")
    donors.columns = [str(c).strip() for c in donors.columns]
    conc_col = find_col(
        list(donors.columns),
        [["conc", "ng", "ml"], ["concentration", "ng", "ml"], ["ng", "ml"]],
    )
    donors = donors.copy()
    donors["ng/ml plasma"] = pd.to_numeric(donors[conc_col], errors="coerce")
    donors["timepoint"] = "Control"

    # ---- Patient-median pairwise (descriptive cross-check) ----
    pairwise_patient_median = stats_reporting.compute_pairwise_bins(
        df_patients=df_patients,
        donors=donors,
        bins=bins,
        unit="patient_median",
        scale="log10",
        correction="bh",
    )

    # ---- Mann–Whitney (nonparametric) sensitivity check (patient medians; log10; BH) ----
    mannwhitney_patient_median = stats_reporting.compute_mannwhitney_bins(
        df_patients=df_patients,
        donors=donors,
        bins=bins,
        unit="patient_median",
        scale="log10",
        correction="bh",
        alternative="two-sided",
        method="auto",
        report_effect_size=True,
    )

    # ---- Paired-patient counts (patients only; no Control) ----
    paired = paired_patient_counts(df_patients, timepoints)

    # ---- Primary hypothesis family flagging ----
    primary_pairs = {
        ("Control", "diag"),
        ("diag", "tp0,5"),
        ("diag", "tp1"),
        ("diag", "tp2"),
    }

    mixed2 = mixed.copy()

    def _is_primary(a: str, b: str) -> bool:
        return (a, b) in primary_pairs or (b, a) in primary_pairs

    mixed2["primary_family"] = [
        _is_primary(str(a), str(b)) for a, b in zip(mixed2["timepoint_a"], mixed2["timepoint_b"], strict=False)
    ]

    mixed2["tp0,5_exploratory"] = [
        (str(a) == "tp0,5") or (str(b) == "tp0,5") for a, b in zip(mixed2["timepoint_a"], mixed2["timepoint_b"], strict=False)
    ]

    # Attach paired counts where applicable (patient-only contrasts)
    paired_key = paired.copy()
    paired_key["key"] = paired_key["timepoint_a"].astype(str) + "||" + paired_key["timepoint_b"].astype(str)
    mixed2["key"] = mixed2["timepoint_a"].astype(str) + "||" + mixed2["timepoint_b"].astype(str)
    mixed2 = mixed2.merge(paired_key[["key", "paired_patients"]], on="key", how="left")
    mixed2.drop(columns=["key"], inplace=True)

    # ---- Add outlier-drop sensitivity deltas (if available) ----
    if outlier_cmp is not None and len(outlier_cmp):
        outlier_cmp2 = outlier_cmp[[
            "timepoint_a",
            "timepoint_b",
            "delta_log10_refit",
            "fold_change_refit",
            "p_adj_refit",
            "diff_delta_log10",
            "diff_fold_change",
            "diff_p_adj",
        ]].copy()
        outlier_cmp2 = outlier_cmp2.rename(
            columns={
                "delta_log10_refit": "outlier_drop_delta_log10_refit",
                "fold_change_refit": "outlier_drop_fold_change_refit",
                "p_adj_refit": "outlier_drop_p_adj_refit",
                "diff_delta_log10": "outlier_drop_diff_delta_log10",
                "diff_fold_change": "outlier_drop_diff_fold_change",
                "diff_p_adj": "outlier_drop_diff_p_adj",
            }
        )
        mixed2 = mixed2.merge(outlier_cmp2, on=["timepoint_a", "timepoint_b"], how="left")

    # ---- Add random-slope qualitative agreement (patients only) ----
    if random_slope is not None and len(random_slope):
        rs2 = random_slope[["timepoint_a", "timepoint_b", "delta_log10", "p_adj"]].copy()
        rs2 = rs2.rename(columns={"delta_log10": "random_slope_delta_log10", "p_adj": "random_slope_p_adj"})
        mixed2 = mixed2.merge(rs2, on=["timepoint_a", "timepoint_b"], how="left")

        def _sign(x: float) -> float:
            if not np.isfinite(x) or x == 0:
                return 0.0
            return 1.0 if x > 0 else -1.0

        mixed2["random_slope_agrees_direction"] = [
            (_sign(a) == _sign(b))
            if (np.isfinite(a) and np.isfinite(b) and _sign(a) != 0.0 and _sign(b) != 0.0)
            else np.nan
            for a, b in zip(mixed2["delta_log10"], mixed2.get("random_slope_delta_log10", pd.Series([np.nan] * len(mixed2))), strict=False)
        ]

    # ---- Build compact primary table ----
    primary_mixed = mixed2[mixed2["primary_family"]].copy().sort_values(["timepoint_a", "timepoint_b"])

    # ---- Minimal counts table ----
    counts = (
        df_patients[df_patients["timepoint"].astype(str).str.strip().str.lower().isin([t.lower() for t in timepoints])]
        .assign(timepoint=lambda x: x["timepoint"].astype(str).str.strip().str.lower())
        .groupby("timepoint")
        .agg(
            n_samples=("ng_per_ml", lambda s: int(pd.to_numeric(s, errors="coerce").notna().sum())),
            n_patients=("lastname", lambda s: int(pd.Series(s).nunique())),
        )
        .reset_index()
    )

    # ---- Write workbook ----
    out_xlsx.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(out_xlsx, engine="openpyxl") as w:
        primary_mixed.to_excel(w, sheet_name="PrimaryMixed", index=False)
        mixed2.sort_values("p_adj").to_excel(w, sheet_name="AllMixed", index=False)
        pairwise_sample.sort_values("p_adj_bh").to_excel(w, sheet_name="PairwiseSample", index=False)
        pairwise_patient_median.sort_values("p_adj_bh").to_excel(w, sheet_name="PairwisePatientMedian", index=False)
        mannwhitney_patient_median.sort_values("p_adj_bh").to_excel(w, sheet_name="MannWhitneyPatientMedian", index=False)
        paired.sort_values("paired_patients", ascending=False).to_excel(w, sheet_name="PairedCounts", index=False)
        counts.to_excel(w, sheet_name="TimepointCounts", index=False)

    print(f"wrote report: {out_xlsx}")


if __name__ == "__main__":
    main()
