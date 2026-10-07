import numpy as np
import pandas as pd
import pytest

from analysis.blast_kinetics.preprocessing import DataValidationError, prepare_data


def source(rows):
    return pd.DataFrame(rows, columns=["id", "time", "measurement", "category"])


def generic_config(configurable, **updates):
    defaults = {
        "columns__subject": "id",
        "columns__time": "time",
        "columns__value": "measurement",
        "columns__group": "category",
        "grouping__aliases": {"old": "A"},
        "grouping__colors": {"A": "#000000"},
        "grouping__unknown_policy": "error",
        "time__minimum": 1,
        "time__maximum": 3,
        "time__minimum_measurements": 2,
        "normalization__baseline_time": 1,
        "normalization__output_baseline": 100,
    }
    defaults.update(updates)
    return configurable(**defaults)


def test_percent_baseline_normalization_filters_cohort_and_preserves_zero(configurable):
    config = generic_config(configurable)
    raw = source([
        ("valid", 1, 10, " old "),
        ("valid", 2, 0, "old"),
        ("outside", 1, 10, "A"),
        ("outside", 5, 2, "A"),
        ("zero", 1, 0, "A"),
        ("zero", 2, 1, "A"),
        ("missing", 2, 1, "A"),
    ])

    prepared = prepare_data(raw, config)

    assert set(prepared.frame["subject_id"]) == {"valid"}
    assert prepared.frame.loc[prepared.frame["time"].eq(2), "analysis_value"].item() == 0
    assert set(prepared.frame["group"]) == {"A"}
    assert prepared.summary["analysis_rows"] == 2
    assert np.isfinite(prepared.frame["analysis_value"]).all()


def test_raw_mode_uses_measurement_without_requiring_baseline(configurable):
    config = generic_config(configurable, normalization__mode="none")
    raw = source([("a", 2, 3.5, "A"), ("a", 3, 4.5, "A")])

    prepared = prepare_data(raw, config)

    assert prepared.frame["analysis_value"].tolist() == [3.5, 4.5]


def test_rejects_duplicate_subject_time(configurable):
    config = generic_config(configurable)
    raw = source([("a", 1, 10, "A"), ("a", 1, 11, "A")])

    with pytest.raises(DataValidationError, match="duplicate subject/time"):
        prepare_data(raw, config)


def test_rejects_unknown_eligible_group(configurable):
    config = generic_config(configurable)
    raw = source([("a", 1, 10, "unknown"), ("a", 2, 5, "unknown")])

    with pytest.raises(DataValidationError, match="without configured colors"):
        prepare_data(raw, config)


def test_rejects_inconsistent_group_without_exposing_subject_in_message(configurable):
    config = generic_config(configurable)
    raw = source([("secret-name", 1, 10, "A"), ("secret-name", 2, 5, "old")])
    config["grouping"]["aliases"] = {}
    config["grouping"]["colors"]["old"] = "#111111"

    with pytest.raises(DataValidationError) as error:
        prepare_data(raw, config)
    assert "secret-name" not in str(error.value)


def test_rejects_missing_or_nonnumeric_required_values(configurable):
    config = generic_config(configurable)
    raw = source([("a", 1, 10, "A"), ("a", "bad", 5, "A")])

    with pytest.raises(DataValidationError, match="nonnumeric required"):
        prepare_data(raw, config)
