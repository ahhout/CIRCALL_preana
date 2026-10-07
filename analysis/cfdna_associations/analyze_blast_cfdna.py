#!/usr/bin/env python3
"""Run one-variable OLS regressions with log10(cfDNA) as the outcome."""

from __future__ import annotations

import argparse
import logging
import math
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import statsmodels.api as sm
import statsmodels.formula.api as smf
from openpyxl import load_workbook
from scipy import stats
from statsmodels.stats.multitest import multipletests


# Compatibility imports: scientific methods are owned by the shared module.
from analysis.association_methods import (
    PredictorConfig, PREDICTORS, DEFAULT_PREDICTORS, select_predictors, add_predictor_argument,
    prepare_analysis_data, _status_results, fit_regression, model_diagnostics,
    _save_figure, plot_assumptions, spearman_sensitivity,
)

LOGGER = logging.getLogger("cfdna_v2")

DEFAULT_PATIENT_COLUMNS = ("lastname", "firstname", "dob")
REQUIRED_ANALYSIS_COLUMNS = (
    "sample_id",
    "treatment_phase",
    "tissue",
    "tube",
    "nucleic_acid",
    "cytology",
    "cytospin_%",
    "sex",
    "age_diag",
    "genetic_subtype",
    "GB_per_L",
    "cfDNA_ng_per_mL_plasma",
)


@dataclass(frozen=True)
class CohortConfig:
    patient_columns: tuple[str, ...] = DEFAULT_PATIENT_COLUMNS
    phase: str = "diag"
    blood_tissue: str = "Sang"
    marrow_tissue: str = "Moelle"
    nucleic_acid: str = "cfDNA"
    tube: str = "Roche"


PREDICTOR_TISSUES = {
    'peripheral_blast_percent': 'Peripheral blood',
    'gb_per_l': 'Peripheral blood',
    'tumor_fraction_percent': 'Bone marrow',
    'peripheral_blast_count': 'Peripheral blood',
    'marrow_blast_count': 'Bone marrow',
}


def normalized_text(series: pd.Series) -> pd.Series:
    """Normalize text used for filtering without changing source values."""
    return series.astype("string").str.strip().str.casefold()


def validate_columns(
    data: pd.DataFrame, patient_columns: Sequence[str] = DEFAULT_PATIENT_COLUMNS
) -> None:
    required = set(REQUIRED_ANALYSIS_COLUMNS) | set(patient_columns)
    missing = sorted(required.difference(data.columns))
    if missing:
        raise ValueError(f"Input is missing required columns: {', '.join(missing)}")


def load_dataset(
    input_path: Path,
    sheet_name: str,
    patient_columns: Sequence[str] = DEFAULT_PATIENT_COLUMNS,
) -> pd.DataFrame:
    """Load cached Excel values or a delimited text file."""
    if not input_path.exists():
        raise FileNotFoundError(f"Input file does not exist: {input_path}")

    suffix = input_path.suffix.lower()
    if suffix in {".xlsx", ".xlsm"}:
        workbook = load_workbook(
            input_path, read_only=True, data_only=True, keep_links=False
        )
        if sheet_name not in workbook.sheetnames:
            workbook.close()
            raise ValueError(
                f"Sheet {sheet_name!r} was not found. "
                f"Available sheets: {', '.join(workbook.sheetnames)}"
            )
        worksheet = workbook[sheet_name]
        rows = worksheet.iter_rows(values_only=True)
        try:
            header = list(next(rows))
        except StopIteration as exc:
            workbook.close()
            raise ValueError(f"Sheet {sheet_name!r} is empty") from exc

        duplicate_headers = [
            column
            for column in set(header)
            if column is not None and header.count(column) > 1
        ]
        if duplicate_headers:
            workbook.close()
            raise ValueError(
                "Input contains duplicate column names: "
                + ", ".join(sorted(duplicate_headers))
            )

        requested = set(REQUIRED_ANALYSIS_COLUMNS) | set(patient_columns)
        available = {column for column in header if column is not None}
        missing = sorted(requested.difference(available))
        if missing:
            workbook.close()
            raise ValueError(
                f"Input is missing required columns: {', '.join(missing)}"
            )
        positions = {column: header.index(column) for column in requested}
        records = [
            {column: row[index] for column, index in positions.items()}
            for row in rows
        ]
        workbook.close()
        data = pd.DataFrame.from_records(records, columns=sorted(requested))
    elif suffix == ".csv":
        data = pd.read_csv(input_path)
    elif suffix in {".tsv", ".txt"}:
        data = pd.read_csv(input_path, sep="\t")
    else:
        raise ValueError(
            "Unsupported input format. Use .xlsx, .xlsm, .csv, .tsv, or .txt."
        )

    validate_columns(data, patient_columns)
    return data


