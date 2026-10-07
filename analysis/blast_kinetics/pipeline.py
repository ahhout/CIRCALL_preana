from analysis.blast_kinetics.data_io import InputDataError, load_input
from analysis.blast_kinetics.outputs import AtomicRunOutput, target_directory, write_run_records
from analysis.blast_kinetics.plotting import PlotError, plot_model, plot_scatter
from analysis.blast_kinetics.preprocessing import prepare_data
from analysis.blast_kinetics.statistics import fit_time_model
from pathlib import Path
from analysis.blast_kinetics.outputs import ROOT
from analysis.provenance import envelope, verify_inputs, utc_now
from analysis.artifacts import kinetics as validate_artifacts


def _validate_plot_values(data, settings, plot_name):
    if not settings["enabled"] or settings["y_scale"] != "log":
        return
    if data["analysis_value"].lt(0).any():
        raise PlotError(f"{plot_name} uses a log scale but analysis values are negative")


def execute(config, validate_only=False, force=False, profile_path=None):
    """Validate and optionally execute one configured measurement analysis."""
    inputs = {'measurement': config['input']['path']}
    if profile_path is not None:
        inputs['profile'] = profile_path
    if not Path(inputs['measurement']).is_file():
        raise InputDataError('Input file does not exist; verify the configured measurement path')
    metadata = envelope('blast_kinetics', config, inputs,
                        [ROOT / 'run.py', *sorted((ROOT / 'analysis').rglob('*.py')),
                         *sorted((ROOT / 'analysis/blast_kinetics').glob('*.py'))],
                        ROOT / 'environments/conda-linux-64.lock')
    source = load_input(config)
    prepared = prepare_data(source, config)
    data = prepared.frame
    _validate_plot_values(data, config["plots"]["scatter"], "Scatter plot")
    _validate_plot_values(data, config["plots"]["model"], "Model plot")

    trend = None
    if config["analysis"]["model"]["enabled"]:
        trend = fit_time_model(data, config)

    if validate_only:
        verify_inputs(metadata['inputs'])
        return prepared.summary, None

    log_lines = [
        f"Run: {config['run']['name']}",
        f"Measurement: {config['measurement']['name']}",
        f"Input rows: {prepared.summary['input_rows']}",
        f"Analysis rows: {prepared.summary['analysis_rows']}",
        f"Analysis subjects: {prepared.summary['analysis_subjects']}",
    ]
    if trend is not None:
        log_lines.extend([
            f"Model converged: {trend.result.converged}",
            f"Model time slope: {trend.result.params['time_centered']:.8g}",
        ])

    with AtomicRunOutput(config, force=force) as stage:
        if config["plots"]["scatter"]["enabled"]:
            plot_scatter(data, config, stage / "scatter.png")
        if trend is not None and config["plots"]["model"]["enabled"]:
            plot_model(trend, config, stage / "mixed_model.png")
        verify_inputs(metadata['inputs'])
        metadata.update(status='complete', finished_utc=utc_now())
        write_run_records(
            stage,
            config,
            prepared.summary,
            log_lines,
            model_result=trend.result if trend is not None else None,
            metadata=metadata,
        )
        validate_artifacts(stage, config)
        verify_inputs(metadata['inputs'])
    return prepared.summary, target_directory(config)
