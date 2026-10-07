from copy import deepcopy
from pathlib import Path

import pandas as pd
import pytest
import yaml

from analysis.blast_kinetics.cli import main
from analysis.blast_kinetics.outputs import OutputError, check_output_available
from analysis.blast_kinetics.pipeline import execute
from analysis.blast_kinetics.plotting import PlotError


def write_small_profile(tmp_path, blast_config, *, negative=False):
    input_path = tmp_path / "input.csv"
    values = [-5, 4] if negative else [10, 4]
    pd.DataFrame({
        "subject": ["private-a", "private-a", "private-b", "private-b"],
        "day": [1, 2, 1, 2],
        "measurement": [values[0], values[1], 8, 3],
        "group": ["HeH", "HeH", "HeH", "HeH"],
    }).to_csv(input_path, index=False)

    config = deepcopy(blast_config)
    config["run"]["name"] = "test_run"
    config["input"].update({
        "path": str(input_path),
        "format": "csv",
        "delimiter": ",",
        "decimal": ".",
    })
    config["columns"] = {
        "subject": "subject",
        "time": "day",
        "value": "measurement",
        "group": "group",
    }
    config["normalization"]["mode"] = "none"
    config["analysis"]["model"]["enabled"] = False
    config["analysis"]["model"]["anchor_at_baseline"] = False
    config["plots"]["model"]["enabled"] = False
    config["plots"]["scatter"]["dpi"] = 50
    config["plots"]["scatter"]["width"] = 8
    config["plots"]["scatter"]["height"] = 4
    config["bootstrap"]["resamples"] = 50
    config["output"]["root"] = str(tmp_path / "outputs")
    profile = tmp_path / "profile.yml"
    profile.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    return profile, config


def test_cli_validation_and_successful_atomic_output(tmp_path, blast_config, capsys):
    profile, _ = write_small_profile(tmp_path, blast_config)

    assert main(["--config", str(profile), "--validate-only"]) == 0
    assert "Validation successful" in capsys.readouterr().out
    assert not (tmp_path / "outputs").exists()

    assert main(["--config", str(profile)]) == 0
    run_dir = tmp_path / "outputs" / "test_run"
    assert (run_dir / "blast_kinetics/scatter.png").is_file()
    assert (run_dir / "blast_kinetics/cohort_summary.json").is_file()
    assert (run_dir / ".audit/workflows/blast_kinetics/resolved_config.yml").is_file()
    assert (run_dir / ".audit/workflows/blast_kinetics/run_metadata.json").is_file()
    log = (run_dir / ".audit/workflows/blast_kinetics/run.log").read_text(encoding="utf-8")
    assert "private-a" not in log
    assert "private-b" not in log


def test_cli_refuses_overwrite_without_force(tmp_path, blast_config, capsys):
    profile, _ = write_small_profile(tmp_path, blast_config)
    assert main(["--config", str(profile)]) == 0

    assert main(["--config", str(profile)]) == 2
    assert "Use --force" in capsys.readouterr().err
    assert main(["--config", str(profile), "--force"]) == 0


def test_force_never_replaces_unrelated_output_files(tmp_path, blast_config):
    _, config = write_small_profile(tmp_path, blast_config)
    target = Path(config["output"]["root"]) / config["run"]["name"]
    target.mkdir(parents=True)
    (target / "notes.txt").write_text("keep", encoding="utf-8")

    with pytest.raises(OutputError, match="not owned"):
        check_output_available(config, force=True)


def test_validate_only_rejects_negative_log_values(tmp_path, blast_config):
    _, config = write_small_profile(tmp_path, blast_config, negative=True)

    with pytest.raises(PlotError, match="negative"):
        execute(config, validate_only=True)


def test_explicit_destination_and_complete_provenance(tmp_path, blast_config):
    import json
    profile, _ = write_small_profile(tmp_path, blast_config)
    destination = tmp_path / 'isolated'
    assert main(['--config', str(profile), '--output-dir', str(destination)]) == 0
    metadata = json.loads((destination / '.audit/workflows/blast_kinetics/run_metadata.json').read_text())
    assert metadata['status'] == 'complete'
    assert metadata['workflow'] == 'blast_kinetics'
    assert metadata['inputs']['profile']['sha256']
    assert metadata['inputs']['measurement']['sha256']
    assert metadata['environment_lock_sha256']
    assert metadata['resolved_settings_sha256']
    assert metadata['scientific_contract']['version'] == 1


