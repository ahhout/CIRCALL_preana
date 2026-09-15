#!/usr/bin/env python3
import argparse
from workflow_paths import parse_workflow_args
import hashlib
import os
import re
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from matplotlib.ticker import LogFormatter
from matplotlib.lines import Line2D
from scipy.stats import ttest_ind

import stats_reporting

SUBTYPE_COLORS = {
    "B-Other": "#1f77b4",
    "DUX4-r": "#aec7e8",
    "ETV6::RUNX1": "#ff7f0e",
    "ETV6::RUNX1-like": "#ffbb78",
    "Hyperdiploidy": "#2ca02c",
    "KMT2A-r": "#98df8a",
    "MYC-r": "#d62728",
    "PAX5-r": "#ff9896",
    "PAX5alt": "#9467bd",
    "Ph+": "#c5b0d5",
    "Ph-like ABL-class": "#8c564b",
    "Ph-like JAK-class": "#c49c94",
    "T-Other": "#e377c2",
    "TCF3::PBX1": "#f7b6d2",
    "ZNF384-r": "#7f7f7f",
    "iAmp21": "#c7c7c7",
}
UNKNOWN_SUBTYPE_COLOR = (0.35, 0.35, 0.35, 1.0)

# ----------------------------- helpers -----------------------------

def _norm(s: str) -> str:
    s = str(s) if not isinstance(s, str) else s
    s = s.strip().lower()
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"[^a-z0-9% ]+", " ", s)
    s = re.sub(r"\s+", " ", s)
    return s

def find_col(cols, patterns, required=True):
    ncols = {c: _norm(c) for c in cols}

    def and_match(nc: str, toks):
        toks = [_norm(t) for t in toks]
        return all(t in nc for t in toks)

    if isinstance(patterns, str):
        pattern_sets = [[patterns]]
    elif isinstance(patterns, (list, tuple)) and all(isinstance(p, str) for p in patterns):
        pattern_sets = [list(patterns)]
    else:
        pattern_sets = patterns

    for c, nc in ncols.items():
        for toks in pattern_sets:
            if and_match(nc, toks):
                return c

    # fallback: best partial score
    best, best_score = None, -1
    for c, nc in ncols.items():
        score = max(sum(_norm(t) in nc for t in toks) for toks in pattern_sets)
        if score > best_score:
            best, best_score = c, score
    if best_score > 0:
        return best

    if required:
        raise KeyError("Could not find a matching donors column.")
    return None

def tp_sort_key(tp: str):

    if tp == "diag": return (0, 0)
    m = re.match(r"tp(\d+)(?:,(\d))?$", str(tp).lower())
    if m:
        whole = int(m.group(1)); frac = int(m.group(2) or 0)
        return (1, whole * 10 + frac)
    if str(tp).lower() == "rechute": return (2, 0)
    if "inotuzumab" in str(tp).lower(): return (3, 0)
    return (4, str(tp))

# ------------------------------- main ------------------------------

