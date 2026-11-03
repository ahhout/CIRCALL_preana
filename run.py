#!/usr/bin/env python3
"""Launch all four layers in the existing pre_analysis Conda environment."""
import os
from pathlib import Path
import shutil
import sys

ENVIRONMENT = 'pre_analysis'
BOOTSTRAP_MARKER = 'PRE_ANALYSIS_CONDA_BOOTSTRAP'


def in_environment():
    """An inherited environment label alone cannot identify this interpreter."""
    prefix = os.environ.get('CONDA_PREFIX')
    return (os.environ.get('CONDA_DEFAULT_ENV') == ENVIRONMENT
            and prefix is not None
            and Path(prefix).resolve() == Path(sys.prefix).resolve())


def conda_executable():
    """Prefer the configured executable, PATH, then standard home installations."""
    candidates = [os.environ.get('CONDA_EXE'), shutil.which('conda')]
    for installation in ('miniconda3', 'miniforge3', 'anaconda3'):
        candidates.append(Path.home()/installation/'bin/conda')
    return next((Path(candidate).expanduser().resolve() for candidate in candidates
                 if candidate and Path(candidate).expanduser().is_file()
                 and os.access(Path(candidate).expanduser(), os.X_OK)), None)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if in_environment():
        from analysis.cli import main as pipeline_main
        return pipeline_main(argv)
    if os.environ.get(BOOTSTRAP_MARKER):
        print('Conda did not select the pre_analysis interpreter; check the existing environment.', file=sys.stderr)
        return 1
    conda = conda_executable()
    if conda is None:
        print('Conda is required. Add it to PATH or set CONDA_EXE to its executable; create pre_analysis from environments/conda-linux-64.lock if missing.', file=sys.stderr)
        return 1
    environment = os.environ.copy()
    environment[BOOTSTRAP_MARKER] = '1'
    # Internal workers also invoke conda; make the discovered installation available.
    environment['PATH'] = str(conda.parent) + os.pathsep + environment.get('PATH', '')
    command = [str(conda), 'run', '--no-capture-output', '-n', ENVIRONMENT,
               'python', '-B', str(Path(__file__).resolve()), *argv]
    try:
        # Replace this process so exit codes and terminal signals reach Conda directly.
        os.execvpe(str(conda), command, environment)
    except OSError:
        print('Conda could not be launched; check its executable and the pre_analysis environment.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
