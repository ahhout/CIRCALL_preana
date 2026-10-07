import argparse
import json
import sys
from pathlib import Path
from copy import deepcopy
import tempfile

from analysis.blast_kinetics.config import ConfigError, load_config
from analysis.blast_kinetics.data_io import InputDataError
from analysis.blast_kinetics.outputs import OutputError
from analysis.blast_kinetics.pipeline import execute
from analysis.blast_kinetics.plotting import PlotError
from analysis.blast_kinetics.preprocessing import DataValidationError
from analysis.blast_kinetics.statistics import ModelError


EXPECTED_ERRORS = (
    ConfigError,
    InputDataError,
    DataValidationError,
    ModelError,
    PlotError,
    OutputError,
)


def build_parser():
    parser = argparse.ArgumentParser(
        description="Analyze one longitudinal numeric measurement from a YAML profile."
    )
    parser.add_argument("--config", required=True, help="Path to a version-1 YAML profile")
    parser.add_argument('--output-dir', type=Path, help='Explicit destination; input paths still resolve from the profile')
    parser.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate configuration, data, and model without writing outputs",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace an existing run containing only pipeline-owned artifacts",
    )
    return parser


def main(argv=None):
    args = build_parser().parse_args(argv)
    try:
        loaded = load_config(args.config)
        if args.output_dir is not None:
            destination = args.output_dir.expanduser().absolute()
            if any(p.is_symlink() for p in (destination, *destination.parents)):
                raise OutputError('Output destination must not contain symlinks')
            loaded.data['output']['root'] = str(destination.parent)
            loaded.data['run']['name'] = destination.name
        if not Path(loaded.data['input']['path']).is_file():
            raise InputDataError('Input file does not exist; verify the configured measurement path')
        if args.validate_only:
            summary, _ = execute(loaded.data, validate_only=True, profile_path=loaded.path)
            print('Validation successful')
            print(json.dumps(summary, indent=2, sort_keys=True))
            return 0
        from analysis.outputs import run_standalone, validate_owned_run
        from analysis.worker import completion
        output = Path(loaded.data['output']['root']) / loaded.data['run']['name']
        backup = None
        if output.is_symlink() or (output.exists() and not output.is_dir()):
            raise OutputError('Output destination must be a real directory')
        if output.exists() and any(output.iterdir()):
            if not args.force:
                raise OutputError('Output directory already contains results. Use --force to replace an owned run.')
            validate_owned_run(output, 'blast_kinetics')
            backup = Path(tempfile.mkdtemp(prefix='.' + output.name + '.previous-', dir=output.parent))
            output.rename(backup / 'run')
        entry = {'name': 'blast_kinetics', 'profile': str(loaded.path)}
        def run_native(source):
            config = deepcopy(loaded.data)
            config['output']['root'] = str(source.parent)
            config['run']['name'] = source.name
            execute(config, profile_path=loaded.path)
            return 0
        try:
            result = run_standalone('blast_kinetics', output, loaded.data, run_native,
                                    lambda source: completion(entry, source))
        except BaseException:
            if backup is not None:
                if output.exists():
                    output.rename(backup / 'failed_attempt')
                (backup / 'run').rename(output)
            raise
        if backup is not None:
            if result:
                output.rename(backup / 'failed_attempt')
                (backup / 'run').rename(output)
                print(f'Previous run restored; failed attempt retained in {backup}', file=sys.stderr)
            else:
                print(f'Previous run retained in {backup}')
        return 0 if result == 0 else 2
    except EXPECTED_ERRORS as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except (ValueError, OSError):
        print('ERROR: source integrity or required file check failed; use a fresh run and verify inputs and the environment lock', file=sys.stderr)
        return 2