def main():
    p = argparse.ArgumentParser(description="Analyze parsed cfDNA data and produce tables/plots.")
    p.add_argument("--parsed", default="outputs/results/cfdna_parsed.csv", help="input parsed CSV from parser")
    p.add_argument("--donors", default="cfDNA_donors.xlsx", help="donors Excel file")
    p.add_argument("--out_excel", default="outputs/results/cfdna_analysis.xlsx", help="output Excel with Summary+Detailed")
    p.add_argument("--plot", default="outputs/results/cfDNA_points_comparison_log.jpeg", help="scatter plot image (Control/Diagnosis/TP1)")
    p.add_argument("--violin", default="outputs/results/cfDNA_violin_log.jpeg", help="violin plot image (Control + all timepoints)")
    p.add_argument(
        "--violin_subset",
        default="outputs/results/cfDNA_violin_subset_connected_log_excl_tp0p5_by_genetic_subtype.jpeg",
        help="violin plot image (Control + selected patient timepoints; connected per patient)",
    )
    p.add_argument(
        "--violin_subset_unconnected",
        default="outputs/results/cfDNA_violin_subset_log_excl_tp0p5_by_genetic_subtype.jpeg",
        help="(optional) second subset violin output without connecting lines (points only). Use 'none' to disable.",
    )
    p.add_argument(
        "--violin_subset_timepoints",
        default="diag;tp0,5;tp1;tp2",
        help="patient timepoints to include. Prefer ';' as separator (because some timepoints contain ','). Example: 'diag;tp0,5;tp1;tp2'",
    )
    p.add_argument(
        "--violin_subset_connect_lines",
        default=True,
        action=argparse.BooleanOptionalAction,
        help="connect points from the same patient across timepoints",
    )
    p.add_argument(
        "--violin_subset_connect_agg",
        default="median",
        choices=["median", "mean", "first"],
        help="when multiple samples exist per patient+timepoint, aggregation for connecting lines",
    )
    p.add_argument("--violin_total_ng", default="outputs/results/cfDNA_violin_total_ng_log.jpeg",
                   help="violin plot image (patients only; total cfDNA ng by timepoint)")

    p.add_argument(
        "--pairwise_table",
        default=None,
        help="(optional) output CSV with pairwise statistical comparisons between bins; if omitted only Excel sheet is written",
    )
    p.add_argument(
        "--pairwise_bins",
        default="subset",
        choices=["subset", "all"],
        help="which bins to compare: 'subset' uses Control + violin_subset_timepoints; 'all' uses Control + all patient timepoints",
    )
    p.add_argument(
        "--pairwise_unit",
        default="sample",
        choices=["sample", "patient_median"],
        help="statistical unit: raw samples, or per-patient median within each bin",
    )
    p.add_argument(
        "--pairwise_scale",
        default="log10",
        choices=["log10"],
        help="run tests on linear values or log10-transformed values",
    )
    p.add_argument(
        "--pairwise_correction",
        default="bh",
        choices=["bh"],
        help="multiple-testing correction across all pairwise comparisons",
    )

    p.add_argument(
        "--mixed_table",
        default=None,
        help="(optional) output CSV with mixed-effects model timepoint contrasts; if omitted only Excel sheet is written",
    )
    p.add_argument(
        "--mixed_bins",
        default="subset",
        choices=["subset", "all"],
        help="which timepoints to include in the MixedLM: 'subset' uses Control + violin_subset_timepoints; 'all' uses Control + all patient timepoints",
    )
    p.add_argument(
        "--mixed_correction",
        default="bh",
        choices=["bh"],
        help="multiple-comparisons correction for MixedLM contrasts (BH enforced)",
    )

    p.add_argument(
        "--test_outputs_dir",
        default="outputs",
        help="output root directory. Results are written to <root>/results and diagnostics to <root>/diagnostics",
    )

    p.add_argument(
        "--mixed_random_slope_sensitivity",
        default=False,
        action=argparse.BooleanOptionalAction,
        help="run sensitivity MixedLM with random slope over ordered time (patients only)",
    )
    p.add_argument(
        "--mixed_outlier_drop_n",
        type=int,
        default=0,
        help="outlier sensitivity: drop top-N observations by |residual| and refit once (0 disables). Suggested: 1 or 2",
    )
    args = parse_workflow_args(p, inputs={'donors': 'cfDNA_donors.xlsx'}, outputs=['parsed', 'out_excel', 'plot', 'violin', 'violin_subset', 'violin_subset_unconnected', 'violin_total_ng', 'pairwise_table', 'mixed_table'], root_flag='test_outputs_dir')

    # load parsed (must include ALL timepoints already)
    parsed_path = Path(args.parsed)
    if not parsed_path.exists() and parsed_path.name == "cfdna_parsed.csv":
        # Backward-compatible fallback for old default location
        parsed_path = Path("cfdna_parsed.csv")
    df = pd.read_csv(parsed_path)
    required_cols = {"lastname","timepoint","tube","ml_plasma","pct_cfdna","dosage_ng_per_uL","total_ng_dna","ng_per_ml"}
    missing = required_cols - set(df.columns)
    if missing:
        raise SystemExit(f"parsed file is missing columns: {missing}")

    # -------- Excel: Summary (all timepoints) + Detailed --------
    summary = (
        df.groupby("timepoint", dropna=False)
          .agg(
              unique_patient_count = ("lastname", lambda x: len(set(x))),
              mean_ml_plasma       = ("ml_plasma", "mean"),
              mean_total_ng_DNA    = ("total_ng_dna", "mean"),
              median_total_ng_DNA  = ("total_ng_dna", "median"),
              mean_ng_per_ml       = ("ng_per_ml", "mean"),
              median_ng_per_ml     = ("ng_per_ml", "median"),
          )
          .reset_index()
    )
    summary = summary.sort_values("timepoint", key=lambda s: s.map(tp_sort_key)).round(2)

    os.makedirs(os.path.dirname(os.path.abspath(args.out_excel)), exist_ok=True)
    with pd.ExcelWriter(args.out_excel, engine="openpyxl") as w:
        summary.to_excel(w, sheet_name="Summary", index=False)
        df.to_excel(w, sheet_name="Detailed", index=False)
    print(f"excel saved: {os.path.abspath(args.out_excel)}")

    # -------- Donors (find concentration column robustly) --------
    donors = pd.read_excel(args.donors, decimal=",")
    donors.columns = [c.strip() for c in donors.columns]
    conc_col = find_col(
        donors.columns,
        [["conc", "ng", "ml"], ["concentration", "ng", "ml"], ["ng", "ml"]]
    )
    donors["ng/ml plasma"] = pd.to_numeric(donors[conc_col], errors="coerce")
    donors["timepoint"] = "Control"

    # Report volume diagnostics without patient names.
    prob = df[df["ml_plasma"].astype(float) > 10]
    print(f"Samples with ml_plasma > 10: {len(prob)}")

    # ============================================================
    # Scatter: Control vs Diagnosis vs TP1  (kept as before)
    # ============================================================
    df_diag_tp1 = df[df["timepoint"].isin(["diag","tp1"])][["timepoint","ng_per_ml"]].copy()
    df_diag_tp1 = df_diag_tp1.rename(columns={"ng_per_ml":"ng/ml plasma"})

    df_plot = pd.concat(
        [donors[["timepoint","ng/ml plasma"]], df_diag_tp1],
        ignore_index=True
    )
    df_plot = df_plot[df_plot["ng/ml plasma"].notna()]
    df_plot["timepoint"] = pd.Categorical(df_plot["timepoint"], categories=["Control","diag","tp1"], ordered=True)

    counts = df_plot["timepoint"].value_counts().to_dict()
    label_map = {
        "Control": f"Control (n={counts.get('Control', 0)})",
        "diag":    f"Diagnosis (n={counts.get('diag', 0)})",
        "tp1":     f"TP1 (n={counts.get('tp1', 0)})",
    }

    plt.figure(figsize=(6.5, 5))
    xmap = {"Control": 0, "diag": 1, "tp1": 2}
    for label, x in xmap.items():
        yvals = df_plot[df_plot["timepoint"] == label]["ng/ml plasma"]
        plt.scatter([x]*len(yvals), yvals, alpha=0.8)

    plt.xticks([0,1,2], [label_map["Control"], label_map["diag"], label_map["tp1"]])
    plt.yscale("log")
    y_scatter = df_plot["ng/ml plasma"].to_numpy(dtype=float)
    y_scatter = y_scatter[np.isfinite(y_scatter) & (y_scatter > 0)]
    if y_scatter.size:
        ymin = float(y_scatter.min()) * 0.9
        ymax = float(y_scatter.max()) * 1.1
        ymin = 0.1 if ymin < 0.1 else ymin
        plt.ylim(ymin, ymax)
    plt.ylabel("ng/ml plasma (log scale)")
    plt.title("cfDNA in patients vs healthy donors (points)")
    plt.grid(True, which="both", axis="y", linestyle="--", alpha=0.4)
    plt.gca().yaxis.set_major_formatter(LogFormatter(labelOnlyBase=True))
    plt.tight_layout()
    os.makedirs(os.path.dirname(os.path.abspath(args.plot)), exist_ok=True)
    plt.savefig(args.plot, format="jpeg", dpi=600)
    plt.close()
    print(f"scatter saved: {os.path.abspath(args.plot)}")

    def _fmt_tick(v: float) -> str:
        return f"{float(v):g}"

    def _log10_limits_and_ticks(values: np.ndarray, floor: float | None = None):
        values = np.asarray(values, dtype=float)
        values = values[np.isfinite(values) & (values > 0)]
        if values.size == 0:
            return (0.0, 1.0), [1.0]

        y_min = float(values.min())
        y_max = float(values.max())
        if floor is not None:
            y_min = max(y_min, float(floor))

        # Build 'nice' ticks on a log scale: 1-2-5 * 10^k.
        def _nice_ticks(lo: float, hi: float) -> list[float]:
            if not (np.isfinite(lo) and np.isfinite(hi) and lo > 0 and hi > 0 and lo <= hi):
                return []
            p_lo = int(np.floor(np.log10(lo))) - 1
            p_hi = int(np.ceil(np.log10(hi))) + 1
            ticks: list[float] = []
            for p in range(p_lo, p_hi + 1):
                base = 10.0 ** p
                for m in (1.0, 2.0, 5.0):
                    ticks.append(m * base)
            ticks = sorted(set(t for t in ticks if lo <= t <= hi))
            return ticks

        def _nice_floor(v: float) -> float:
            ticks = _nice_ticks(v / 10.0, v)  # small window to find <= v
            candidates = [t for t in ticks if t <= v]
            return max(candidates) if candidates else v

        def _nice_ceil(v: float) -> float:
            ticks = _nice_ticks(v, v * 10.0)  # small window to find >= v
            candidates = [t for t in ticks if t >= v]
            return min(candidates) if candidates else v

        ymin = _nice_floor(y_min)
        ymax = _nice_ceil(y_max)
        if floor is not None:
            ymin = max(ymin, float(floor))

        tick_vals = _nice_ticks(ymin, ymax)

        # If range spans many decades, fall back to decades-only ticks.
        if tick_vals:
            decades = int(np.ceil(np.log10(ymax)) - np.floor(np.log10(ymin)))
            if decades >= 5 or len(tick_vals) > 14:
                pmin = int(np.floor(np.log10(ymin)))
                pmax = int(np.ceil(np.log10(ymax)))
                tick_vals = [10 ** p for p in range(pmin, pmax + 1)]
                tick_vals = [t for t in tick_vals if ymin <= t <= ymax]

        if not tick_vals:
            tick_vals = [ymin, ymax]
        return (ymin, ymax), tick_vals

    # ============================================================
    # Violin: Control + ALL patient timepoints, with jittered points
    # ============================================================
    # build combined df with donors and all timepoints
    df_all = df.rename(columns={"ng_per_ml":"ng/ml plasma"})[["timepoint","ng/ml plasma"]].copy()
    df_all = pd.concat([donors[["timepoint","ng/ml plasma"]], df_all], ignore_index=True)
    df_all = df_all[df_all["ng/ml plasma"].notna()].copy()

    # category order
    cats_patients = sorted(df["timepoint"].dropna().unique(), key=tp_sort_key)
    cats = ["Control"] + list(cats_patients)
    df_all["timepoint"] = pd.Categorical(df_all["timepoint"], categories=cats, ordered=True)

    # list of data arrays per category
    data = [df_all.loc[df_all["timepoint"] == c, "ng/ml plasma"].astype(float).values for c in cats]
    data = [y[np.isfinite(y) & (y > 0)] for y in data]

    # IMPORTANT: because we want a log-scaled view, we compute the violin density in log10-space.
    # If you compute KDE in linear space and then set a log y-axis, the violin shape can look
    # disconnected from the jittered points.
    data_log = [np.log10(y) if y.size else np.array([]) for y in data]

    # new style: thin, translucent violins + median line + IQR bar + jittered points
    plt.figure(figsize=(9.5, 5.5))
    parts = plt.violinplot(
        dataset=data_log,
        positions=range(len(cats)),
        widths=0.8,
        showmeans=False,
        showmedians=False,
        showextrema=False
    )
    # translucency and slimmer outlines without setting explicit colors
    for b in parts["bodies"]:
        b.set_alpha(0.25)
        b.set_linewidth(1.0)

    # overlay median line and IQR bar per category
    for i, y in enumerate(data):
        if y.size == 0:
            continue
        q1, med, q3 = np.percentile(y, [25, 50, 75])
        q1l, medl, q3l = np.log10([q1, med, q3])
        # IQR bar (thin vertical line)
        plt.vlines(i, q1l, q3l, linewidth=2, zorder=3)
        # median line (short horizontal bar)
        plt.hlines(medl, i - 0.18, i + 0.18, linewidth=2, zorder=4)
        # annotate median value (black)
        plt.text(
            i + 0.24,
            medl,
            f"{med:.0f}",
            color="black",
            fontsize=8,
            va="center",
            ha="left",
            zorder=6,
        )

    # jittered individual points
    rng = np.random.default_rng(42)
    for i, y in enumerate(data):
        if y.size == 0:
            continue
        x = i + rng.uniform(-0.08, 0.08, size=y.size)
        plt.scatter(x, np.log10(y), s=12, alpha=0.7, linewidths=0.3, zorder=5)

    # axes, labels
    # y-axis is log10(values) (limits derived from data so nothing is clipped)
    (ymin, ymax), tick_vals = _log10_limits_and_ticks(np.concatenate(data) if data else np.array([]), floor=0.1)
    plt.ylim(np.log10(ymin), np.log10(ymax))
    plt.yticks([np.log10(t) for t in tick_vals], [_fmt_tick(t) for t in tick_vals])
    counts_all = df_all["timepoint"].value_counts().to_dict()
    def pretty_label(c):
        if c == "Control": return f"Control (n={counts_all.get(c,0)})"
        if c == "diag":    return f"Diagnosis (n={counts_all.get(c,0)})"
        return f"{c.upper()} (n={counts_all.get(c,0)})"

    plt.xticks(range(len(cats)), [pretty_label(c) for c in cats], rotation=15, ha="right")
    plt.ylabel("ng/ml plasma (log scale)")
    plt.title("cfDNA by timepoint vs healthy donors (violin + points)")
    plt.grid(True, which="both", axis="y", linestyle="--", alpha=0.4)
    plt.minorticks_on()
    plt.tight_layout()
    os.makedirs(os.path.dirname(os.path.abspath(args.violin)), exist_ok=True)
    plt.savefig(args.violin, format="jpeg", dpi=600)
    plt.close()
    print(f"violin saved: {os.path.abspath(args.violin)}")

    # ============================================================
    # Violin (subset): Control + selected patient timepoints,
    # with optional per-patient connecting lines
    # ============================================================
    def _stable_u01(key: str) -> float:
        h = hashlib.blake2b(key.encode("utf-8"), digest_size=8).digest()
        return int.from_bytes(h, "little") / float(2**64 - 1)

    def _stable_jitter(key: str, width: float = 0.08) -> float:
        u = _stable_u01(key)
        return (u * 2.0 - 1.0) * width

    def _parse_timepoints_arg(raw: str, available: set[str]) -> list[str]:
        raw = str(raw)
        sep = ";" if ";" in raw else ","
        toks = [t.strip().lower() for t in raw.split(sep) if t.strip()]

        # If user used comma separator, timepoints like 'tp0,5' can be split into ['tp0','5'].
        # Recombine if the joined candidate exists in the data.
        if sep == ",":
            out: list[str] = []
            i = 0
            while i < len(toks):
                cur = toks[i]
                nxt = toks[i + 1] if i + 1 < len(toks) else None
                if nxt is not None and re.fullmatch(r"tp\d+", cur) and re.fullmatch(r"\d+", nxt):
                    cand = f"{cur},{nxt}"
                    if cand in available:
                        out.append(cand)
                        i += 2
                        continue
                out.append(cur)
                i += 1
            toks = out
        return toks

    available_tps = set(df["timepoint"].dropna().astype(str).str.strip().str.lower().unique().tolist())
    subset_tps_norm = _parse_timepoints_arg(args.violin_subset_timepoints, available=available_tps)
    subset_tps_norm = list(dict.fromkeys(subset_tps_norm))  # de-dup, keep order
    subset_sorted = sorted(subset_tps_norm, key=tp_sort_key)
    subset_plot_sorted = [tp for tp in subset_sorted if str(tp).strip().lower() != "tp0,5"]

    df_pat = df.copy()
    df_pat["timepoint"] = df_pat["timepoint"].astype(str).str.strip().str.lower()
    df_pat = df_pat[df_pat["timepoint"].isin(subset_plot_sorted)].copy()
    df_pat = df_pat.rename(columns={"ng_per_ml": "ng/ml plasma"})
    patient_key_col = "patient_key" if "patient_key" in df_pat.columns else "lastname"
    df_pat["_patient"] = df_pat[patient_key_col].astype(str).str.strip().str.lower()
    subtype_col = None
    for c in df_pat.columns:
        nc = _norm(c)
        if nc in {"genetic subtype", "genetic_subtype"} or ("genetic" in nc and "subtype" in nc):
            subtype_col = c
            break
    if subtype_col is None:
        print("note: genetic_subtype column not found in parsed input; subtype colors will be set to 'unknown'")

    has_mrd_status = "MRD_IgTCR_status" in df_pat.columns
    has_mrd_raw = "MRD_IgTCR" in df_pat.columns
    keep_cols = ["_patient", "lastname", "timepoint", "ng/ml plasma"]
    if subtype_col is not None:
        keep_cols.append(subtype_col)
    if has_mrd_raw:
        keep_cols.append("MRD_IgTCR")
    if has_mrd_status:
        keep_cols.append("MRD_IgTCR_status")
    df_pat = df_pat[[c for c in keep_cols if c in df_pat.columns]].copy()

    df_sub_all = pd.concat(
        [
            donors[["timepoint", "ng/ml plasma"]].assign(lastname=pd.NA),
            df_pat,
        ],
        ignore_index=True,
    )
    df_sub_all = df_sub_all[df_sub_all["ng/ml plasma"].notna()].copy()

    cats_subset = ["Control"] + subset_plot_sorted
    df_sub_all["timepoint"] = pd.Categorical(df_sub_all["timepoint"], categories=cats_subset, ordered=True)

    data_subset = [
        df_sub_all.loc[df_sub_all["timepoint"] == c, "ng/ml plasma"].astype(float).values
        for c in cats_subset
    ]
    data_subset = [y[np.isfinite(y) & (y > 0)] for y in data_subset]
    data_subset_log = [np.log10(y) if y.size else np.array([]) for y in data_subset]

    pos = {c: i for i, c in enumerate(cats_subset)}

    # patients: one aggregated point per patient+timepoint (so lines connect the plotted points)
    df_pts = df_pat.dropna(subset=["_patient", "ng/ml plasma"]).copy()
    df_pts = df_pts[df_pts["ng/ml plasma"].astype(float) > 0]
    if args.violin_subset_connect_agg == "median":
        df_pts = df_pts.groupby(["_patient", "timepoint"], as_index=False)["ng/ml plasma"].median()
    elif args.violin_subset_connect_agg == "mean":
        df_pts = df_pts.groupby(["_patient", "timepoint"], as_index=False)["ng/ml plasma"].mean()
    else:  # first
        df_pts = df_pts.groupby(["_patient", "timepoint"], as_index=False)["ng/ml plasma"].first()

    def _norm_subtype(v) -> str:
        if pd.isna(v):
            return "unknown"
        s = str(v).strip()
        return s if s else "unknown"

    if subtype_col is not None and subtype_col in df_pat.columns:
        df_subtype = (
            df_pat.dropna(subset=["_patient"])
                  .assign(_genetic_subtype=lambda x: x[subtype_col].map(_norm_subtype))
                  .groupby("_patient", as_index=False)
                  .agg(_genetic_subtype=("_genetic_subtype", "first"))
        )
        df_pts = df_pts.merge(df_subtype, on="_patient", how="left")
    else:
        df_pts["_genetic_subtype"] = "unknown"

    df_pts["_genetic_subtype"] = df_pts["_genetic_subtype"].map(_norm_subtype)
    known_subtypes = sorted(s for s in df_pts["_genetic_subtype"].dropna().unique().tolist() if s != "unknown")
    subtype_palette = {s: SUBTYPE_COLORS.get(s, UNKNOWN_SUBTYPE_COLOR) for s in known_subtypes}

    def _subtype_color(subtype: str):
        return subtype_palette.get(str(subtype), UNKNOWN_SUBTYPE_COLOR)

    # MRD status per patient+timepoint (preferred: use parsed MRD_IgTCR_status).
    status_col = None
    if has_mrd_status:
        df_mrd_status = (
            df_pat.dropna(subset=["_patient", "timepoint"])
                 .groupby(["_patient", "timepoint"], as_index=False)
                 .agg(MRD_IgTCR_status=("MRD_IgTCR_status", "first"))
        )
        df_pts = df_pts.merge(df_mrd_status, on=["_patient", "timepoint"], how="left")
        status_col = "MRD_IgTCR_status"
    elif has_mrd_raw:
        def _mrd_norm(v) -> str:
            if pd.isna(v):
                return ""
            return str(v).strip().lower()

        # Missing MRD is treated as unknown (not negative). Negative requires at least one recorded entry.
        mrd_neg_values = {"na", "negative", "neg", "n/a"}
        missing_values = {"", "nan", "none"}

        df_mrd = df_pat.dropna(subset=["_patient", "timepoint"]).copy()
        df_mrd["_mrd_norm"] = df_mrd["MRD_IgTCR"].map(_mrd_norm)

        def _status_from_series(s: pd.Series) -> str:
            s = s.astype(str).str.strip().str.lower().replace({"nan": "", "none": ""})
            recorded = s[~s.isin(missing_values)]
            if recorded.empty:
                return ""
            if recorded.isin(mrd_neg_values).all():
                return "neg"
            return "pos"

        df_mrd_status = df_mrd.groupby(["_patient", "timepoint"], as_index=False).agg(
            _mrd_status=("_mrd_norm", _status_from_series)
        )
        df_pts = df_pts.merge(df_mrd_status, on=["_patient", "timepoint"], how="left")
        status_col = "_mrd_status"

    tp_order = {tp: i for i, tp in enumerate(subset_plot_sorted)}
    df_pts["_tp_order"] = df_pts["timepoint"].map(tp_order)
    df_pts = df_pts.dropna(subset=["_tp_order"]).copy()
    df_pts["_x"] = df_pts.apply(
        lambda rr: pos[rr["timepoint"]] + _stable_jitter(f"{rr['_patient']}|{rr['timepoint']}", width=0.08),
        axis=1,
    )

    counts_subset = df_sub_all["timepoint"].value_counts().to_dict()
    def _display_tp(tp: str) -> str:
        tp = str(tp)
        if tp.startswith("tp"):
            return tp.upper().replace(",", ".")
        return tp
    def pretty_label_subset(c):
        if c == "Control":
            return f"Control (n={counts_subset.get(c, 0)})"
        if c == "diag":
            return f"Diagnosis (n={counts_subset.get(c, 0)})"
        return f"{_display_tp(c)} (n={counts_subset.get(c, 0)})"

    def _save_subset_violin(out_path: str, connect_lines: bool) -> None:
        plt.figure(figsize=(7.5, 5.5))

        # Matplotlib's violin KDE requires >=2 points. Only draw violins where possible.
        violin_positions: list[int] = []
        violin_data: list[np.ndarray] = []
        for i, yl in enumerate(data_subset_log):
            if isinstance(yl, np.ndarray) and yl.size >= 2:
                violin_positions.append(i)
                violin_data.append(yl)

        if violin_data:
            parts = plt.violinplot(
                dataset=violin_data,
                positions=violin_positions,
                widths=0.8,
                showmeans=False,
                showmedians=False,
                showextrema=False,
            )
            for b in parts["bodies"]:
                b.set_alpha(0.25)
                b.set_linewidth(1.0)

        # overlay median + IQR for each category
        for i, y in enumerate(data_subset):
            if y.size == 0:
                continue
            q1, med, q3 = np.percentile(y, [25, 50, 75])
            q1l, medl, q3l = np.log10([q1, med, q3])
            plt.vlines(i, q1l, q3l, linewidth=2, zorder=3)
            plt.hlines(medl, i - 0.18, i + 0.18, linewidth=2, zorder=4)
            plt.text(
                i + 0.24,
                medl,
                f"{med:.0f}",
                color="black",
                fontsize=8,
                va="center",
                ha="left",
                zorder=6,
            )

        # donors: individual points
        df_don_pts = donors[["timepoint", "ng/ml plasma"]].copy()
        df_don_pts = df_don_pts[df_don_pts["ng/ml plasma"].notna()].copy()
        for idx, r in df_don_pts.iterrows():
            y = float(r["ng/ml plasma"])
            if not np.isfinite(y) or y <= 0:
                continue
            x = pos["Control"] + _stable_jitter(f"Control|{idx}", width=0.08)
            plt.scatter(
                [x],
                [np.log10(y)],
                s=18,
                alpha=0.85,
                linewidths=0.9,
                zorder=6,
                color="0.6",
                marker="x",
            )

        # patient points
        for _, r in df_pts.iterrows():
            y = float(r["ng/ml plasma"])
            if not np.isfinite(y) or y <= 0:
                continue

            is_post_diagnosis_tp = str(r["timepoint"]).lower() not in {"diag", "control"}
            mrd_status = str(r.get(status_col, "")).lower() if status_col is not None else ""
            marker = "x" if (is_post_diagnosis_tp and mrd_status == "neg") else "o"
            size = 18 if marker == "x" else 12
            plt.scatter(
                [float(r["_x"])],
                [np.log10(y)],
                s=size,
                alpha=0.85,
                linewidths=0.9 if marker == "x" else 0.3,
                zorder=6,
                color=_subtype_color(str(r["_genetic_subtype"])),
                marker=marker,
            )

        # per-patient connecting lines
        if connect_lines:
            for _, g in df_pts.sort_values(["_patient", "_tp_order"]).groupby("_patient"):
                if len(g) < 2:
                    continue
                xs = g["_x"].to_numpy(dtype=float)
                ys = g["ng/ml plasma"].to_numpy(dtype=float)
                mask = np.isfinite(ys) & (ys > 0)
                xs = xs[mask]
                ys = ys[mask]
                if ys.size < 2:
                    continue
                line_color = _subtype_color(str(g["_genetic_subtype"].iloc[0])) if "_genetic_subtype" in g.columns else "black"
                plt.plot(xs, np.log10(ys), color=line_color, alpha=0.30, linewidth=0.6, zorder=2)

        legend_handles = [
            Line2D([0], [0], marker="o", linestyle="", color=c, markerfacecolor=c, markersize=5, label=s)
            for s, c in subtype_palette.items()
        ]
        if (df_pts["_genetic_subtype"] == "unknown").any() or not legend_handles:
            legend_handles.append(
                Line2D([0], [0], marker="o", linestyle="", color=UNKNOWN_SUBTYPE_COLOR, markerfacecolor=UNKNOWN_SUBTYPE_COLOR, markersize=5, label="unknown")
            )
        plt.legend(
            handles=legend_handles,
            title="Genetic subtype",
            loc="center left",
            bbox_to_anchor=(1.02, 0.5),
            borderaxespad=0.0,
            fontsize=7,
            title_fontsize=8,
            frameon=True,
        )

        (ymin, ymax), tick_vals = _log10_limits_and_ticks(
            np.concatenate(data_subset) if data_subset else np.array([]),
            floor=0.1,
        )
        plt.ylim(np.log10(ymin), np.log10(ymax))
        plt.yticks([np.log10(t) for t in tick_vals], [_fmt_tick(t) for t in tick_vals])
        plt.xticks(range(len(cats_subset)), [pretty_label_subset(c) for c in cats_subset], rotation=15, ha="right")
        plt.ylabel("ng/ml plasma (log scale)")
        plt.title("plasma cfDNA by timepoint and genetic subtype")
        plt.grid(True, which="both", axis="y", linestyle="--", alpha=0.4)
        plt.minorticks_on()
        plt.tight_layout(rect=(0.0, 0.0, 0.82, 1.0))
        os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)
        plt.savefig(out_path, format="jpeg", dpi=600)
        plt.close()
        print(f"violin (subset) saved: {os.path.abspath(out_path)}")

    _save_subset_violin(args.violin_subset, connect_lines=bool(args.violin_subset_connect_lines))

    raw_alt = str(args.violin_subset_unconnected).strip() if args.violin_subset_unconnected is not None else ""
    if raw_alt and raw_alt.lower() not in {"none", "null"}:
        if os.path.abspath(raw_alt) == os.path.abspath(args.violin_subset):
            print("note: violin_subset_unconnected points to the same path as violin_subset; skipping second write")
        else:
            _save_subset_violin(raw_alt, connect_lines=False)

    # ============================================================
    # Violin: PATIENTS ONLY, TOTAL cfDNA ng (total_ng_dna)
    # (donors don't have a comparable 'total ng' field here)
    # ============================================================
    df_total = df[["timepoint", "total_ng_dna"]].rename(columns={"total_ng_dna": "cfDNA total ng"}).copy()
    df_total = df_total[df_total["cfDNA total ng"].notna()].copy()
    df_total["timepoint"] = pd.Categorical(
        df_total["timepoint"],
        categories=sorted(df["timepoint"].dropna().unique(), key=tp_sort_key),
        ordered=True,
    )

    cats_total = list(df_total["timepoint"].cat.categories)
    data_total = [df_total.loc[df_total["timepoint"] == c, "cfDNA total ng"].astype(float).values for c in cats_total]
    data_total = [y[np.isfinite(y) & (y > 0)] for y in data_total]
    data_total_log = [np.log10(y) if y.size else np.array([]) for y in data_total]

    plt.figure(figsize=(9.5, 5.5))
    parts = plt.violinplot(
        dataset=data_total_log,
        positions=range(len(cats_total)),
        widths=0.8,
        showmeans=False,
        showmedians=False,
        showextrema=False,
    )
    for b in parts["bodies"]:
        b.set_alpha(0.25)
        b.set_linewidth(1.0)

    for i, y in enumerate(data_total):
        if y.size == 0:
            continue
        q1, med, q3 = np.percentile(y, [25, 50, 75])
        q1l, medl, q3l = np.log10([q1, med, q3])
        plt.vlines(i, q1l, q3l, linewidth=2, zorder=3)
        plt.hlines(medl, i - 0.18, i + 0.18, linewidth=2, zorder=4)
        plt.text(
            i + 0.24,
            medl,
            f"{med:.0f}",
            color="black",
            fontsize=8,
            va="center",
            ha="left",
            zorder=6,
        )

    rng = np.random.default_rng(42)
    for i, y in enumerate(data_total):
        if y.size == 0:
            continue
        x = i + rng.uniform(-0.08, 0.08, size=y.size)
        plt.scatter(x, np.log10(y), s=12, alpha=0.7, linewidths=0.3, zorder=5)

    (ymin, ymax), tick_vals = _log10_limits_and_ticks(np.concatenate(data_total) if data_total else np.array([]), floor=0.1)
    plt.ylim(np.log10(ymin), np.log10(ymax))
    plt.yticks([np.log10(t) for t in tick_vals], [_fmt_tick(t) for t in tick_vals])
    plt.ylabel("cfDNA total ng (log scale)")
    counts_total = df_total["timepoint"].value_counts().to_dict()
    def pretty_label_total(c):
        if c == "diag":
            return f"Diagnosis (n={counts_total.get(c, 0)})"
        return f"{str(c).upper()} (n={counts_total.get(c, 0)})"
    plt.xticks(range(len(cats_total)), [pretty_label_total(c) for c in cats_total], rotation=15, ha="right")
    plt.title("Total cfDNA (ng) by timepoint (violin + points)")
    plt.grid(True, which="both", axis="y", linestyle="--", alpha=0.4)
    plt.minorticks_on()
    plt.tight_layout()
    os.makedirs(os.path.dirname(os.path.abspath(args.violin_total_ng)), exist_ok=True)
    plt.savefig(args.violin_total_ng, format="jpeg", dpi=600)
    plt.close()
    print(f"violin (total ng) saved: {os.path.abspath(args.violin_total_ng)}")

    # ============================================================
    # Pairwise statistical comparison table between bins
    # ============================================================
    if args.pairwise_bins == "subset":
        bins = ["Control"] + subset_sorted
    else:
        all_tps = sorted(
            df["timepoint"].dropna().astype(str).str.strip().str.lower().unique().tolist(),
            key=tp_sort_key,
        )
        bins = ["Control"] + all_tps

    pairwise_df = stats_reporting.compute_pairwise_bins(
        df_patients=df,
        donors=donors,
        bins=bins,
        unit=args.pairwise_unit,
        scale="log10",
        correction="bh",
    )

    out_root = Path(os.path.abspath(args.test_outputs_dir))
    results_dir = out_root / "results"
    diagnostics_dir = out_root / "diagnostics"
    results_dir.mkdir(parents=True, exist_ok=True)
    diagnostics_dir.mkdir(parents=True, exist_ok=True)

    # Always save updated pairwise CSV into <out_root>/results/
    pairwise_csv = str(results_dir / "cfDNA_pairwise_bins_stats_log10_bh.csv")
    pairwise_df.to_csv(pairwise_csv, index=False)
    print(f"pairwise stats CSV saved: {pairwise_csv}")

    # Diagnostics for t-test assumptions (per-bin hist + Q-Q on log10)
    try:
        stats_reporting.write_pairwise_log10_diagnostics(
            df_patients=df,
            donors=donors,
            bins=bins,
            out_dir=diagnostics_dir / "pairwise_log10",
        )
        print(f"pairwise diagnostics saved under: {diagnostics_dir / 'pairwise_log10'}")
    except Exception as e:
        print(f"warning: could not write pairwise diagnostics: {e}")

    if args.pairwise_table:
        pairwise_df.to_csv(args.pairwise_table, index=False)
        print(f"pairwise stats saved: {os.path.abspath(args.pairwise_table)}")

    # append to Excel output as a new sheet (or replace if present)
    try:
        with pd.ExcelWriter(args.out_excel, engine="openpyxl", mode="a", if_sheet_exists="replace") as w:
            pairwise_df.to_excel(w, sheet_name="PairwiseBins", index=False)
        print(f"pairwise stats added to Excel: {os.path.abspath(args.out_excel)} (sheet PairwiseBins)")
    except Exception as e:
        print(f"warning: could not append pairwise stats to Excel: {e}")

    # ============================================================
    # Mixed-effects model: log10(cfDNA) ~ timepoint + (1|patient)
    # Then all pairwise timepoint contrasts with fold-change + CI
    # ============================================================
    try:
        if args.mixed_bins == "subset":
            mixed_tps = subset_sorted
        else:
            mixed_tps = sorted(
                df["timepoint"].dropna().astype(str).str.strip().str.lower().unique().tolist(),
                key=tp_sort_key,
            )

        mixed_df = stats_reporting.compute_mixedlm_contrasts(
            df_patients=df,
            donors=donors,
            timepoints=mixed_tps,
            correction="bh",
            diagnostics_dir=diagnostics_dir / "mixedlm",
        )

        # Always save updated mixed contrasts CSV into <out_root>/results/
        mixed_csv = str(results_dir / "cfDNA_mixedlm_timepoint_contrasts_log10_bh.csv")
        mixed_df.to_csv(mixed_csv, index=False)
        print(f"mixedlm contrasts CSV saved: {mixed_csv}")

        if args.mixed_table:
            mixed_df.to_csv(args.mixed_table, index=False)
            print(f"mixedlm contrasts saved: {os.path.abspath(args.mixed_table)}")
        try:
            with pd.ExcelWriter(args.out_excel, engine="openpyxl", mode="a", if_sheet_exists="replace") as w:
                mixed_df.to_excel(w, sheet_name="MixedContrasts", index=False)
            print(f"mixedlm contrasts added to Excel: {os.path.abspath(args.out_excel)} (sheet MixedContrasts)")
        except Exception as e:
            print(f"warning: could not append mixedlm contrasts to Excel: {e}")

        # --- Sensitivity checks (optional) ---
        sens_dir = diagnostics_dir / "mixedlm_sensitivity"

        if args.mixed_random_slope_sensitivity:
            try:
                rs_df = stats_reporting.mixedlm_random_slope_time_sensitivity(
                    df_patients=df,
                    timepoints=mixed_tps,
                    correction="bh",
                    diagnostics_dir=sens_dir / "random_slope_time",
                )
                rs_csv = str(results_dir / "cfDNA_mixedlm_random_slope_time_contrasts_log10_bh.csv")
                rs_df.to_csv(rs_csv, index=False)
                print(f"mixedlm random-slope sensitivity CSV saved: {rs_csv}")
            except Exception as e:
                print(f"warning: random-slope sensitivity failed: {e}")

        if args.mixed_outlier_drop_n and args.mixed_outlier_drop_n > 0:
            try:
                outlier = stats_reporting.mixedlm_outlier_drop_sensitivity(
                    df_patients=df,
                    donors=donors,
                    timepoints=mixed_tps,
                    correction="bh",
                    drop_n=int(args.mixed_outlier_drop_n),
                )

                removed_csv = str(results_dir / f"cfDNA_mixedlm_outlier_drop{args.mixed_outlier_drop_n}_removed_observations.csv")
                outlier["removed_observations"].to_csv(removed_csv, index=False)

                refit_csv = str(results_dir / f"cfDNA_mixedlm_outlier_drop{args.mixed_outlier_drop_n}_contrasts_log10_bh.csv")
                outlier["contrasts_refit"].to_csv(refit_csv, index=False)

                cmp_csv = str(results_dir / f"cfDNA_mixedlm_outlier_drop{args.mixed_outlier_drop_n}_contrasts_vs_base.csv")
                outlier["contrasts_comparison"].to_csv(cmp_csv, index=False)

                print(f"mixedlm outlier-drop sensitivity saved: {removed_csv}, {refit_csv}, {cmp_csv}")
            except Exception as e:
                print(f"warning: outlier-drop sensitivity failed: {e}")
    except Exception as e:
        print(f"warning: mixedlm contrasts failed: {e}")

    # -------- T-tests (kept to the original three pairs) --------
    print("\n=== T-TEST RESULTS ===")
    group = {
        "Control":   df_plot[df_plot["timepoint"]=="Control"]["ng/ml plasma"],
        "Diagnosis": df_plot[df_plot["timepoint"]=="diag"]["ng/ml plasma"],
        "TP1":       df_plot[df_plot["timepoint"]=="tp1"]["ng/ml plasma"],
    }
    for (a,b) in [("Control","Diagnosis"), ("Control","TP1"), ("Diagnosis","TP1")]:
        if len(group[a]) > 1 and len(group[b]) > 1:
            stat, pval = ttest_ind(group[a], group[b], equal_var=False)
            if pval < 0.001: level = "*** (p < 0.001)"
            elif pval < 0.01: level = "** (p < 0.01)"
            elif pval < 0.05: level = "* (p < 0.05)"
            else: level = "ns (not significant)"
            print(f"{a} vs {b}: t = {stat:.3f}, p = {pval:.4e} → {level}")
        else:
            print(f"{a} vs {b}: insufficient data for t-test")

if __name__ == "__main__":
    main()
