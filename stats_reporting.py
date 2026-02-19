#!/usr/bin/env python3
"""Stats utilities for cfDNA_inventory.

This module contains the statistical testing/modeling used by analysis.py.
Keeping it separate makes the plotting/IO script easier to read and maintain.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import norm, ttest_ind


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


def holm_adjust(pvals: np.ndarray) -> np.ndarray:
    """Holm–Bonferroni family-wise error adjustment."""
    pvals = np.asarray(pvals, dtype=float)
    out = np.full_like(pvals, np.nan, dtype=float)
    ok = np.isfinite(pvals)
    if not ok.any():
        return out

    p = pvals[ok]
    m = p.size
    order = np.argsort(p)
    ranked = p[order]
    adj = (m - np.arange(m)) * ranked
    adj = np.maximum.accumulate(adj)
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

    if correction == "bh":
        out["p_adj_bh"] = bh_adjust(out["p_value"].to_numpy(dtype=float))
        out["signif"] = out["p_adj_bh"].map(stars)
    else:
        out["p_adj_bh"] = np.nan
        out["signif"] = out["p_value"].map(stars)

    return out


def compute_mixedlm_contrasts(
    *,
    df_patients: pd.DataFrame,
    donors: pd.DataFrame,
    timepoints: list[str],
    correction: str,  # 'none' | 'bh' | 'holm' | 'tukey'
) -> pd.DataFrame:
    """Fit MixedLM on log10(cfDNA) with patient random intercept and compute contrasts.

    Returns a long table with all pairwise contrasts.
    """

    import statsmodels.formula.api as smf
    from patsy import dmatrix

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

    if correction == "bh":
        out["p_adj"] = bh_adjust(out["p_value"].to_numpy(dtype=float))
    elif correction == "holm":
        out["p_adj"] = holm_adjust(out["p_value"].to_numpy(dtype=float))
    elif correction == "tukey":
        out["p_adj"] = tukey_style_adjust(
            out["p_value"].to_numpy(dtype=float),
            out["z"].to_numpy(dtype=float),
            k=len(cats),
        )
    else:
        out["p_adj"] = out["p_value"]

    out["signif"] = out["p_adj"].map(stars)
    out["correction"] = correction
    out["model"] = "mixedlm_log10_random_intercept"
    return out
