import numpy as np
import pandas as pd
import pytest

from analysis.blast_kinetics.statistics import bootstrap_daily_median_ci, predict_time_trend


def test_bootstrap_is_reproducible_and_omits_sparse_times(blast_config):
    data = pd.DataFrame({
        "time": [1, 1, 1, 2],
        "analysis_value": [50.0, 100.0, 150.0, 25.0],
    })
    config = blast_config
    config["bootstrap"]["resamples"] = 500

    lower, upper = bootstrap_daily_median_ci(data, [1, 2, 3], config)
    lower_again, upper_again = bootstrap_daily_median_ci(data, [1, 2, 3], config)

    pd.testing.assert_series_equal(lower, lower_again)
    pd.testing.assert_series_equal(upper, upper_again)
    assert lower[1] <= 100 <= upper[1]
    assert np.isnan(lower[2]) and np.isnan(upper[2])


def test_baseline_anchored_prediction_uses_unmodified_slope(blast_config):
    params = pd.Series({"Intercept": 3.0, "time_centered": -0.25})

    prediction = predict_time_trend(params, np.array([1, 2]), blast_config)

    assert prediction[0] == pytest.approx(100)
    assert prediction[1] == pytest.approx(np.exp(np.log(100.1) - 0.25) - 0.1)


def test_unanchored_raw_prediction_uses_fitted_intercept(configurable):
    config = configurable(
        normalization__mode="none",
        analysis__model__response_transform="none",
        analysis__model__anchor_at_baseline=False,
    )
    params = pd.Series({"Intercept": 10.0, "time_centered": 2.0})

    prediction = predict_time_trend(params, np.array([1, 2]), config)

    assert prediction.tolist() == [10.0, 12.0]
