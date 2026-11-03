from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import shutil
import tempfile
import sys

import matplotlib
import numpy
import pandas
import scipy
import seaborn
import statsmodels
import yaml

from analysis.blast_kinetics import __version__

ROOT = Path(__file__).resolve().parents[2]

from analysis.provenance import write_json


PIPELINE_ARTIFACTS = {
    "scatter.png",
    "mixed_model.png",
    "model_summary.txt",
    "cohort_summary.json",
    "resolved_config.yml",
    "run_metadata.json",
    "run.log",
}


class OutputError(RuntimeError):
    """Raised when safe output publication is not possible."""


def target_directory(config):
    return Path(config["output"]["root"]) / config["run"]["name"]


def check_output_available(config, force=False):
    target = target_directory(config)
    if target.is_symlink() or (target.exists() and not target.is_dir()):
        raise OutputError('Output destination must be a real directory')
    if not target.exists() or not any(target.iterdir()):
        return target
    existing = {entry.name for entry in target.iterdir()}
    unknown = existing - PIPELINE_ARTIFACTS
    if unknown:
        raise OutputError(
            f"Output directory contains files not owned by the pipeline: {sorted(unknown)}"
        )
    if any(entry.is_symlink() or not entry.is_file() for entry in target.iterdir()):
        raise OutputError('Output directory contains artifacts not owned as regular files')
    if not force:
        raise OutputError(
            f"Output directory already contains results: {target}. Use --force to replace them."
        )
    return target


class AtomicRunOutput:
    """Stage a complete run and publish it only after every artifact succeeds."""

    def __init__(self, config, force=False):
        self.config = config
        self.force = force
        self.target = check_output_available(config, force=force)
        self.stage = None

    def __enter__(self):
        root = self.target.parent
        root.mkdir(parents=True, exist_ok=True)
        self.stage = Path(tempfile.mkdtemp(prefix=f".{self.target.name}-", dir=root))
        return self.stage

    def __exit__(self, exc_type, exc, traceback):
        if exc_type is not None:
            if self.stage and self.stage.exists():
                shutil.rmtree(self.stage)
            return False
        check_output_available(self.config, force=self.force)
        if self.target.exists():
            if self.force:
                # Delete only reviewed pipeline files. rmdir refuses any file added
                # after validation, and unlink cannot recursively remove a directory.
                for entry in self.target.iterdir():
                    if entry.name not in PIPELINE_ARTIFACTS or entry.is_symlink() or not entry.is_file():
                        raise OutputError('Output ownership changed during publication')
                    entry.unlink()
            self.target.rmdir()
        self.stage.replace(self.target)
        return False


def write_run_records(stage, config, summary, log_lines, model_result=None, metadata=None):
    """Write non-row-level run records and an optional model summary."""
    with (stage / "resolved_config.yml").open("w", encoding="utf-8") as handle:
        yaml.safe_dump(config, handle, sort_keys=False, allow_unicode=True)
    with (stage / "cohort_summary.json").open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, indent=2, sort_keys=True)
        handle.write("\n")
    metadata = {**(metadata or {}),
        "completed_at_utc": datetime.now(timezone.utc).isoformat(),
        "pipeline_version": __version__,
        "python": platform.python_version(),
        "packages": {**(metadata or {}).get('packages', {}),
            "matplotlib": matplotlib.__version__,
            "numpy": numpy.__version__,
            "pandas": pandas.__version__,
            "scipy": scipy.__version__,
            "seaborn": seaborn.__version__,
            "statsmodels": statsmodels.__version__,
        },
    }
    write_json(stage / 'run_metadata.json', metadata)
    (stage / "run.log").write_text("\n".join(log_lines) + "\n", encoding="utf-8")
    if model_result is not None:
        (stage / "model_summary.txt").write_text(
            str(model_result.summary()) + "\n", encoding="utf-8"
        )