def _normalize_patient_component(series: pd.Series, is_date: bool) -> pd.Series:
    if is_date:
        parsed = pd.to_datetime(series, errors="coerce", format="mixed")
        return parsed.dt.strftime("%Y-%m-%d").astype("string")
    return normalized_text(series)


def _numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series, errors="coerce").replace([np.inf, -np.inf], np.nan)


def _join_sample_ids(series: pd.Series) -> str:
    sample_ids = sorted(
        {
            str(value).strip()
            for value in series.dropna()
            if str(value).strip()
            and str(value).strip().casefold() not in {"na", "n/a", "none"}
        }
    )
    return ";".join(sample_ids)


def _first_nonmissing_text(series: pd.Series) -> object:
    values = series.astype("string").str.strip()
    values = values.loc[
        values.notna() & ~values.str.casefold().isin({"", "na", "n/a", "none"})
    ]
    return values.iat[0] if not values.empty else pd.NA


def prepare_cohort(
    data: pd.DataFrame, config: CohortConfig
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Filter, aggregate, and match the patient-level data."""
    validate_columns(data, config.patient_columns)
    working = data.copy()

    key_parts = []
    for column in config.patient_columns:
        is_date = column.casefold() in {"dob", "date_of_birth", "birth_date"}
        key_parts.append(_normalize_patient_component(working[column], is_date))
    missing_key = pd.concat(key_parts, axis=1).isna().any(axis=1)
    working["_patient_key"] = list(zip(*(part.fillna("") for part in key_parts)))

    phase_mask = normalized_text(working["treatment_phase"]).eq(
        config.phase.strip().casefold()
    )
    diagnostic = working.loc[phase_mask & ~missing_key].copy()

    cytology = _numeric(diagnostic["cytology"])
    cytospin = _numeric(diagnostic["cytospin_%"])
    blast_fraction = cytology.fillna(cytospin)
    observed_blast_fraction = blast_fraction.dropna()
    if ((observed_blast_fraction < 0) | (observed_blast_fraction > 1)).any():
        raise ValueError(
            "Numeric cytology and cytospin_% values must be fractions between 0 and 1 "
            "before conversion to percentage points."
        )
    diagnostic["_blast_percent"] = blast_fraction * 100.0
    diagnostic["_yield"] = _numeric(diagnostic["cfDNA_ng_per_mL_plasma"])
    diagnostic["_age_diag"] = _numeric(diagnostic["age_diag"])
    diagnostic["_gb_per_l"] = _numeric(diagnostic["GB_per_L"])

    tissue = normalized_text(diagnostic["tissue"])
    nucleic_acid = normalized_text(diagnostic["nucleic_acid"])
    tube = normalized_text(diagnostic["tube"])

    blood_mask = (
        tissue.eq(config.blood_tissue.strip().casefold())
        & nucleic_acid.eq(config.nucleic_acid.strip().casefold())
        & tube.eq(config.tube.strip().casefold())
    )
    marrow_mask = tissue.eq(config.marrow_tissue.strip().casefold())

    blood_rows = diagnostic.loc[blood_mask]
    marrow_rows = diagnostic.loc[marrow_mask]

    blood = blood_rows.groupby("_patient_key", sort=True).agg(
        blood_sample_ids=("sample_id", _join_sample_ids),
        peripheral_blast_percent=("_blast_percent", "median"),
        cfdna_ng_per_ml=("_yield", "median"),
        sex=("sex", _first_nonmissing_text),
        age_diag=("_age_diag", "median"),
        blood_row_count=("_patient_key", "size"),
    )
    marrow = marrow_rows.groupby("_patient_key", sort=True).agg(
        marrow_sample_ids=("sample_id", _join_sample_ids),
        tumor_fraction_percent=("_blast_percent", "median"),
        marrow_row_count=("_patient_key", "size"),
    )
    clinical = diagnostic.groupby("_patient_key", sort=True).agg(
        genetic_subtype=("genetic_subtype", _first_nonmissing_text),
        gb_per_l=("_gb_per_l", "median"),
    )

    cohort = blood.join(marrow, how="left").join(clinical, how="left").reset_index(
        drop=True
    )
    cohort.insert(0, "observation", np.arange(1, len(cohort) + 1))
    matched = blood.join(marrow, how="inner")
    complete_mask = matched[
        [
            "peripheral_blast_percent",
            "cfdna_ng_per_ml",
            "tumor_fraction_percent",
        ]
    ].notna().all(axis=1)
    complete = matched.loc[complete_mask]
    counts = {
        "input_rows": int(len(data)),
        "rows_missing_patient_key": int(missing_key.sum()),
        "phase_rows_with_patient_key": int(len(diagnostic)),
        "blood_candidate_rows": int(len(blood_rows)),
        "marrow_candidate_rows": int(len(marrow_rows)),
        "blood_patients": int(len(blood)),
        "marrow_patients": int(len(marrow)),
        "matched_patients": int(len(matched)),
        "patients_excluded_incomplete": int((~complete_mask).sum()),
        "patients_with_nonpositive_yield": int((complete["cfdna_ng_per_ml"] <= 0).sum()),
        "analysis_patients": int(len(complete)),
        "blood_patients_with_repeated_rows": int((blood["blood_row_count"] > 1).sum()),
        "marrow_patients_with_repeated_rows": int(
            (marrow["marrow_row_count"] > 1).sum()
        ),
    }
    if len(cohort) == 0:
        raise ValueError("No diagnostic blood cfDNA patients remain after filtering.")
    return cohort, counts


def _format_p_value(value: float) -> str:
    if not np.isfinite(value):
        return "NA"
    return "<0.001" if value < 0.001 else f"{value:.3f}"


def plot_continuous(
    analysis: pd.DataFrame,
    predictor: PredictorConfig,
    model: object,
    output_path: Path,
    sensitivity=None,
) -> None:
    x_values = np.linspace(
        analysis[predictor.variable].min(), analysis[predictor.variable].max(), 200
    )
    grid = pd.DataFrame({predictor.variable: x_values})
    inference = model.get_robustcov_results(cov_type="HC3") if predictor.robust_se else model
    predictions = inference.get_prediction(grid).summary_frame(alpha=0.05)
    ci_label = "95% CI (HC3)" if predictor.robust_se else "95% CI"
    label = (
        f"OLS fit: R2={model.rsquared:.3f}; inference in results table"
    )

    figure, axis = plt.subplots(figsize=(7.4, 5.4))
    axis.scatter(
        analysis[predictor.variable],
        analysis["log10_cfDNA"],
        color="#2864a5",
        edgecolor="white",
        alpha=0.85,
        label=f"Patients (n={len(analysis)})",
    )
    axis.plot(x_values, predictions["mean"], color="#b33b2e", label=label)
    axis.fill_between(
        x_values,
        predictions["mean_ci_lower"],
        predictions["mean_ci_upper"],
        color="#b33b2e",
        alpha=0.18,
        label=ci_label,
    )
    axis.set(
        xlabel=predictor.label,
        ylabel="log10(cfDNA yield [ng/mL plasma])",
        title=f"log10(cfDNA) vs {predictor.label.lower()}",
    )
    if sensitivity and sensitivity['spearman_status'] == 'computed':
        axis.text(.02, .98, f"Spearman sensitivity: rho={sensitivity['spearman_rho']:.3f}; "
                  f"approx. p={sensitivity['spearman_p_value']:.3g}",
                  transform=axis.transAxes, va='top', fontsize=9,
                  bbox=dict(facecolor='white', alpha=.85, edgecolor='none'))
    axis.legend(loc="best")
    axis.grid(alpha=0.2)
    _save_figure(figure, output_path)


def plot_categorical(
    analysis: pd.DataFrame,
    predictor: PredictorConfig,
    model: object,
    output_path: Path,
) -> None:
    categories = sorted(analysis[predictor.variable].dropna().astype(str).unique())
    positions = np.arange(1, len(categories) + 1)
    grouped = [
        analysis.loc[
            analysis[predictor.variable].astype(str).eq(category), "log10_cfDNA"
        ].to_numpy()
        for category in categories
    ]
    prediction_data = pd.DataFrame({predictor.variable: categories})
    predictions = model.get_prediction(prediction_data).summary_frame(alpha=0.05)
    label = (
        f"Fitted means: R2={model.rsquared:.3f}; inference in results table"
    )

    figure, axis = plt.subplots(figsize=(max(7.4, len(categories) * 0.8), 5.6))
    axis.boxplot(grouped, positions=positions, widths=0.55, showfliers=False)
    rng = np.random.default_rng(123)
    for position, values in zip(positions, grouped, strict=True):
        jitter = rng.normal(0, 0.045, size=len(values))
        axis.scatter(
            np.full(len(values), position) + jitter,
            values,
            color="#2864a5",
            edgecolor="white",
            alpha=0.85,
            s=34,
        )
    axis.errorbar(
        positions,
        predictions["mean"],
        yerr=[
            predictions["mean"] - predictions["mean_ci_lower"],
            predictions["mean_ci_upper"] - predictions["mean"],
        ],
        fmt="D",
        color="#b33b2e",
        capsize=4,
        label=label,
    )
    axis.set(
        xlabel=predictor.label,
        ylabel="log10(cfDNA yield [ng/mL plasma])",
        title=f"log10(cfDNA) by {predictor.label.lower()}",
        xticks=positions,
        xticklabels=categories,
    )
    axis.tick_params(axis="x", rotation=35)
    axis.legend(loc="best")
    axis.grid(axis="y", alpha=0.2)
    _save_figure(figure, output_path)


def _safe_analysis_columns(analysis: pd.DataFrame, predictor: PredictorConfig) -> list[str]:
    columns = [
        "cohort",
        "observation",
        "blood_sample_ids",
        "marrow_sample_ids",
        "cfdna_ng_per_ml",
        "log10_cfDNA",
        predictor.variable,
    ]
    return [column for column in columns if column in analysis.columns]


def write_predictor_outputs(cohort, predictor, output_root, *, spearman_enabled=True):
    output_dir = output_root / predictor.output_name
    assumptions_dir = output_dir / 'assumptions'
    assumptions_dir.mkdir(parents=True, exist_ok=True)
    analysis = prepare_analysis_data(cohort, predictor)
    analysis.loc[:, _safe_analysis_columns(analysis, predictor)].to_csv(output_dir / 'analysis_data.csv', index=False)
    model, results = fit_regression(analysis, predictor)
    sensitivity = (spearman_sensitivity(analysis, predictor)
                   if spearman_enabled and predictor.variable == 'peripheral_blast_percent' else {})
    if model is None:
        for key, value in sensitivity.items():
            results[key] = value
        pd.DataFrame([dict(status='skipped', note=results.reason.iat[0])]).to_csv(assumptions_dir/'diagnostics.csv', index=False)
        return results
    model_diagnostics(model).to_csv(assumptions_dir/'diagnostics.csv', index=False)
    if predictor.kind == 'continuous':
        results = results.loc[results.term.eq(predictor.variable)].copy()
        increment = 10.0 if predictor.variable.endswith('_percent') else 1.0
        results['predictor_increment'] = increment
        for source, target in [('coefficient', 'fold_change'), ('ci95_low', 'ci95_low_fc'), ('ci95_high', 'ci95_high_fc')]:
            results[target] = np.power(10., results[source] * increment)
        plot_continuous(analysis, predictor, model, output_dir/predictor.figure_name, sensitivity=sensitivity)
    else:
        # One omnibus question, not a battery of reference-category tests.
        results = results.iloc[[0]].copy()
        results['term'] = 'overall predictor'
        results['p_value'] = results['f_p_value']
        results[['coefficient', 'ci95_low', 'ci95_high']] = np.nan
        plot_categorical(analysis, predictor, model, output_dir/predictor.figure_name)
    plot_assumptions(model, assumptions_dir)
    columns = ['status', 'reason', 'predictor', 'formula', 'standard_error_type', 'n', 'term',
               'coefficient', 'ci95_low', 'ci95_high', 'p_value', 'df_resid',
               'predictor_increment', 'fold_change', 'ci95_low_fc', 'ci95_high_fc']
    for key, value in sensitivity.items():
        results[key] = value
    return results.reindex(columns=columns + list(sensitivity))


def write_descriptive_predictor(cohort, predictor, output_root):
    """Keep every clinical question visible independently of hypothesis selection."""
    output = output_root / predictor.output_name
    output.mkdir(parents=True, exist_ok=True)
    data = prepare_analysis_data(cohort, predictor)
    data.loc[:, _safe_analysis_columns(data, predictor)].to_csv(output/'analysis_data.csv', index=False)
    fig, ax = plt.subplots(figsize=(7.4 if predictor.kind == 'continuous' else 10, 5.4))
    rows = []
    if predictor.kind == 'continuous':
        x, y = data[predictor.variable].to_numpy(), data.log10_cfDNA.to_numpy()
        if 'cohort' in data and data.cohort.nunique()>1:
            colors={'retrospective':'#4C78A8','circall':'#F58518'}
            for cohort,group in data.groupby('cohort',sort=True):
                ax.scatter(group[predictor.variable],group.log10_cfDNA,color=colors[cohort],edgecolor='white',alpha=.85,label=f'{cohort.capitalize()} (n={len(group)})')
        else:
            ax.scatter(x,y,color='#2864a5',edgecolor='white',alpha=.85,label=f'Patients (n={len(data)})')
        summary = dict(predictor=predictor.variable, n=len(data), status='descriptive' if len(data) else 'unavailable',
                       reason='' if len(data) else 'No complete positive cfDNA/predictor pairs')
        if len(data) >= 2 and np.ptp(x) > 0:
            slope, intercept = np.polyfit(x,y,1)
            grid = np.linspace(x.min(),x.max(),200)
            trend, = ax.plot(grid,intercept+slope*grid,color='#b33b2e',label='Descriptive linear trend')
            summary.update(slope_log10_per_unit=float(slope),intercept_log10=float(intercept))
            if np.ptp(y) > 0:
                summary.update(pearson_r=float(np.corrcoef(x,y)[0,1]),
                    spearman_rho=float(pd.Series(x).rank().corr(pd.Series(y).rank())))
                trend.set_label(f"Descriptive linear trend; Pearson r = {summary['pearson_r']:.3f}; "
                                f"Spearman ρ = {summary['spearman_rho']:.3f}")
        rows.append(summary)
        ax.legend(frameon=False)
    else:
        categories = sorted(data[predictor.variable].astype(str).unique())
        rng = np.random.default_rng(123)
        for position, category in enumerate(categories,1):
            group = data.loc[data[predictor.variable].astype(str).eq(category)]
            values = group.log10_cfDNA.to_numpy()
            ax.boxplot([values],positions=[position],widths=.55,showfliers=False)
            if 'cohort' in group and data.cohort.nunique()>1:
                colors={'retrospective':'#4C78A8','circall':'#F58518'}
                for cohort,part in group.groupby('cohort',sort=True):
                    ax.scatter(position+rng.normal(0,.045,len(part)),part.log10_cfDNA,color=colors[cohort],edgecolor='white',alpha=.85,label=cohort.capitalize() if position==1 else None)
            else:
                ax.scatter(position+rng.normal(0,.045,len(values)),values,color='#2864a5',edgecolor='white',alpha=.85)
            rows.append(dict(predictor=predictor.variable,category=category,n=len(group),status='descriptive',reason='',
                median_cfDNA=group.cfdna_ng_per_ml.median(),q1_cfDNA=group.cfdna_ng_per_ml.quantile(.25),
                q3_cfDNA=group.cfdna_ng_per_ml.quantile(.75)))
        ax.set_xticks(range(1,len(categories)+1),[f'{c}\n(n={len(data.loc[data[predictor.variable].astype(str).eq(c)])})' for c in categories])
        ax.tick_params(axis='x',rotation=35)
        if 'cohort' in data and data.cohort.nunique()>1:
            from matplotlib.lines import Line2D
            ax.legend(handles=[Line2D([],[],marker='o',linestyle='',color=color,label=name) for name,color in [('Retrospective','#4C78A8'),('Circall','#F58518')]])
        if not rows:
            rows.append(dict(predictor=predictor.variable,n=0,status='unavailable',reason='No complete positive cfDNA/predictor pairs'))
    if data.empty:
        ax.text(.5,.5,'No complete observations',transform=ax.transAxes,ha='center')
    ax.set(xlabel=predictor.label,ylabel='log10(cfDNA yield [ng/mL plasma])',
           title=f'log10(cfDNA) vs {predictor.label.lower()} — descriptive')
    ax.grid(alpha=.2)
    _save_figure(fig,output/predictor.figure_name)
    description = pd.DataFrame(rows)
    description['predictor_label'] = predictor.label
    description['predictor_tissue'] = PREDICTOR_TISSUES.get(predictor.variable, 'Not tissue-specific')
    description['cfdna_specimen'] = 'Blood plasma'
    description.to_csv(output/'descriptive_summary.csv',index=False)


def descriptive_predictors(cohort):
    rows = []
    for predictor in PREDICTORS:
        # Descriptions do not inherit log-model positivity requirements.
        available = cohort.loc[cohort[predictor.variable].notna()]
        groups = available.groupby(predictor.variable, sort=True) if predictor.kind == 'categorical' else [('Overall', available)]
        for category, group in groups:
            values = group[predictor.variable] if predictor.kind == 'continuous' else group.cfdna_ng_per_ml
            rows.append(dict(predictor=predictor.variable, category=category, n=len(group),
                missing_predictor=int(cohort[predictor.variable].isna().sum()),
                summary_variable=predictor.variable if predictor.kind == 'continuous' else 'cfdna_ng_per_ml',
                median=values.median(), q1=values.quantile(.25), q3=values.quantile(.75)))
    return pd.DataFrame(rows)


def write_outputs(output_dir, cohort, counts, overwrite=False, predictors=None, *,
                  descriptive_only=False, view_predictors=None, spearman_enabled=True):
    selected = () if descriptive_only else select_predictors(predictors)
    views = PREDICTORS if view_predictors is None else view_predictors
    if output_dir.exists():
        if not overwrite and any(output_dir.iterdir()):
            raise FileExistsError(f'Output directory is not empty: {output_dir}. Use a fresh destination.')
        if overwrite:
            shutil.rmtree(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    pd.DataFrame([{'metric': metric, 'count': count} for metric, count in counts.items()], columns=['metric','count']).to_csv(output_dir/'cohort_summary.csv', index=False)
    descriptive_predictors(cohort).to_csv(output_dir/'predictor_descriptions.csv', index=False)
    for predictor in views:
        if predictor.variable not in {p.variable for p in selected}:
            write_descriptive_predictor(cohort, predictor, output_dir)
    tables = [write_predictor_outputs(cohort, predictor, output_dir, spearman_enabled=spearman_enabled) for predictor in selected]
    # Include every prespecified predictor in the family; unavailable tests use p=1
    # for adjustment only and remain unavailable in exported results.
    pvalues = [float(table.p_value.iat[0]) if table.status.iat[0] == 'fit' else 1.0 for table in tables]
    adjusted = multipletests(pvalues, method='fdr_bh')[1] if pvalues else []
    for predictor, table, p_adj in zip(selected, tables, adjusted, strict=True):
        table['p_adj_bh'] = p_adj if table.status.iat[0] == 'fit' else np.nan
        table['predictor_label'] = predictor.label
        table['predictor_tissue'] = PREDICTOR_TISSUES.get(predictor.variable, 'Not tissue-specific')
        table['cfdna_specimen'] = 'Blood plasma'
        table['correction'] = 'BH across selected predictor tests'
        table['inference'] = 'single-predictor association; no covariate adjustment or causal interpretation'
        table.to_csv(output_dir/predictor.output_name/'results.csv', index=False)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run v2.0 one-variable OLS regressions against log10(cfDNA)."
    )
    add_predictor_argument(parser)
    parser.add_argument("input", type=Path, help="Input .xlsx, .csv, .tsv, or .txt")
    parser.add_argument(
        "--sheet",
        default="Inventaire",
        help="Worksheet name for Excel input (default: Inventaire)",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output/y_cfDNA"),
        help="Output directory (default: output/y_cfDNA)",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Replace existing generated v2.0 output directory.",
    )
    parser.add_argument("--phase", default="diag", help="Treatment phase filter")
    parser.add_argument("--blood-tissue", default="Sang", help="Blood tissue label")
    parser.add_argument("--marrow-tissue", default="Moelle", help="Marrow tissue label")
    parser.add_argument(
        "--nucleic-acid", default="cfDNA", help="Blood nucleic acid filter"
    )
    parser.add_argument("--tube", default="Roche", help="Blood tube filter")
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level",
    )
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(levelname)s: %(message)s",
    )
    try:
        config = CohortConfig(
            phase=args.phase,
            blood_tissue=args.blood_tissue,
            marrow_tissue=args.marrow_tissue,
            nucleic_acid=args.nucleic_acid,
            tube=args.tube,
        )
        data = load_dataset(args.input, args.sheet, config.patient_columns)
        cohort, counts = prepare_cohort(data, config)
        write_outputs(args.output_dir, cohort, counts, overwrite=args.overwrite, predictors=args.predictors, spearman_enabled=args.spearman_sensitivity)
    except Exception as exc:
        LOGGER.error("%s", exc)
        return 1

    LOGGER.info("Wrote v2.0 cfDNA outputs to %s", args.output_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
