"""Shared diagnosis association methods; no workbook preparation or row exports."""
from __future__ import annotations
from analysis.figure_layout import remove_plot_text

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

def influence_diagnostics(model):
    """Diagnostic values only where residual variance is numerically defined.

    Unit leverage is possible for singleton categories. A dimension-scaled
    floating-point tolerance treats rounding around one consistently; it is not
    an observation exclusion or a model-fitting threshold.
    """
    leverage = np.asarray(model.get_influence().hat_matrix_diag)
    residuals = np.asarray(model.resid)
    variance = float(model.mse_resid)
    tolerance = np.finfo(float).eps * max(model.model.exog.shape) * 8
    valid = np.isfinite(leverage) & (leverage >= 0) & (1 - leverage > tolerance)
    valid &= np.isfinite(residuals) & np.isfinite(variance) & (variance > 0)
    standardized = np.full(residuals.shape, np.nan)
    cooks = np.full(residuals.shape, np.nan)
    if valid.any():
        standardized[valid] = residuals[valid] / np.sqrt(variance) / np.sqrt(1 - leverage[valid])
        cooks[valid] = standardized[valid] ** 2 / model.model.exog.shape[1]
        cooks[valid] *= leverage[valid] / (1 - leverage[valid])
    return leverage, standardized, cooks


def model_diagnostics(model):
    """Aggregate residual/influence checks; no additional hypothesis tests."""
    leverage, standardized, cooks = influence_diagnostics(model)
    result = dict(status='review', n=int(model.nobs), df_resid=float(model.df_resid),
        max_leverage=float(np.max(leverage)),
        max_cooks_distance=float(np.max(cooks[np.isfinite(cooks)])) if np.isfinite(cooks).any() else np.nan,
        note='Review residual, Q-Q and influence diagnostics; no automatic assumption-test selection')
    unavailable = int((~np.isfinite(standardized)).sum())
    if unavailable:
        result.update(undefined_studentized_residuals=unavailable,
                      undefined_cooks_distances=int((~np.isfinite(cooks)).sum()))
        result['note'] += '; unit leverage or unavailable residual variance makes some influence diagnostics undefined; model observations retained'
    return pd.DataFrame([result])

def _save_figure(figure: plt.Figure, output_path: Path) -> None:
    from analysis.plot_style import save_figure
    remove_plot_text(figure)
    figure.tight_layout()
    save_figure(figure, output_path)
    plt.close(figure)

def plot_assumptions(model: object, output_dir: Path, *, outcome_label: str = 'cfDNA', cohort: str | None = None) -> None:
    from analysis.plot_style import COHORT_COLORS, COHORT_MARKERS, INK, style_axes, save_figure
    color = COHORT_COLORS[cohort] if cohort else '#2864a5'
    marker = COHORT_MARKERS[cohort] if cohort else 'o'
    from analysis.plot_style import scatter_points, point_handles
    frame = model.model.data.frame
    centers = (frame.loc[model.model.data.row_labels, 'center'].fillna('unknown').to_numpy()
               if cohort == 'circall' and 'center' in frame else None)
    def scatter(axis, x, y, selected=None, **kwargs):
        if centers is not None:
            scatter_points(axis, x, y, cohort, centers if selected is None else centers[selected],
                           circall_only=True, **kwargs)
        else:
            axis.scatter(x, y, color=color, marker=marker, **kwargs)
    def save(figure, path):
        if cohort:
            if centers is not None:
                figure.axes[0].legend(handles=point_handles(cohort,centers,circall_only=True),frameon=False)
            style_axes(figure.axes[0])
            figure.tight_layout()
            save_figure(figure,path)
            plt.close(figure)
        else:
            _save_figure(figure,path)
    fitted = np.asarray(model.fittedvalues)
    residuals = np.asarray(model.resid)
    _, standardized, _ = influence_diagnostics(model)

    figure, axis = plt.subplots(figsize=(6.8, 5.0))
    scatter(axis, fitted, residuals, edgecolor="white", alpha=0.8)
    axis.axhline(0, color="#333333", linewidth=1)
    axis.set(
        xlabel=f"Fitted log10({outcome_label})",
        ylabel="Residuals",
        title="Residuals vs fitted values",
    )
    axis.grid(alpha=0.2)
    save(figure, output_dir / "residuals_vs_fitted.png")

    figure = sm.qqplot(residuals, line="45", fit=True)
    axis = figure.axes[0]
    axis.set_title("Q-Q plot of residuals")
    if cohort:
        axis.lines[0].set(color=color,marker=marker,markeredgecolor='white',alpha=.8)
        axis.lines[1].set(color=INK,linewidth=1)
        if centers is not None:
            qq = axis.lines[0]
            x, y = qq.get_xdata(), qq.get_ydata()
            qq.set_visible(False)
            scatter(axis, x, y, selected=np.argsort(residuals), edgecolor='white', alpha=.8)
    save(figure, output_dir / "qq_plot.png")

    figure, axis = plt.subplots(figsize=(6.8, 5.0))
    usable = np.isfinite(standardized)
    scatter(
        axis, fitted[usable],
        np.sqrt(np.abs(standardized[usable])),
        selected=usable,
        edgecolor="white",
        alpha=0.85,
    )
    if not usable.all():
        axis.text(.02, .98, f'Undefined studentized residuals: {int((~usable).sum())}; model observations retained',
                  transform=axis.transAxes, va='top', fontsize=8, wrap=True)
    axis.set(
        xlabel=f"Fitted log10({outcome_label})",
        ylabel="sqrt(|standardized residuals|)",
        title="Scale-location plot",
    )
    axis.grid(alpha=0.2)
    save(figure, output_dir / "scale_location.png")

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
