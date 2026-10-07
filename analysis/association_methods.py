"""Shared diagnosis association methods; no workbook preparation or row exports."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf
from scipy import stats

@dataclass(frozen=True)
class PredictorConfig:
    variable: str
    label: str
    kind: str
    output_name: str
    robust_se: bool = False
    figure_name: str = ""

    def __post_init__(self):
        if not self.figure_name:
            object.__setattr__(self, "figure_name", f"log10_cfDNA_vs_{self.variable}.png")

    @property
    def formula_term(self) -> str:
        if self.kind == "categorical":
            return f"C({self.variable})"
        return self.variable

PREDICTORS = (
    PredictorConfig("sex", "Sex", "categorical", "cfDNA_sex"),
    PredictorConfig(
        "age_diag",
        "Age at diagnosis",
        "continuous",
        "cfDNA_age_diag",
        robust_se=True,
    ),
    PredictorConfig(
        "genetic_subtype",
        "Genetic subtype",
        "categorical",
        "cfDNA_genetic_subtype",
    ),
    PredictorConfig(
        "peripheral_blast_percent",
        "Peripheral blood blasts (%)",
        "continuous",
        "cfDNA_vs_peripheral_blood_blast_percent",
        robust_se=True,
        figure_name="log10_cfDNA_ng_per_mL_vs_peripheral_blood_blast_percent.png",
    ),
    PredictorConfig("gb_per_l", "Peripheral blood WBC count (source units)", "continuous", "cfDNA_vs_peripheral_blood_wbc_count", robust_se=True,
                    figure_name="log10_cfDNA_ng_per_mL_vs_peripheral_blood_wbc_count.png"),
    PredictorConfig(
        "tumor_fraction_percent",
        "Bone marrow blasts (%)",
        "continuous",
        "cfDNA_vs_bone_marrow_blast_percent",
        robust_se=True,
        figure_name="log10_cfDNA_ng_per_mL_vs_bone_marrow_blast_percent.png",
    ),
)

DEFAULT_PREDICTORS = ('peripheral_blast_percent',)

def select_predictors(names=None):
    names = list(DEFAULT_PREDICTORS if names is None else names)
    available = {p.variable: p for p in PREDICTORS}
    if not names or len(set(names)) != len(names) or set(names) - available.keys():
        raise ValueError('Predictors must be a nonempty unique selection of supported variables')
    return tuple(available[name] for name in names)

def add_predictor_argument(parser):
    parser.add_argument('--spearman-sensitivity', action=argparse.BooleanOptionalAction, default=True,
                        help='Add two-sided approximate Spearman sensitivity for selected peripheral blasts (default: enabled)')
    parser.add_argument('--predictors', nargs='+', choices=[p.variable for p in PREDICTORS],
                        default=list(DEFAULT_PREDICTORS),
                        help='Predictors selected for hypothesis testing; all six retain descriptive analyses and plots')

def prepare_analysis_data(
    cohort: pd.DataFrame, predictor: PredictorConfig
) -> pd.DataFrame:
    required = ["cfdna_ng_per_ml", predictor.variable]
    selected = cohort.loc[cohort[required].notna().all(axis=1)].copy()
    if (selected["cfdna_ng_per_ml"] <= 0).any():
        bad = int((selected["cfdna_ng_per_ml"] <= 0).sum())
        raise ValueError(
            f"{bad} complete {predictor.variable} analysis row(s) have non-positive "
            "cfDNA values; log10(cfDNA) cannot be computed without changing the data."
        )
    selected = selected.reset_index(drop=True)
    selected["observation"] = np.arange(1, len(selected) + 1)
    selected["log10_cfDNA"] = np.log10(selected["cfdna_ng_per_ml"])
    return selected

def _status_results(
    predictor: PredictorConfig, analysis: pd.DataFrame, status: str, reason: str
) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "status": status,
                "reason": reason,
                "predictor": predictor.variable,
                "formula": "",
                "standard_error_type": "HC3 robust"
                if predictor.robust_se
                else "conventional OLS",
                "n": len(analysis),
                "term": "",
                "coefficient": np.nan,
                "std_error": np.nan,
                "t_statistic": np.nan,
                "p_value": np.nan,
                "f_statistic": np.nan,
                "f_p_value": np.nan,
                "multiple_r_squared": np.nan,
                "adjusted_r_squared": np.nan,
                "aic": np.nan,
                "bic": np.nan,
                "df_resid": np.nan,
            }
        ]
    )

def fit_regression(
    analysis: pd.DataFrame, predictor: PredictorConfig
) -> tuple[object | None, pd.DataFrame]:
    if len(analysis) < 3:
        return None, _status_results(
            predictor,
            analysis,
            "skipped",
            "At least 3 complete observations are required.",
        )
    if analysis[predictor.variable].nunique(dropna=True) < 2:
        return None, _status_results(
            predictor,
            analysis,
            "skipped",
            "The predictor has fewer than 2 observed values.",
        )

    formula = f"log10_cfDNA ~ {predictor.formula_term}"
    model = smf.ols(formula, data=analysis).fit()
    if model.df_resid < 1:
        return None, _status_results(
            predictor,
            analysis,
            "skipped",
            "The fitted model has no residual degrees of freedom.",
        )

    inference = model.get_robustcov_results(cov_type="HC3") if predictor.robust_se else model
    if not np.isfinite(np.asarray(inference.bse)).all() or not np.isfinite(np.asarray(inference.pvalues)).all():
        return None, _status_results(predictor, analysis, 'skipped', 'Nonfinite regression uncertainty; insufficient information')
    confidence = np.asarray(inference.conf_int(alpha=0.05))
    terms = list(model.params.index)
    standard_errors = pd.Series(np.asarray(inference.bse), index=terms)
    t_statistics = pd.Series(np.asarray(inference.tvalues), index=terms)
    p_values = pd.Series(np.asarray(inference.pvalues), index=terms)

    rows = []
    for index, term in enumerate(terms):
        rows.append(
            {
                "status": "fit",
                "reason": "",
                "predictor": predictor.variable,
                "formula": formula,
                "standard_error_type": "HC3 robust"
                if predictor.robust_se
                else "conventional OLS",
                "n": int(model.nobs),
                "term": term,
                "coefficient": float(model.params[term]),
                "ci95_low": float(confidence[index, 0]),
                "ci95_high": float(confidence[index, 1]),
                "std_error": float(standard_errors[term]),
                "t_statistic": float(t_statistics[term]),
                "p_value": float(p_values[term]),
                "f_statistic": float(inference.fvalue)
                if inference.fvalue is not None
                else np.nan,
                "f_p_value": float(inference.f_pvalue)
                if inference.f_pvalue is not None
                else np.nan,
                "multiple_r_squared": float(model.rsquared),
                "adjusted_r_squared": float(model.rsquared_adj),
                "aic": float(model.aic),
                "bic": float(model.bic),
                "df_resid": float(model.df_resid),
            }
        )
    return model, pd.DataFrame(rows)

def model_diagnostics(model):
    """Aggregate residual/influence checks; no additional hypothesis tests."""
    influence = model.get_influence()
    return pd.DataFrame([dict(status='review', n=int(model.nobs), df_resid=float(model.df_resid),
        max_leverage=float(np.max(influence.hat_matrix_diag)),
        max_cooks_distance=float(np.nanmax(influence.cooks_distance[0])),
        note='Review residual, Q-Q and influence diagnostics; no automatic assumption-test selection')])

def _save_figure(figure: plt.Figure, output_path: Path) -> None:
    from analysis.figure_layout import legends_below
    figure.tight_layout()
    legends_below(figure)
    figure.savefig(output_path, dpi=300, bbox_inches="tight")
    plt.close(figure)

def plot_assumptions(model: object, output_dir: Path) -> None:
    fitted = np.asarray(model.fittedvalues)
    residuals = np.asarray(model.resid)
    standardized = model.get_influence().resid_studentized_internal

    figure, axis = plt.subplots(figsize=(6.8, 5.0))
    axis.scatter(fitted, residuals, color="#2864a5", edgecolor="white", alpha=0.85)
    axis.axhline(0, color="#333333", linewidth=1)
    axis.set(
        xlabel="Fitted log10(cfDNA)",
        ylabel="Residuals",
        title="Residuals vs fitted values",
    )
    axis.grid(alpha=0.2)
    _save_figure(figure, output_dir / "residuals_vs_fitted.png")

    figure = sm.qqplot(residuals, line="45", fit=True)
    axis = figure.axes[0]
    axis.set_title("Q-Q plot of residuals")
    _save_figure(figure, output_dir / "qq_plot.png")

    figure, axis = plt.subplots(figsize=(6.8, 5.0))
    axis.scatter(
        fitted,
        np.sqrt(np.abs(standardized)),
        color="#2864a5",
        edgecolor="white",
        alpha=0.85,
    )
    axis.set(
        xlabel="Fitted log10(cfDNA)",
        ylabel="sqrt(|standardized residuals|)",
        title="Scale-location plot",
    )
    axis.grid(alpha=0.2)
    _save_figure(figure, output_dir / "scale_location.png")

def spearman_sensitivity(analysis, predictor):
    """Two-sided rank sensitivity on the same complete patient pairs as OLS."""
    x, y = analysis[predictor.variable], analysis.log10_cfDNA
    result = dict(spearman_n=len(analysis), spearman_rho=np.nan, spearman_p_value=np.nan,
                  spearman_status='unavailable', spearman_reason='',
                  spearman_method='Two-sided scipy.stats.spearmanr; asymptotic p-value; average ranks for ties',
                  spearman_inference='Sensitivity only; unadjusted p-value; primary regression unchanged')
    if len(analysis) < 3 or x.nunique() < 2 or y.nunique() < 2:
        result['spearman_reason'] = 'Requires at least three complete pairs and nonconstant variables'
        return result
    rho, pvalue = stats.spearmanr(x, y, alternative='two-sided')
    result.update(spearman_status='computed', spearman_rho=float(rho), spearman_p_value=float(pvalue))
    return result
