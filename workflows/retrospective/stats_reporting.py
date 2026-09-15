#!/usr/bin/env python3
"""Stats utilities for cfDNA_inventory.

This module contains the statistical testing/modeling used by analysis.py.
Keeping it separate makes the plotting/IO script easier to read and maintain.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import mannwhitneyu, norm, probplot, ttest_ind


def stars(p: float) -> str:
    if not np.isfinite(p):
        return ""
    if p < 0.001:
        return "***"
    if p < 0.01:
        return "**"
    if p < 0.05:
        return "*"
    return "ns"


def bh_adjust(pvals: np.ndarray) -> np.ndarray:
    """Benjamini–Hochberg FDR adjustment."""
    pvals = np.asarray(pvals, dtype=float)
    out = np.full_like(pvals, np.nan, dtype=float)
    ok = np.isfinite(pvals)
    if not ok.any():
        return out

    p = pvals[ok]
    m = p.size
    order = np.argsort(p)
    ranked = p[order]
    adj = ranked * m / (np.arange(1, m + 1))
    adj = np.minimum.accumulate(adj[::-1])[::-1]
    adj = np.clip(adj, 0.0, 1.0)

    inv = np.empty_like(order)
    inv[order] = np.arange(m)
    out[ok] = adj[inv]
    return out


def tukey_style_adjust(pvals: np.ndarray, zvals: np.ndarray, k: int) -> np.ndarray:
    """Approximate Tukey adjustment using studentized range, df=inf.

    MixedLM does not provide exact Tukey HSD for marginal means.
    This uses a z-based studentized range approximation.
    """
    try:
        from statsmodels.stats.libqsturng import psturng
    except Exception:
        return np.asarray(pvals, dtype=float)

    zvals = np.asarray(zvals, dtype=float)
    out = np.full_like(zvals, np.nan, dtype=float)
    ok = np.isfinite(zvals)
    if not ok.any():
        return out

    q = np.abs(zvals[ok]) * np.sqrt(2.0)
    padj = 1.0 - psturng(q, k, np.inf)
    out[ok] = np.clip(padj, 0.0, 1.0)
    return out

def compute_pairwise_bins(
    *,
    df_patients: pd.DataFrame,
    donors: pd.DataFrame,
    bins: list[str],
    unit: str,
    scale: str,
    correction: str,
) -> pd.DataFrame:
    """Pairwise Welch t-tests between bins.

    Parameters
    - df_patients: columns: lastname, timepoint, ng_per_ml (patient samples)
    - donors: columns: timepoint ('Control'), ng/ml plasma
    - bins: e.g. ['Control','diag','tp0,5','tp1','tp2']
    """

    def bin_values(tp: str) -> pd.DataFrame:
        if tp == "Control":
            out = donors[["ng/ml plasma"]].copy()
            out["lastname"] = pd.NA
            out = out.rename(columns={"ng/ml plasma": "value"})
            return out
        tmp = df_patients[["lastname", "timepoint", "ng_per_ml"]].copy()
        tmp["timepoint"] = tmp["timepoint"].astype(str).str.strip().str.lower()
        tmp = tmp[tmp["timepoint"] == str(tp).lower()].copy()
        tmp = tmp.rename(columns={"ng_per_ml": "value"})
        return tmp[["lastname", "value"]]

    if scale != "log10":
        raise ValueError("Pairwise tests must use log10 scale (enforced).")
    if correction != "bh":
        raise ValueError("Pairwise tests must use BH correction (enforced).")

    bin_frames: dict[str, pd.DataFrame] = {}
    for b in bins:
        bdf = bin_values(b)
        bdf["value"] = pd.to_numeric(bdf["value"], errors="coerce")
        bdf = bdf[np.isfinite(bdf["value"].to_numpy(dtype=float))].copy()

        if scale == "log10":
            bdf = bdf[bdf["value"] > 0].copy()
            bdf["value"] = np.log10(bdf["value"].to_numpy(dtype=float))

        if unit == "patient_median" and b != "Control":
            bdf = bdf.dropna(subset=["lastname"]).copy()
            bdf = bdf.groupby("lastname", as_index=False)["value"].median()

        bin_frames[b] = bdf

    rows: list[dict] = []
    for i in range(len(bins)):
        for j in range(i + 1, len(bins)):
            a, b = bins[i], bins[j]
            va = bin_frames[a]["value"].to_numpy(dtype=float)
            vb = bin_frames[b]["value"].to_numpy(dtype=float)
            na = int(np.isfinite(va).sum())
            nb = int(np.isfinite(vb).sum())

            stat = np.nan
            pval = np.nan
            if na >= 2 and nb >= 2:
                stat, pval = ttest_ind(va, vb, equal_var=False, nan_policy="omit")

            rows.append(
                {
                    "bin_a": a,
                    "bin_b": b,
                    "n_a": na,
                    "n_b": nb,
                    "test": "welch_ttest",
                    "scale": scale,
                    "unit": unit,
                    "t_stat": float(stat) if np.isfinite(stat) else np.nan,
                    "p_value": float(pval) if np.isfinite(pval) else np.nan,
                }
            )

    out = pd.DataFrame(rows)
    if len(out) == 0:
        out["p_adj_bh"] = []
        out["signif"] = []
        return out

    out["p_adj_bh"] = bh_adjust(out["p_value"].to_numpy(dtype=float))
    out["signif"] = out["p_adj_bh"].map(stars)

    return out


def cliffs_delta(a: np.ndarray, b: np.ndarray) -> float:
    """Cliff's delta effect size.

    Returns a value in [-1, 1], where +1 means all a > b, -1 means all a < b.
    """

    a = np.asarray(a, dtype=float)
    b = np.asarray(b, dtype=float)
    a = a[np.isfinite(a)]
    b = b[np.isfinite(b)]
    if a.size == 0 or b.size == 0:
        return np.nan

    # O(n*m) but n,m are small here (patient-median bins).
    gt = (a[:, None] > b[None, :]).sum()
    lt = (a[:, None] < b[None, :]).sum()
    denom = a.size * b.size
    if denom == 0:
        return np.nan
    return float((gt - lt) / denom)


def compute_mannwhitney_bins(
    *,
    df_patients: pd.DataFrame,
    donors: pd.DataFrame,
    bins: list[str],
    unit: str,
    scale: str,
    correction: str,
    alternative: str = "two-sided",
    method: str = "auto",
    report_effect_size: bool = True,
) -> pd.DataFrame:
    """Pairwise Mann–Whitney U tests between bins (nonparametric sensitivity check).

    Settings are intentionally aligned with the main workflow:
    - scale: log10 (enforced)
    - unit: patient_median (enforced; avoids pseudo-replication)
    - correction: BH (enforced)
    - alternative: two-sided
    - method: auto
    """

    def bin_values(tp: str) -> pd.DataFrame:
        if tp == "Control":
            out = donors[["ng/ml plasma"]].copy()
            out["lastname"] = pd.NA
            out = out.rename(columns={"ng/ml plasma": "value"})
            return out
        tmp = df_patients[["lastname", "timepoint", "ng_per_ml"]].copy()
        tmp["timepoint"] = tmp["timepoint"].astype(str).str.strip().str.lower()
        tmp = tmp[tmp["timepoint"] == str(tp).lower()].copy()
        tmp = tmp.rename(columns={"ng_per_ml": "value"})
        return tmp[["lastname", "value"]]

    if scale != "log10":
        raise ValueError("Mann–Whitney tests must use log10 scale (enforced).")
    if unit != "patient_median":
        raise ValueError("Mann–Whitney tests must use patient_median unit (enforced).")
    if correction != "bh":
        raise ValueError("Mann–Whitney tests must use BH correction (enforced).")
    if alternative not in {"two-sided", "less", "greater"}:
        raise ValueError(f"Invalid alternative: {alternative}")
    if method not in {"auto", "exact", "asymptotic"}:
        raise ValueError(f"Invalid method: {method}")

    bin_frames: dict[str, pd.DataFrame] = {}
    for b in bins:
        bdf = bin_values(b)
        bdf["value"] = pd.to_numeric(bdf["value"], errors="coerce")
        bdf = bdf[np.isfinite(bdf["value"].to_numpy(dtype=float))].copy()

        # log10 transform (monotone; Mann–Whitney ranks are invariant, but we do
        # it for consistency with the rest of the pipeline).
        bdf = bdf[bdf["value"] > 0].copy()
        bdf["value"] = np.log10(bdf["value"].to_numpy(dtype=float))

        if b != "Control":
            bdf = bdf.dropna(subset=["lastname"]).copy()
            bdf = bdf.groupby("lastname", as_index=False)["value"].median()

        bin_frames[b] = bdf

    rows: list[dict] = []
    for i in range(len(bins)):
        for j in range(i + 1, len(bins)):
            a, b = bins[i], bins[j]
            va = bin_frames[a]["value"].to_numpy(dtype=float)
            vb = bin_frames[b]["value"].to_numpy(dtype=float)
            na = int(np.isfinite(va).sum())
            nb = int(np.isfinite(vb).sum())

            u_stat = np.nan
            pval = np.nan
            if na >= 1 and nb >= 1:
                # SciPy supports method=... on recent versions; keep fallback
                # for older versions.
                try:
                    res = mannwhitneyu(va, vb, alternative=alternative, method=method)
                except TypeError:
                    res = mannwhitneyu(va, vb, alternative=alternative)
                u_stat = float(res.statistic) if np.isfinite(res.statistic) else np.nan
                pval = float(res.pvalue) if np.isfinite(res.pvalue) else np.nan

            row = {
                "bin_a": a,
                "bin_b": b,
                "n_a": na,
                "n_b": nb,
                "test": "mannwhitneyu",
                "scale": scale,
                "unit": unit,
                "alternative": alternative,
                "method": method,
                "u_stat": u_stat,
                "p_value": pval,
            }
            if report_effect_size:
                cd = cliffs_delta(va, vb)
                row["cliffs_delta"] = cd
                row["abs_cliffs_delta"] = float(abs(cd)) if np.isfinite(cd) else np.nan
            rows.append(row)

    out = pd.DataFrame(rows)
    if len(out) == 0:
        out["p_adj_bh"] = []
        out["signif"] = []
        return out

    out["p_adj_bh"] = bh_adjust(out["p_value"].to_numpy(dtype=float))
    out["signif"] = out["p_adj_bh"].map(stars)
    return out


def write_pairwise_log10_diagnostics(
    *,
    df_patients: pd.DataFrame,
    donors: pd.DataFrame,
    bins: list[str],
    out_dir: Path,
) -> None:
    """Write per-bin histograms and Q-Q plots of log10(ng_per_ml).

    This helps check the normality assumption behind Welch's t-test.
    """

    import matplotlib.pyplot as plt

    out_dir.mkdir(parents=True, exist_ok=True)

    for b in bins:
        if b == "Control":
            series = pd.to_numeric(donors.get("ng/ml plasma"), errors="coerce")
        else:
            tmp = df_patients[["timepoint", "ng_per_ml"]].copy()
            tmp["timepoint"] = tmp["timepoint"].astype(str).str.strip().str.lower()
            tmp = tmp[tmp["timepoint"] == str(b).lower()]
            series = pd.to_numeric(tmp["ng_per_ml"], errors="coerce")

        vals = series.to_numpy(dtype=float)
        vals = vals[np.isfinite(vals) & (vals > 0)]
        if vals.size == 0:
            continue
        logv = np.log10(vals)

        safe_name = str(b).replace("/", "_")

        # Histogram
        plt.figure(figsize=(6, 4))
        plt.hist(logv, bins=min(30, max(5, int(np.sqrt(logv.size)))), edgecolor="black", alpha=0.85)
        plt.title(f"Histogram: log10(ng_per_ml) — {b} (n={logv.size})")
        plt.xlabel("log10(ng_per_ml)")
        plt.ylabel("count")
        plt.tight_layout()
        plt.savefig(out_dir / f"hist_log10_{safe_name}.png", dpi=200)
        plt.close()

        # Q-Q plot
        plt.figure(figsize=(5, 5))
        (osm, osr), (slope, intercept, r) = probplot(logv, dist="norm")
        plt.scatter(osm, osr, s=18, alpha=0.85)
        x = np.asarray(osm)
        plt.plot(x, slope * x + intercept, color="black", linewidth=1)
        plt.title(f"Q-Q: log10(ng_per_ml) — {b} (n={logv.size})")
        plt.xlabel("theoretical quantiles")
        plt.ylabel("ordered values")
        plt.tight_layout()
        plt.savefig(out_dir / f"qq_log10_{safe_name}.png", dpi=200)
        plt.close()


def compute_mixedlm_contrasts(
    *,
    df_patients: pd.DataFrame,
    donors: pd.DataFrame,
    timepoints: list[str],
    correction: str,  # enforced 'bh'
    diagnostics_dir: Path | None = None,
) -> pd.DataFrame:
    """Fit MixedLM on log10(cfDNA) with patient random intercept and compute contrasts.

    Returns a long table with all pairwise contrasts.
    """

    if correction != "bh":
        raise ValueError("MixedLM contrasts must use BH correction (enforced).")

    res, d, cats = _fit_mixedlm_random_intercept_categorical(
        df_patients=df_patients,
        donors=donors,
        timepoints=timepoints,
    )
    out = _mixedlm_contrasts_from_fit(res=res, d=d, cats=cats, correction=correction)

    if diagnostics_dir is not None:
        write_mixedlm_diagnostics(res=res, diagnostics_dir=diagnostics_dir)
    return out


def _fit_mixedlm(model):
    last_err = None
    res = None
    for method in ("lbfgs", "powell", "nm"):
        try:
            res = model.fit(method=method, reml=False, disp=False)
            break
        except Exception as e:
            last_err = e
    if res is None:
        raise last_err
    return res


def _fit_mixedlm_random_intercept_categorical(*, df_patients: pd.DataFrame, donors: pd.DataFrame, timepoints: list[str]):
    import statsmodels.formula.api as smf

    pat = df_patients[["lastname", "timepoint", "ng_per_ml"]].copy()
    pat["timepoint"] = pat["timepoint"].astype(str).str.strip().str.lower()
    pat = pat[pat["timepoint"].isin([tp.lower() for tp in timepoints])].copy()
    pat = pat.rename(columns={"lastname": "patient", "ng_per_ml": "cfdna"})

    ctrl = donors[["ng/ml plasma"]].copy()
    ctrl = ctrl.rename(columns={"ng/ml plasma": "cfdna"})
    ctrl["timepoint"] = "Control"
    ctrl["patient"] = [f"Control_{i:05d}" for i in range(len(ctrl))]

    d = pd.concat([ctrl[["patient", "timepoint", "cfdna"]], pat[["patient", "timepoint", "cfdna"]]], ignore_index=True)
    d["cfdna"] = pd.to_numeric(d["cfdna"], errors="coerce")
    d = d[np.isfinite(d["cfdna"].to_numpy(dtype=float))].copy()
    d = d[d["cfdna"] > 0].copy()
    d["log10_cfdna"] = np.log10(d["cfdna"].to_numpy(dtype=float))

    cats = ["Control"] + list(timepoints)
    d["timepoint"] = pd.Categorical(d["timepoint"], categories=cats, ordered=True)

    model = smf.mixedlm(
        "log10_cfdna ~ 0 + C(timepoint)",
        data=d,
        groups=d["patient"],
        re_formula="1",
    )
    res = _fit_mixedlm(model)
    return res, d, cats


def _mixedlm_contrasts_from_fit(*, res, d: pd.DataFrame, cats: list[str], correction: str) -> pd.DataFrame:
    from patsy import dmatrix

    cov_fe = getattr(res, "cov_fe", None)
    if cov_fe is None:
        k_fe = len(res.fe_params)
        cov_all = res.cov_params()
        cov_fe = np.asarray(cov_all)[:k_fe, :k_fe]
    else:
        cov_fe = np.asarray(cov_fe)

    design_info = res.model.data.design_info
    exog_by_tp: dict[str, np.ndarray] = {}
    mean_by_tp: dict[str, float] = {}
    for tp in cats:
        X = dmatrix(design_info, pd.DataFrame({"timepoint": [tp]}), return_type="dataframe")
        x = X.iloc[0].to_numpy(dtype=float)
        exog_by_tp[tp] = x
        mean_by_tp[tp] = float(np.dot(x, res.fe_params.to_numpy(dtype=float)))

    rows: list[dict] = []
    fe = res.fe_params.to_numpy(dtype=float)
    for i in range(len(cats)):
        for j in range(i + 1, len(cats)):
            a, b = cats[i], cats[j]
            c = exog_by_tp[b] - exog_by_tp[a]
            delta = float(np.dot(c, fe))
            se = float(np.sqrt(np.dot(c, np.dot(cov_fe, c))))
            z = delta / se if se > 0 else np.nan
            p = 2.0 * (1.0 - norm.cdf(abs(z))) if np.isfinite(z) else np.nan
            ci_low = delta - 1.96 * se if np.isfinite(se) else np.nan
            ci_high = delta + 1.96 * se if np.isfinite(se) else np.nan

            rows.append(
                {
                    "timepoint_a": a,
                    "timepoint_b": b,
                    "mean_log10_a": mean_by_tp[a],
                    "mean_log10_b": mean_by_tp[b],
                    "delta_log10": delta,
                    "se": se,
                    "z": z,
                    "p_value": p,
                    "ci95_low_log10": ci_low,
                    "ci95_high_log10": ci_high,
                    "fold_change": float(10 ** delta) if np.isfinite(delta) else np.nan,
                    "ci95_low_fc": float(10 ** ci_low) if np.isfinite(ci_low) else np.nan,
                    "ci95_high_fc": float(10 ** ci_high) if np.isfinite(ci_high) else np.nan,
                }
            )

    out = pd.DataFrame(rows)
    if len(out) == 0:
        out["p_adj"] = []
        out["signif"] = []
        out["correction"] = correction
        out["model"] = "mixedlm_log10_random_intercept"
        return out

    out["p_adj"] = bh_adjust(out["p_value"].to_numpy(dtype=float))
    out["signif"] = out["p_adj"].map(stars)
    out["correction"] = correction
    out["model"] = "mixedlm_log10_random_intercept"
    return out


def _timepoint_to_ordered_time(tp: str) -> float:
    """Map common timepoint labels to a numeric time for sensitivity checks.

    Supported:
    - diag -> 0
    - tpN or tpN,5 (comma decimal) -> float
    Returns NaN if not parseable.
    """

    if tp is None:
        return float("nan")
    s = str(tp).strip().lower()
    if s == "diag":
        return 0.0
    if s.startswith("tp"):
        num = s[2:].strip().replace(",", ".")
        try:
            return float(num)
        except Exception:
            return float("nan")
    return float("nan")


def mixedlm_random_slope_time_sensitivity(
    *,
    df_patients: pd.DataFrame,
    timepoints: list[str],
    correction: str,
    diagnostics_dir: Path | None = None,
) -> pd.DataFrame:
    """Sensitivity model: (1 + ordered_time | patient) with fixed effects (1 + ordered_time).

    Patients only (Control excluded) because ordered_time is undefined for controls.
    """

    import statsmodels.formula.api as smf

    if correction != "bh":
        raise ValueError("Sensitivity MixedLM must use BH correction (enforced).")

    pat = df_patients[["lastname", "timepoint", "ng_per_ml"]].copy()
    pat["timepoint"] = pat["timepoint"].astype(str).str.strip().str.lower()
    pat = pat[pat["timepoint"].isin([tp.lower() for tp in timepoints])].copy()
    pat = pat.rename(columns={"lastname": "patient", "ng_per_ml": "cfdna"})

    pat["ordered_time"] = pat["timepoint"].map(_timepoint_to_ordered_time)
    pat["cfdna"] = pd.to_numeric(pat["cfdna"], errors="coerce")
    pat = pat[np.isfinite(pat["cfdna"].to_numpy(dtype=float)) & (pat["cfdna"] > 0)].copy()
    pat = pat[np.isfinite(pat["ordered_time"].to_numpy(dtype=float))].copy()
    pat["log10_cfdna"] = np.log10(pat["cfdna"].to_numpy(dtype=float))

    if pat.empty:
        return pd.DataFrame(
            columns=[
                "timepoint_a",
                "timepoint_b",
                "time_a",
                "time_b",
                "delta_log10",
                "se",
                "z",
                "p_value",
                "p_adj",
                "fold_change",
                "ci95_low_fc",
                "ci95_high_fc",
                "correction",
                "model",
            ]
        )

    model = smf.mixedlm(
        "log10_cfdna ~ 1 + ordered_time",
        data=pat,
        groups=pat["patient"],
        re_formula="1 + ordered_time",
    )
    res = _fit_mixedlm(model)

    # Only slope drives pairwise time differences
    fe = res.fe_params
    if "ordered_time" not in fe.index:
        raise RuntimeError("Random slope sensitivity fit did not include 'ordered_time' fixed effect")
    beta = float(fe["ordered_time"])

    cov_fe = getattr(res, "cov_fe", None)
    if cov_fe is None:
        k_fe = len(res.fe_params)
        cov_all = res.cov_params()
        cov_fe = np.asarray(cov_all)[:k_fe, :k_fe]
    else:
        cov_fe = np.asarray(cov_fe)

    fe_names = list(res.fe_params.index)
    idx = fe_names.index("ordered_time")
    var_beta = float(cov_fe[idx, idx])

    # build numeric time for each requested timepoint
    tp_times = [(tp, _timepoint_to_ordered_time(tp)) for tp in timepoints]
    tp_times = [(tp, t) for tp, t in tp_times if np.isfinite(t)]

    rows: list[dict] = []
    for i in range(len(tp_times)):
        for j in range(i + 1, len(tp_times)):
            a, ta = tp_times[i]
            b, tb = tp_times[j]
            dt = float(tb - ta)
            delta = beta * dt
            se = abs(dt) * float(np.sqrt(var_beta)) if var_beta >= 0 else np.nan
            z = delta / se if se and se > 0 else np.nan
            p = 2.0 * (1.0 - norm.cdf(abs(z))) if np.isfinite(z) else np.nan
            ci_low = delta - 1.96 * se if np.isfinite(se) else np.nan
            ci_high = delta + 1.96 * se if np.isfinite(se) else np.nan

            rows.append(
                {
                    "timepoint_a": a,
                    "timepoint_b": b,
                    "time_a": ta,
                    "time_b": tb,
                    "delta_log10": delta,
                    "se": se,
                    "z": z,
                    "p_value": p,
                    "ci95_low_log10": ci_low,
                    "ci95_high_log10": ci_high,
                    "fold_change": float(10 ** delta) if np.isfinite(delta) else np.nan,
                    "ci95_low_fc": float(10 ** ci_low) if np.isfinite(ci_low) else np.nan,
                    "ci95_high_fc": float(10 ** ci_high) if np.isfinite(ci_high) else np.nan,
                }
            )

    out = pd.DataFrame(rows)
    if len(out):
        out["p_adj"] = bh_adjust(out["p_value"].to_numpy(dtype=float))
        out["signif"] = out["p_adj"].map(stars)
        out["correction"] = correction
        out["model"] = "mixedlm_log10_random_slope_time"
        out["n_obs"] = int(pat.shape[0])
        out["n_patients"] = int(pat["patient"].nunique())

    if diagnostics_dir is not None:
        write_mixedlm_diagnostics(res=res, diagnostics_dir=diagnostics_dir)
        _write_random_slope_hist(res=res, diagnostics_dir=diagnostics_dir)

    return out


def _write_random_slope_hist(*, res, diagnostics_dir: Path) -> None:
    """If model has a random slope, also plot its distribution (patients only)."""

    import matplotlib.pyplot as plt

    diagnostics_dir.mkdir(parents=True, exist_ok=True)
    re = getattr(res, "random_effects", {})
    slopes = []
    for key, v in re.items():
        if str(key).startswith("Control_"):
            continue
        try:
            arr = np.asarray(v, dtype=float).reshape(-1)
            if arr.size >= 2:
                slopes.append(float(arr[1]))
        except Exception:
            continue
    slopes = np.asarray(slopes, dtype=float)
    slopes = slopes[np.isfinite(slopes)]
    if not slopes.size:
        return
    plt.figure(figsize=(6, 4))
    plt.hist(slopes, bins=min(30, max(5, int(np.sqrt(slopes.size)))), edgecolor="black", alpha=0.85)
    plt.title(f"MixedLM random slopes (ordered_time) (n={slopes.size})")
    plt.xlabel("random slope")
    plt.ylabel("count")
    plt.tight_layout()
    plt.savefig(diagnostics_dir / "mixedlm_random_slopes_hist.png", dpi=200)
    plt.close()


def mixedlm_outlier_drop_sensitivity(
    *,
    df_patients: pd.DataFrame,
    donors: pd.DataFrame,
    timepoints: list[str],
    correction: str,
    drop_n: int,
) -> dict[str, pd.DataFrame]:
    """Sensitivity check: drop the top-N absolute residual observations and refit once."""

    if drop_n <= 0:
        raise ValueError("drop_n must be >= 1")
    if correction != "bh":
        raise ValueError("Outlier sensitivity must use BH correction (enforced).")

    res0, d0, cats = _fit_mixedlm_random_intercept_categorical(
        df_patients=df_patients,
        donors=donors,
        timepoints=timepoints,
    )
    base = _mixedlm_contrasts_from_fit(res=res0, d=d0, cats=cats, correction=correction)

    resid = np.asarray(res0.resid)
    fitted = np.asarray(res0.fittedvalues)
    abs_resid = np.abs(resid)
    mask = np.isfinite(abs_resid)
    if not mask.any():
        raise RuntimeError("No finite residuals available for outlier sensitivity")

    idx_sorted = np.argsort(abs_resid[mask])[::-1]
    idx_all = np.flatnonzero(mask)
    drop_n = int(min(drop_n, idx_sorted.size))
    drop_idx = idx_all[idx_sorted[:drop_n]]

    removed = d0.iloc[drop_idx].copy()
    removed["fitted"] = fitted[drop_idx]
    removed["resid"] = resid[drop_idx]
    removed["abs_resid"] = abs_resid[drop_idx]

    d1 = d0.drop(index=d0.index[drop_idx]).copy()

    import statsmodels.formula.api as smf
    model1 = smf.mixedlm(
        "log10_cfdna ~ 0 + C(timepoint)",
        data=d1,
        groups=d1["patient"],
        re_formula="1",
    )
    res1 = _fit_mixedlm(model1)
    refit = _mixedlm_contrasts_from_fit(res=res1, d=d1, cats=cats, correction=correction)

    key_cols = ["timepoint_a", "timepoint_b"]
    cmp = base.merge(refit, on=key_cols, how="outer", suffixes=("_base", "_refit"))
    for c in ["delta_log10", "fold_change", "p_adj"]:
        cb = f"{c}_base"
        cr = f"{c}_refit"
        if cb in cmp.columns and cr in cmp.columns:
            cmp[f"diff_{c}"] = cmp[cr] - cmp[cb]

    return {
        "removed_observations": removed,
        "contrasts_base": base,
        "contrasts_refit": refit,
        "contrasts_comparison": cmp,
    }


def write_mixedlm_diagnostics(*, res, diagnostics_dir: Path) -> None:
    """Write MixedLM diagnostics plots.

    - Q-Q plot of residuals
    - Residuals vs fitted
    - Histogram of random intercepts (excluding pseudo Control_*)
    """

    import matplotlib.pyplot as plt

    diagnostics_dir.mkdir(parents=True, exist_ok=True)

    fitted = np.asarray(res.fittedvalues)
    resid = np.asarray(res.resid)

    # Q-Q residuals
    plt.figure(figsize=(5, 5))
    (osm, osr), (slope, intercept, r) = probplot(resid[np.isfinite(resid)], dist="norm")
    plt.scatter(osm, osr, s=12, alpha=0.85)
    x = np.asarray(osm)
    plt.plot(x, slope * x + intercept, color="black", linewidth=1)
    plt.title("MixedLM residuals Q-Q")
    plt.xlabel("theoretical quantiles")
    plt.ylabel("ordered residuals")
    plt.tight_layout()
    plt.savefig(diagnostics_dir / "mixedlm_resid_qq.png", dpi=200)
    plt.close()

    # Residuals vs fitted
    plt.figure(figsize=(6, 4))
    mask = np.isfinite(fitted) & np.isfinite(resid)
    plt.scatter(fitted[mask], resid[mask], s=12, alpha=0.6)
    plt.axhline(0.0, color="black", linewidth=1)
    plt.title("MixedLM residuals vs fitted")
    plt.xlabel("fitted values")
    plt.ylabel("residuals")
    plt.tight_layout()
    plt.savefig(diagnostics_dir / "mixedlm_resid_vs_fitted.png", dpi=200)
    plt.close()

    # Random effects histogram (random intercepts)
    re = getattr(res, "random_effects", {})
    vals = []
    for key, v in re.items():
        if str(key).startswith("Control_"):
            continue
        try:
            arr = np.asarray(v, dtype=float).reshape(-1)
            if arr.size:
                vals.append(float(arr[0]))
        except Exception:
            continue
    vals = np.asarray(vals, dtype=float)
    vals = vals[np.isfinite(vals)]
    if vals.size:
        plt.figure(figsize=(6, 4))
        plt.hist(vals, bins=min(30, max(5, int(np.sqrt(vals.size)))), edgecolor="black", alpha=0.85)
        plt.title(f"MixedLM random intercepts (patients) (n={vals.size})")
        plt.xlabel("random intercept")
        plt.ylabel("count")
        plt.tight_layout()
        plt.savefig(diagnostics_dir / "mixedlm_random_effects_hist.png", dpi=200)
        plt.close()
