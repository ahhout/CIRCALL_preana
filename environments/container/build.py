#!/usr/bin/env python3
"""Prepare and optionally build one four-layer image with explicitly selected data."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import platform
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
ROLES = ('inventory', 'circall', 'donors', 'blood-counts', 'retrospective-blasts')
FONTS = ('Arial.ttf', 'Arial_Bold.ttf', 'Arial_Italic.ttf', 'Arial_Bold_Italic.ttf')
LAYERS = {'data_integrity', 'sample_statistics', 'advanced_analysis', 'disease_modeling'}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def copy_file(source, destination):
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(source, destination)
    destination.chmod(0o644)


def prepare(config, arial_dir, context):
    """Copy the chosen workbook bytes unchanged; this does not anonymise inputs."""
    sys.path.insert(0, str(ROOT))
    from analysis.configuration import unique_object
    profile = json.loads(config.read_text(), object_pairs_hook=unique_object)
    if profile.get('schema_version') != 2 or set(profile.get('layers', {})) != LAYERS:
        raise ValueError('Select an explicit schema-2 master containing all four layers')
    if set(profile.get('sources', {})) != set(ROLES):
        raise ValueError('The bundled image requires explicit sources for all five roles')
    if any(layer.get('enabled', True) is not True for layer in profile['layers'].values()):
        raise ValueError('Every layer must remain enabled')
    if not isinstance(profile.get('defaults'), dict) or any(
            not isinstance(layer.get('options'), dict) for layer in profile['layers'].values()):
        raise ValueError('Master defaults and layer options must be objects')
    # Scientific option validation remains the integrated preflight's responsibility.
    selected = {}
    for role in ROLES:
        source = (config.parent/profile['sources'][role]).resolve()
        if not source.is_file() or source.suffix.lower() != '.xlsx':
            raise ValueError('Selected workbook unavailable for role '+role)
        selected[role] = source
    for name in FONTS:
        if not (arial_dir/name).is_file():
            raise ValueError('Arial requires regular, bold, italic and bold-italic TTF files')
    if context.exists() or context.is_symlink() or any(p.is_symlink() for p in context.parents):
        raise ValueError('Choose a fresh context directory without symlinked ancestors')
    context.mkdir(parents=True, exist_ok=False)
    files = [ROOT/p for p in ('Apptainer.def', 'run.py', 'README.md', 'AGENTS.md',
                              'environments/environment.yml', 'environments/conda-linux-64.lock')]
    visible = subprocess.run(['git', '-C', str(ROOT), 'ls-files', '-c', '-o',
                              '--exclude-standard', '-z'], capture_output=True, check=True).stdout.decode().split('\0')
    suffixes = {'analysis': {'.py', '.json'}, 'configs': {'.json'},
                'docs': {'.md', '.json'}, 'tests': {'.py', '.json'}}
    files.extend(ROOT/name for name in visible if name
                 and Path(name).parts[0] in suffixes
                 and Path(name).suffix in suffixes[Path(name).parts[0]]
                 and (ROOT/name).is_file())
    code_hashes = {}
    for source in sorted(set(files)):
        if source.is_symlink():
            raise ValueError('Build sources must not be symlinks')
        relative = source.relative_to(ROOT)
        copy_file(source, context/relative)
        code_hashes[str(relative)] = digest(source)
    fonts = {}
    for name in FONTS:
        copy_file(arial_dir/name, context/'arial'/name)
        fonts[name] = digest(context/'arial'/name)
    sources = {}
    for role, source in selected.items():
        target = context/'dataset/input'/f'{role}.xlsx'
        before = digest(source)
        copy_file(source, target)
        if digest(source) != before or digest(target) != before:
            raise ValueError('Selected source changed while preparing role '+role)
        sources[role] = before
        profile['sources'][role] = f'../input/{role}.xlsx'
    # Resolve referenced rules/definitions to their unchanged in-repository files.
    for options in [profile['defaults'], *[layer['options'] for layer in profile['layers'].values()]]:
        for field in ('rules', 'definitions'):
            if field in options:
                original = (config.parent/options[field]).resolve()
                try:
                    relative = original.relative_to(ROOT/'configs')
                except ValueError:
                    raise ValueError('Rules and definitions must be selected from repository configs') from None
                options[field] = str(relative)
    profile.pop('output-dir', None)
    profile.pop('validate-only', None)
    target = context/'dataset/configs/container_master.json'
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(profile, indent=2)+'\n')
    target.chmod(0o644)
    revision = subprocess.run(['git', '-C', str(ROOT), 'rev-parse', 'HEAD'],
                              capture_output=True, text=True, check=True).stdout.strip()
    dirty = subprocess.run(['git', '-C', str(ROOT), 'status', '--porcelain'],
                           capture_output=True, text=True, check=True).stdout.strip()
    record = dict(schema_version=1, prepared_utc=datetime.now(timezone.utc).isoformat(),
                  platform='linux/amd64', runtime='apptainer', code_revision=revision, code_dirty=bool(dirty),
                  code_sha256=code_hashes, source_sha256=sources, arial_sha256=fonts,
                  config_sha256=digest(config), container_config_sha256=digest(target),
                  environment_lock_sha256=digest(ROOT/'environments/conda-linux-64.lock'),
                  preparation_script_sha256=digest(Path(__file__)))
    (context/'container_build.json').write_text(json.dumps(record, indent=2)+'\n')
    return record


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--config', type=Path, required=True,
                        help='Explicit full master selecting reviewed data; workbook bytes are copied unchanged')
    parser.add_argument('--arial-dir', type=Path, required=True)
    parser.add_argument('--context', type=Path, required=True,
                        help='Fresh local build directory; contains the selected data and fonts')
    parser.add_argument('--image', type=Path, default=Path('circall-preana.sif'),
                        help='Fresh SIF output path; existing images are never replaced')
    parser.add_argument('--prepare-only', action='store_true')
    parser.add_argument('--root-mapped-build', action='store_true',
                        help='Use root-mapped namespaces without subordinate IDs or host fakeroot (WSL workaround)')
    args = parser.parse_args(argv)
    if platform.system() != 'Linux' or platform.machine() not in ('x86_64', 'AMD64'):
        parser.error('The environment lock requires Linux x86-64 (WSL2 is supported)')
    if not args.prepare_only and shutil.which('apptainer') is None:
        parser.error('Apptainer is required; no build context was created')
    try:
        context = args.context.expanduser().absolute()
        image = args.image.expanduser().absolute()
        if not args.prepare_only and (image.exists() or image.is_symlink()
                                      or any(p.is_symlink() for p in image.parents)):
            raise ValueError('Choose a fresh image path without symlinked ancestors')
        record = prepare(args.config.expanduser().resolve(), args.arial_dir.expanduser().resolve(), context)
        if args.prepare_only:
            print('Prepared one full-pipeline context; image not built')
            return 0
        image.parent.mkdir(parents=True, exist_ok=True)
        version = subprocess.run(['apptainer', '--version'], check=True,
                                 capture_output=True, text=True).stdout.strip()
        command = ['apptainer', 'build', '--fakeroot']
        if args.root_mapped_build:
            command += ['--ignore-subuid', '--ignore-fakeroot-command']
        command += [str(image), 'Apptainer.def']
        subprocess.run(command, cwd=context, check=True)
        record.update(image=str(image), image_sha256=digest(image), apptainer_version=version,
                      build_command=command, build_cwd=str(context))
        (context/'build_result.json').write_text(json.dumps(record, indent=2)+'\n')
        print('Built full-pipeline image '+str(image))
        return 0
    except ValueError as error:
        print('Container preparation failed: '+str(error), file=sys.stderr)
        return 1
    except Exception as error:
        print('Container preparation/build failed ('+type(error).__name__+'); existing evidence preserved', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
