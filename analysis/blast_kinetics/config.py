from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
import math
import re

import yaml


class ConfigError(ValueError):
    """Raised when a pipeline configuration is incomplete or inconsistent."""


@dataclass(frozen=True)
class LoadedConfig:
    data: dict
    path: Path


def _require(mapping, key, context):
    if not isinstance(mapping, dict):
        raise ConfigError(f"Configuration section '{context}' must be a mapping")
    if key not in mapping:
        raise ConfigError(f"Missing required configuration key: {context}.{key}")
    return mapping[key]


def _require_section(config, name):
    section = _require(config, name, "config")
    if not isinstance(section, dict):
        raise ConfigError(f"Configuration section '{name}' must be a mapping")
    return section


def _validate_positive(value, label, allow_zero=False):
    _finite(value, label)
    valid = value >= 0 if allow_zero else value > 0
    if not valid:
        qualifier = "non-negative" if allow_zero else "positive"
        raise ConfigError(f"{label} must be {qualifier}")


def _finite(value, label):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ConfigError(f"{label} must be a finite number")


def _integer(value, label, minimum=0):
    if type(value) is not int or value < minimum:
        raise ConfigError(f"{label} must be an integer >= {minimum}")


def _boolean(value, label):
    if type(value) is not bool:
        raise ConfigError(f"{label} must be Boolean")


def _string(value, label):
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{label} must be a nonempty string")


