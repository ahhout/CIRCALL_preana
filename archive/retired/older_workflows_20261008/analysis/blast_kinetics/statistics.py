from dataclasses import dataclass

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf
from scipy.stats.mstats import winsorize


class ModelError(RuntimeError):
    """Raised when the configured model cannot be fitted safely."""


@dataclass(frozen=True)
class FittedTrend:
    result: object
    frame: pd.DataFrame
    predictions: pd.DataFrame


def apply_winsorization(data, config):
    """Apply configured global tail winsorization to the model response only."""
    result = data.copy()
    settings = config["analysis"]["winsorization"]
    if settings["enabled"]:
        result["analysis_value"] = winsorize(
            result["analysis_value"],
            limits=(settings["lower_limit"], settings["upper_limit"]),
        ).data
    return result


def _inverse_transform(values, transform, offset):
    if transform == "log_offset":
        return np.exp(values) - offset
    return values


def predict_time_trend(params, time_grid, config):
    """Build configured display-scale predictions from fitted fixed effects."""
    settings = config["analysis"]["model"]
    transform = settings["response_transform"]
    offset = settings["log_offset"]
    centered = time_grid - settings["time_origin"]
    slope = params["time_centered"]
    if settings["anchor_at_baseline"]:
        anchor = config["normalization"]["output_baseline"]
        if transform == "log_offset":
            response = np.log(anchor + offset) + slope * centered
        else:
            response = anchor + slope * centered
    else:
        response = params["Intercept"] + slope * centered
    return _inverse_transform(response, transform, offset)


def fit_time_model(data, config):
    """Fit the supported random-intercept linear time model."""
    settings = config["analysis"]["model"]
    frame = apply_winsorization(data, config)
    origin = settings["time_origin"]
    frame["time_centered"] = frame["time"] - origin
    transform = settings["response_transform"]
    offset = settings["log_offset"]

    if transform == "log_offset":
        shifted = frame["analysis_value"] + offset
        if shifted.le(0).any():
            raise ModelError(
                "The model log offset does not make every analysis value positive"
            )
        frame["model_response"] = np.log(shifted)
    else:
        frame["model_response"] = frame["analysis_value"]

    try:
        result = smf.mixedlm(
            "model_response ~ time_centered",
            frame,
            groups=frame["subject_id"],
        ).fit()
    except (ValueError, np.linalg.LinAlgError) as exc:
        raise ModelError(f"Mixed model fitting failed: {exc}") from exc
    if not result.converged:
        raise ModelError("Mixed model did not converge")

    time_config = config["time"]
    grid = np.arange(
        time_config["minimum"],
        time_config["maximum"] + time_config["tick_step"] / 2,
        time_config["tick_step"],
    )
    predictions = pd.DataFrame({
        "time": grid,
        "predicted": predict_time_trend(result.params, grid, config),
    })
    return FittedTrend(result=result, frame=frame, predictions=predictions)


def bootstrap_daily_median_ci(data, time_points, config):
    """Return deterministic bootstrap bounds for the median at each time point."""
    settings = config["bootstrap"]
    rng = np.random.default_rng(settings["seed"])
    alpha = (1 - settings["confidence"]) / 2
    lower = pd.Series(np.nan, index=time_points, dtype=float)
    upper = pd.Series(np.nan, index=time_points, dtype=float)

    for time_point in time_points:
        values = data.loc[data["time"].eq(time_point), "analysis_value"].to_numpy()
        if len(values) < settings["minimum_observations"]:
            continue
        samples = rng.choice(
            values,
            size=(settings["resamples"], len(values)),
            replace=True,
        )
        medians = np.median(samples, axis=1)
        lower[time_point], upper[time_point] = np.quantile(
            medians, [alpha, 1 - alpha]
        )
    return lower, upper
