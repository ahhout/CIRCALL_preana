from pathlib import Path

import pandas as pd
import pytest
import yaml

from analysis.blast_kinetics.config import ConfigError, load_config
from analysis.blast_kinetics.data_io import InputDataError, load_input


ROOT = Path(__file__).resolve().parents[2]


def test_loads_and_resolves_blast_yaml():
    loaded = load_config(ROOT / "configs" / "blast_kinetics" / "blast_kinetics.yml")

    assert loaded.data["schema_version"] == 1
    assert Path(loaded.data["input"]["path"]).is_absolute()
    assert Path(loaded.data["output"]["root"]).is_absolute()


def test_rejects_incompatible_baseline_anchor(tmp_path):
    config = yaml.safe_load((ROOT / "configs" / "blast_kinetics" / "raw_measurement_example.yml").read_text())
    config["analysis"]["model"]["enabled"] = True
    config["analysis"]["model"]["anchor_at_baseline"] = True
    path = tmp_path / "invalid.yml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")

    with pytest.raises(ConfigError, match="anchoring requires"):
        load_config(path)


def test_reports_missing_plot_parameter_as_config_error(tmp_path):
    config = yaml.safe_load((ROOT / "configs" / "blast_kinetics" / "blast_kinetics.yml").read_text())
    del config["plots"]["scatter"]["marker_size"]
    path = tmp_path / "invalid.yml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")

    with pytest.raises(ConfigError, match="plots.scatter.marker_size"):
        load_config(path)


def test_csv_loader_uses_configured_delimiter_and_decimal(tmp_path, configurable):
    path = tmp_path / "measurements.csv"
    path.write_text("id;time;value;group\na;1;10,5;A\n", encoding="utf-8")
    config = configurable(
        input__path=str(path),
        input__format="csv",
        input__delimiter=";",
        input__decimal=",",
    )

    result = load_input(config)

    assert result.loc[0, "value"] == pytest.approx(10.5)


def test_loader_fails_cleanly_for_missing_input(configurable, tmp_path):
    config = configurable(input__path=str(tmp_path / "absent.xlsx"))

    with pytest.raises(InputDataError, match="does not exist"):
        load_input(config)


@pytest.mark.parametrize('section,key,value', [
    ('bootstrap', 'resamples', 2.5), ('bootstrap', 'seed', -1),
    ('time', 'minimum_measurements', True), ('time', 'minimum', float('nan')),
    ('normalization', 'baseline_time', float('nan')), ('analysis', 'model', None),
    ('grouping', 'require_constant_per_subject', 'true'),
])
def test_malformed_settings_fail_early(tmp_path, section, key, value):
    config = yaml.safe_load((ROOT / 'configs/blast_kinetics/blast_kinetics.yml').read_text())
    config[section][key] = value
    path = tmp_path / 'invalid.yml'
    path.write_text(yaml.safe_dump(config))
    with pytest.raises(ConfigError):
        load_config(path)


@pytest.mark.parametrize('format', ['excel', 'csv'])
def test_duplicate_headers_are_rejected_before_pandas_renames_them(tmp_path, configurable, format):
    path = tmp_path / ('duplicates.xlsx' if format == 'excel' else 'duplicates.csv')
    if format == 'excel':
        from openpyxl import Workbook
        book = Workbook()
        sheet = book.active
        sheet.title = 'blast'
        sheet.append(['subject', 'time', 'measurement', 'measurement'])
        sheet.append(['synthetic', 1, 10, 99])
        book.save(path)
    else:
        path.write_text('subject,time,measurement,measurement\nsynthetic,1,10,99\n')
    config = configurable(input__path=str(path), input__format=format, input__delimiter=',')
    with pytest.raises(InputDataError, match='duplicate column headers'):
        load_input(config)