def load_config(path):
    """Load, resolve, and validate a version-1 YAML configuration."""
    config_path = Path(path).expanduser().resolve()
    if not config_path.is_file():
        raise ConfigError(f"Configuration file does not exist: {config_path}")

    try:
        with config_path.open(encoding="utf-8") as handle:
            raw = yaml.safe_load(handle)
    except (OSError, yaml.YAMLError):
        raise ConfigError('Cannot read a valid YAML profile') from None
    if not isinstance(raw, dict):
        raise ConfigError("Configuration root must be a mapping")

    config = deepcopy(raw)
    if type(config.get("schema_version")) is not int or config.get("schema_version") != 1:
        raise ConfigError("schema_version must be 1")

    run = _require_section(config, "run")
    run_name = _require(run, "name", "run")
    if not isinstance(run_name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", run_name):
        raise ConfigError("run.name must contain only letters, numbers, underscores, or hyphens")

    input_config = _require_section(config, "input")
    input_format = _require(input_config, "format", "input")
    _string(input_format, 'input.format')
    if input_format not in {"excel", "csv"}:
        raise ConfigError("input.format must be 'excel' or 'csv'")
    _string(_require(input_config, "path", "input"), 'input.path')
    input_path = Path(input_config['path']).expanduser()
    if not input_path.is_absolute():
        input_path = config_path.parent / input_path
    input_config["path"] = str(input_path.resolve())
    if input_format == "excel" and not input_config.get("sheet"):
        raise ConfigError("input.sheet is required for Excel input")
    if input_format == "csv" and not input_config.get("delimiter"):
        raise ConfigError("input.delimiter is required for CSV input")
    for field in ('delimiter', 'decimal'):
        if field in input_config:
            _string(input_config[field], 'input.' + field)
            if len(input_config[field]) != 1:
                raise ConfigError('input.' + field + ' must be one character')

    columns = _require_section(config, "columns")
    for name in ("subject", "time", "value"):
        _string(_require(columns, name, "columns"), 'columns.' + name)
    if columns.get('group') is not None:
        _string(columns['group'], 'columns.group')
    mapped = [value for value in columns.values() if value is not None]
    if len(mapped) != len(set(mapped)):
        raise ConfigError('Configured source columns must be distinct')

    measurement = _require_section(config, "measurement")
    _string(_require(measurement, "name", "measurement"), 'measurement.name')
    _string(_require(measurement, "unit", "measurement"), 'measurement.unit')

    time = _require_section(config, "time")
    minimum = _require(time, "minimum", "time")
    maximum = _require(time, "maximum", "time")
    _finite(minimum, 'time.minimum')
    _finite(maximum, 'time.maximum')
    if minimum > maximum:
        raise ConfigError("time.minimum cannot exceed time.maximum")
    _integer(_require(time, "minimum_measurements", "time"), "time.minimum_measurements", 1)
    _validate_positive(_require(time, "tick_step", "time"), "time.tick_step")

    normalization = _require_section(config, "normalization")
    mode = _require(normalization, "mode", "normalization")
    _string(mode, 'normalization.mode')
    if mode not in {"none", "percent_of_baseline"}:
        raise ConfigError("normalization.mode must be 'none' or 'percent_of_baseline'")
    for key in ('baseline_time', 'output_baseline'):
        if key in normalization and normalization[key] is not None:
            _finite(normalization[key], 'normalization.' + key)
    if mode == "percent_of_baseline":
        _finite(_require(normalization, "baseline_time", "normalization"), 'normalization.baseline_time')
        _validate_positive(_require(normalization, "output_baseline", "normalization"), 'normalization.output_baseline')
        for policy in ("missing_baseline_policy", "nonpositive_baseline_policy"):
            _string(_require(normalization, policy, 'normalization'), 'normalization.' + policy)
            if _require(normalization, policy, "normalization") not in {"exclude", "error"}:
                raise ConfigError(f"normalization.{policy} must be 'exclude' or 'error'")

    grouping = _require_section(config, "grouping")
    _boolean(_require(grouping, "require_constant_per_subject", "grouping"), 'grouping.require_constant_per_subject')
    _string(_require(grouping, 'unknown_policy', 'grouping'), 'grouping.unknown_policy')
    if _require(grouping, "unknown_policy", "grouping") not in {"error", "auto"}:
        raise ConfigError("grouping.unknown_policy must be 'error' or 'auto'")
    for name in ("aliases", "colors"):
        if not isinstance(_require(grouping, name, "grouping"), dict):
            raise ConfigError(f"grouping.{name} must be a mapping")

    bootstrap = _require_section(config, "bootstrap")
    confidence = _require(bootstrap, "confidence", "bootstrap")
    _finite(confidence, 'bootstrap.confidence')
    if not 0 < confidence < 1:
        raise ConfigError("bootstrap.confidence must be between 0 and 1")
    _integer(_require(bootstrap, "resamples", "bootstrap"), "bootstrap.resamples", 1)
    _integer(
        _require(bootstrap, "minimum_observations", "bootstrap"),
        "bootstrap.minimum_observations", 1,
    )
    _integer(_require(bootstrap, "seed", "bootstrap"), 'bootstrap.seed')

    analysis = _require_section(config, "analysis")
    winsorization = _require(analysis, "winsorization", "analysis")
    _boolean(_require(winsorization, 'enabled', 'analysis.winsorization'), 'analysis.winsorization.enabled')
    if _require(winsorization, "enabled", "analysis.winsorization"):
        for key in ("lower_limit", "upper_limit"):
            value = _require(winsorization, key, "analysis.winsorization")
            _finite(value, 'analysis.winsorization.' + key)
            if not 0 <= value < 0.5:
                raise ConfigError(f"analysis.winsorization.{key} must be in [0, 0.5)")

    model = _require(analysis, "model", "analysis")
    _boolean(_require(model, 'enabled', 'analysis.model'), 'analysis.model.enabled')
    if 'anchor_at_baseline' in model or model['enabled']:
        _boolean(_require(model, 'anchor_at_baseline', 'analysis.model'), 'analysis.model.anchor_at_baseline')
    for key in ('time_origin', 'log_offset'):
        if key in model:
            _finite(model[key], 'analysis.model.' + key)
    if _require(model, "enabled", "analysis.model"):
        _finite(_require(model, "time_origin", "analysis.model"), 'analysis.model.time_origin')
        transform = _require(model, "response_transform", "analysis.model")
        _string(transform, 'analysis.model.response_transform')
        if transform not in {"none", "log_offset"}:
            raise ConfigError("analysis.model.response_transform must be 'none' or 'log_offset'")
        _validate_positive(
            _require(model, "log_offset", "analysis.model"),
            "analysis.model.log_offset",
            allow_zero=True,
        )
        if model.get("anchor_at_baseline") and mode != "percent_of_baseline":
            raise ConfigError("Model baseline anchoring requires percent_of_baseline normalization")

    plots = _require_section(config, "plots")
    _require(plots, "scatter", "plots")
    _require(plots, "model", "plots")
    common_plot_keys = {
        "enabled", "title", "x_label", "y_label", "y_scale", "y_limits",
        "y_ticks", "detection_limit", "width", "height", "dpi",
        "title_fontsize", "label_fontsize", "legend_fontsize", "marker_size",
        "marker_alpha", "marker_edge_color", "marker_edge_width", "jitter",
        "jitter_seed",
    }
    plot_specific_keys = {
        "scatter": {"legend_title", "ci_color", "ci_alpha"},
        "model": {
            "legend_columns", "trend_color", "trend_marker", "trend_marker_size",
            "trend_label",
        },
    }
    for plot_name in ("scatter", "model"):
        plot = plots[plot_name]
        context = f"plots.{plot_name}"
        for key in common_plot_keys | plot_specific_keys[plot_name]:
            _require(plot, key, context)
        _boolean(plot['enabled'], context + '.enabled')
        _string(plot['y_scale'], context + '.y_scale')
        _integer(plot['jitter_seed'], context + '.jitter_seed')
        _integer(plot['dpi'], context + '.dpi', 1)
        for key in ('jitter', 'marker_size', 'marker_edge_width'):
            _validate_positive(plot[key], context + '.' + key, allow_zero=True)
        for key in ('title_fontsize', 'label_fontsize', 'legend_fontsize', 'detection_limit', 'trend_marker_size'):
            if key in plot:
                _validate_positive(plot[key], context + '.' + key)
        if 'legend_columns' in plot:
            _integer(plot['legend_columns'], context + '.legend_columns', 1)
        for key in ('marker_alpha', 'ci_alpha'):
            if key in plot:
                _finite(plot[key], context + '.' + key)
                if not 0 <= plot[key] <= 1:
                    raise ConfigError(context + '.' + key + ' must be in [0, 1]')
        if plot["y_scale"] not in {"linear", "log"}:
            raise ConfigError(f"plots.{plot_name}.y_scale must be 'linear' or 'log'")
        _validate_positive(plot["width"], f"plots.{plot_name}.width")
        _validate_positive(plot["height"], f"plots.{plot_name}.height")
        _validate_positive(plot["dpi"], f"plots.{plot_name}.dpi")
        if plot["y_scale"] == "log":
            _validate_positive(
                plot["detection_limit"], f"plots.{plot_name}.detection_limit"
            )
        if plot["y_limits"] is not None:
            if not isinstance(plot['y_limits'], list) or len(plot['y_limits']) != 2:
                raise ConfigError(f"plots.{plot_name}.y_limits must contain two values")
            for value in plot['y_limits']:
                _finite(value, context + '.y_limits')
            if plot['y_limits'][0] >= plot['y_limits'][1]:
                raise ConfigError(context + '.y_limits must be increasing')
        if plot["y_ticks"] is not None:
            ticks = plot["y_ticks"]
            if not isinstance(ticks, dict) or set(ticks) != {"values", "labels"} or not all(isinstance(ticks[k], list) for k in ticks) or len(ticks["values"]) != len(ticks["labels"]):
                raise ConfigError(
                    f"plots.{plot_name}.y_ticks values and labels must have equal lengths"
                )
            for value in ticks['values']:
                _finite(value, context + '.y_ticks.values')
        allowed = common_plot_keys | plot_specific_keys[plot_name]
        if set(plot) - allowed:
            raise ConfigError(context + ' contains unknown settings')

    output = _require_section(config, "output")
    _string(_require(output, "root", "output"), 'output.root')
    output_root = Path(output['root']).expanduser()
    if not output_root.is_absolute():
        output_root = config_path.parent / output_root
    output["root"] = str(output_root.resolve())

    allowed_sections = {
        'run': {'name'}, 'input': {'path', 'format', 'sheet', 'delimiter', 'decimal'},
        'columns': {'subject', 'time', 'value', 'group'}, 'measurement': {'name', 'unit'},
        'time': {'minimum', 'maximum', 'tick_step', 'minimum_measurements'},
        'normalization': {'mode', 'baseline_time', 'output_baseline', 'missing_baseline_policy', 'nonpositive_baseline_policy'},
        'grouping': {'require_constant_per_subject', 'unknown_policy', 'aliases', 'colors'},
        'bootstrap': {'confidence', 'resamples', 'minimum_observations', 'seed'},
        'analysis': {'winsorization', 'model'}, 'plots': {'scatter', 'model'}, 'output': {'root'},
    }
    if set(config) != {'schema_version', *allowed_sections}:
        raise ConfigError('Profile contains unknown or missing sections')
    for section, allowed in allowed_sections.items():
        if set(config[section]) - allowed:
            raise ConfigError(section + ' contains unknown settings')
    for key, allowed in [('winsorization', {'enabled', 'lower_limit', 'upper_limit'}),
                         ('model', {'enabled', 'time_origin', 'response_transform', 'log_offset', 'anchor_at_baseline'})]:
        if set(analysis[key]) - allowed:
            raise ConfigError('analysis.' + key + ' contains unknown settings')

    return LoadedConfig(data=config, path=config_path)