def test_input_mutation_prevents_atomic_publication(tmp_path, blast_config, monkeypatch):
    from analysis.blast_kinetics import pipeline
    _, config = write_small_profile(tmp_path, blast_config)
    original = pipeline.plot_scatter
    def mutate(data, settings, path):
        original(data, settings, path)
        Path(config['input']['path']).write_text('changed synthetic source')
    monkeypatch.setattr(pipeline, 'plot_scatter', mutate)
    with pytest.raises(ValueError, match='input changed'):
        execute(config)
    assert not (tmp_path / 'outputs/test_run').exists()


def test_pipeline_filename_cannot_hide_unrelated_directory(tmp_path, blast_config):
    _, config = write_small_profile(tmp_path, blast_config)
    target = Path(config['output']['root']) / config['run']['name']
    nested = target / 'scatter.png'
    nested.mkdir(parents=True)
    keep = nested / 'notes.txt'
    keep.write_text('keep')
    with pytest.raises(OutputError, match='regular files'):
        check_output_available(config, force=True)
    assert keep.read_text() == 'keep'


def test_late_unrelated_file_prevents_publication(tmp_path, blast_config):
    from analysis.blast_kinetics.outputs import AtomicRunOutput
    _, config = write_small_profile(tmp_path, blast_config)
    target = Path(config['output']['root']) / config['run']['name']
    with pytest.raises(OutputError, match='not owned'):
        with AtomicRunOutput(config) as stage:
            (stage / 'scatter.png').write_text('synthetic staged artifact')
            target.mkdir()
            (target / 'notes.txt').write_text('keep')
    assert (target / 'notes.txt').read_text() == 'keep'


def test_missing_source_fails_cleanly_without_a_traceback(tmp_path, blast_config, capsys):
    profile, config = write_small_profile(tmp_path, blast_config)
    Path(config['input']['path']).unlink()
    assert main(['--config', str(profile)]) == 2
    message = capsys.readouterr().err
    assert 'Input file does not exist' in message
    assert 'Traceback' not in message


def test_force_rejects_unknown_files_and_directories_in_clean_run(tmp_path, blast_config):
    profile, _ = write_small_profile(tmp_path, blast_config)
    assert main(['--config', str(profile)]) == 0
    target = tmp_path / 'outputs/test_run'
    keep = target / 'notes.txt'
    keep.write_text('keep')
    assert main(['--config', str(profile), '--force']) == 2
    assert keep.read_text() == 'keep'
    keep.unlink()
    (target / 'unreviewed').mkdir()
    assert main(['--config', str(profile), '--force']) == 2
    assert (target / 'unreviewed').is_dir()


def test_force_rejects_symlink_destination(tmp_path, blast_config):
    profile, _ = write_small_profile(tmp_path, blast_config)
    assert main(['--config', str(profile)]) == 0
    alias = tmp_path / 'alias'
    alias.symlink_to(tmp_path / 'outputs/test_run', target_is_directory=True)
    assert main(['--config', str(profile), '--output-dir', str(alias), '--force']) == 2
    assert alias.is_symlink()


def test_failed_force_restores_previous_run_and_retains_failure(tmp_path, blast_config, monkeypatch):
    import analysis.blast_kinetics.cli as cli
    profile, _ = write_small_profile(tmp_path, blast_config)
    assert main(['--config', str(profile)]) == 0
    target = tmp_path / 'outputs/test_run'
    before = (target / 'blast_kinetics/scatter.png').read_bytes()
    def fail(*args, **kwargs):
        raise OSError('synthetic failure')
    monkeypatch.setattr(cli, 'execute', fail)
    assert main(['--config', str(profile), '--force']) == 2
    assert (target / 'blast_kinetics/scatter.png').read_bytes() == before
    backups = list(target.parent.glob('.test_run.previous-*'))
    assert len(backups) == 1
    assert (backups[0] / 'failed_attempt/.audit/run_manifest.json').is_file()
