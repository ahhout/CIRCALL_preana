from dataclasses import dataclass

import numpy as np
import pandas as pd


class DataValidationError(ValueError):
    """Raised when source data violates an analysis requirement."""


@dataclass(frozen=True)
class PreparedData:
    frame: pd.DataFrame
    summary: dict


def _numeric(series, decimal):
    return pd.to_numeric(
        series.astype(str).str.replace(decimal, ".", regex=False),
        errors="coerce",
    )


def prepare_data(source, config):
    """Map source columns and create a validated generic analysis cohort."""
    columns = config["columns"]
    required_sources = [columns["subject"], columns["time"], columns["value"]]
    if columns.get("group"):
        required_sources.append(columns["group"])
    missing = sorted(set(required_sources) - set(source.columns))
    if missing:
        raise DataValidationError(f"Input is missing configured columns: {missing}")

    rename = {
        columns["subject"]: "subject_id",
        columns["time"]: "time",
        columns["value"]: "value",
    }
    if columns.get("group"):
        rename[columns["group"]] = "group"
    data = source[list(rename)].rename(columns=rename).copy()
    if "group" not in data:
        data["group"] = "All"

    decimal = config["input"].get("decimal", ".")
    data["subject_id"] = data["subject_id"].astype("string").str.strip()
    data["subject_id"] = data["subject_id"].mask(data["subject_id"].eq(""))
    data["time"] = _numeric(data["time"], decimal)
    data["value"] = _numeric(data["value"], decimal)
    data["group"] = data["group"].astype("string").str.strip()
    data["group"] = data["group"].mask(data["group"].eq(""))

    invalid_required = data[["subject_id", "time", "value", "group"]].isna().any(axis=1)
    if invalid_required.any():
        raise DataValidationError(
            f"{int(invalid_required.sum())} rows have missing or nonnumeric required values"
        )
    if not np.isfinite(data[["time", "value"]].to_numpy()).all():
        raise DataValidationError("Input contains nonfinite time or measurement values")

    aliases = config["grouping"]["aliases"]
    data["group"] = data["group"].replace(aliases)

    time_config = config["time"]
    data = data[data["time"].between(time_config["minimum"], time_config["maximum"])].copy()
    rows_in_window = len(data)
    if data.empty:
        raise DataValidationError("No observations remain inside the configured time window")

    duplicates = data.duplicated(["subject_id", "time"], keep=False)
    if duplicates.any():
        raise DataValidationError(
            f"{int(duplicates.sum())} rows are duplicate subject/time observations"
        )

    initial_subjects = int(data["subject_id"].nunique())
    excluded_missing_baseline = 0
    excluded_nonpositive_baseline = 0
    normalization = config["normalization"]

    if normalization["mode"] == "percent_of_baseline":
        baseline_time = normalization["baseline_time"]
        baseline_rows = data[data["time"].eq(baseline_time)]
        baselines = baseline_rows.set_index("subject_id")["value"]
        missing_subjects = set(data["subject_id"].unique()) - set(baselines.index)
        nonpositive_subjects = set(baselines[baselines.le(0)].index)
        excluded_missing_baseline = len(missing_subjects)
        excluded_nonpositive_baseline = len(nonpositive_subjects)
        if missing_subjects and normalization["missing_baseline_policy"] == "error":
            raise DataValidationError(
                f"{len(missing_subjects)} subjects lack the configured baseline"
            )
        if nonpositive_subjects and normalization["nonpositive_baseline_policy"] == "error":
            raise DataValidationError(
                f"{len(nonpositive_subjects)} subjects have a nonpositive baseline"
            )
        eligible_baselines = baselines[baselines.gt(0)]
        data = data[data["subject_id"].isin(eligible_baselines.index)].copy()
        data["analysis_value"] = (
            data["value"] / data["subject_id"].map(eligible_baselines)
            * normalization["output_baseline"]
        )
    else:
        data["analysis_value"] = data["value"]

    counts = data["subject_id"].value_counts()
    eligible = counts[counts.ge(time_config["minimum_measurements"])].index
    excluded_too_few = int(data.loc[~data["subject_id"].isin(eligible), "subject_id"].nunique())
    data = data[data["subject_id"].isin(eligible)].copy()
    if data.empty:
        raise DataValidationError("No subjects satisfy the configured cohort requirements")

    if not np.isfinite(data["analysis_value"]).all():
        raise DataValidationError("Normalization produced nonfinite analysis values")

    if config["grouping"]["require_constant_per_subject"]:
        inconsistent = data.groupby("subject_id")["group"].nunique().gt(1)
        if inconsistent.any():
            raise DataValidationError(
                f"{int(inconsistent.sum())} subjects have inconsistent group labels"
            )

    configured_colors = config["grouping"]["colors"]
    unknown_groups = sorted(set(data["group"].unique()) - set(configured_colors))
    if unknown_groups and config["grouping"]["unknown_policy"] == "error":
        raise DataValidationError(
            f"Eligible data contain groups without configured colors: {unknown_groups}"
        )

    data = data.sort_values(["subject_id", "time"]).reset_index(drop=True)
    group_subject_counts = {
        str(group): int(part["subject_id"].nunique())
        for group, part in data.groupby("group", sort=True)
    }
    summary = {
        "input_rows": int(len(source)),
        "rows_in_time_window": rows_in_window,
        "analysis_rows": int(len(data)),
        "subjects_in_time_window": initial_subjects,
        "analysis_subjects": int(data["subject_id"].nunique()),
        "excluded_missing_baseline_subjects": excluded_missing_baseline,
        "excluded_nonpositive_baseline_subjects": excluded_nonpositive_baseline,
        "excluded_too_few_measurements_subjects": excluded_too_few,
        "subjects_by_group": group_subject_counts,
    }
    return PreparedData(frame=data, summary=summary)
