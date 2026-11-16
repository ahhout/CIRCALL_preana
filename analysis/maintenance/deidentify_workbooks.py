"""Create pseudonymised analysis copies; retain reviewed study IDs and exact dates."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import secrets
import subprocess
import sys

from analysis.configuration import unique_object
from analysis.maintenance.deidentification_package import CLEAR, group_values, scan_names, transform
from analysis.layer_configuration import LAYERS, SOURCES
from analysis.provenance import ROOT, digest


def utc():
    return datetime.now(timezone.utc).isoformat()


def fresh(path):
    if path.exists() or path.is_symlink() or any(p.is_symlink() for p in path.parents):
        raise ValueError('Fresh destinations without symlinked ancestors are required')


def write_private(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.write('\n')
    path.chmod(0o600)


def run(config, output, private, group_map=None):
    started = utc()
    profile = json.loads(config.read_text(), object_pairs_hook=unique_object)
    if profile.get('schema_version') != 2 or set(profile.get('layers', {})) != set(LAYERS):
        raise ValueError('Select a full schema-2 master')
    if set(profile.get('sources', {})) != SOURCES:
        raise ValueError('All five explicit source roles are required')
    selected = {role: (config.parent / source).resolve() for role, source in profile['sources'].items()}
    if any(not p.is_file() or p.suffix.lower() != '.xlsx' for p in selected.values()):
        raise ValueError('Each selected role requires an existing XLSX workbook')
    for path in (output, private):
        fresh(path)
        if path == ROOT or ROOT not in path.parents:
            raise ValueError('Destinations must be inside the repository and Git-ignored')
        ignored = subprocess.run(['git', '-C', str(ROOT), 'check-ignore', '-q', str(path.relative_to(ROOT))+'/'])
        if ignored.returncode != 0:
            raise ValueError('Destinations must already be Git-ignored')
    if output in private.parents or private in output.parents or output == private:
        raise ValueError('The private mapping must be separate from the analysis bundle')
    definitions = json.loads((ROOT/'configs/definitions/disease_modeling.json').read_text())
    missing = {str(x).strip().casefold() for key in ('missing_tokens', 'unknown_tokens') for x in definitions[key]}
    groups = json.loads(group_map.read_text(), object_pairs_hook=unique_object) if group_map else {}
    if (not isinstance(groups, dict) or any(not isinstance(k, str) or not isinstance(v, str)
                                          or not v.startswith('RETRO-GROUP-') for k, v in groups.items())
            or len(set(groups.values())) != len(groups)):
        raise ValueError('Invalid private surname-group mapping')
    for name in sorted(group_values(selected['retrospective-blasts'], missing)):
        if name not in groups:
            token = 'RETRO-GROUP-'+secrets.token_hex(12)
            while token in groups.values():
                token = 'RETRO-GROUP-'+secrets.token_hex(12)
            groups[name] = token
    output.mkdir(parents=True, mode=0o700)
    private.mkdir(parents=True, mode=0o700)
    write_private(private/'retrospective_count_groups.json', groups)
    record = dict(schema_version=1, status='preparing', started_utc=started,
                  kind='pseudonymised_working_copies_not_certified_anonymous',
                  cleared_fields=sorted(CLEAR), retained='Approved study/sample/DNA/donor IDs; exact clinical dates and times; scientific values and missingness',
                  count_group_rule='Same trimmed, case-sensitive surname groups within the retrospective count source; no inventory linkage',
                  study_id_caution='Existing protocol IDs may contain initials; they remain approved pseudonyms, not proof of anonymity',
                  command=[sys.executable, *sys.argv], config_sha256=digest(config),
                  code_sha256={str(p.relative_to(ROOT)): digest(p) for p in
                               (Path(__file__), Path(__file__).with_name('deidentification_package.py'))},
                  environment_lock_sha256=digest(ROOT/'environments/conda-linux-64.lock'),
                  workbooks={})
    names = set()
    try:
        for role, source in selected.items():
            target = output/(role+'.xlsx')
            details, removed_names = transform(source, target, role, groups, missing)
            record['workbooks'][role] = details
            names.update(removed_names)
            profile['sources'][role] = target.name
        for role in selected:
            hits = scan_names(output/(role+'.xlsx'), names)
            if hits:
                record['workbooks'][role]['residual_name_match_counts'] = hits
                raise ValueError('Residual identifier match requires private review; bundle not accepted')
        for options in [profile['defaults'], *[v['options'] for v in profile['layers'].values()]]:
            for field in ('rules', 'definitions'):
                if field in options:
                    options[field] = str((config.parent/options[field]).resolve())
        write_private(output/'master.json', profile)
        record.update(status='package_verified_pipeline_validation_pending', finished_utc=utc(),
                      mapped_surname_groups=len(groups), residual_known_name_matches=0,
                      privacy_limitations='Retained dates, pseudonymous codes and rare clinical combinations require controlled access; package scanning is not anonymity certification')
        write_private(output/'deidentification_report.json', record)
    except Exception as error:
        record.update(status='failed', error_code=type(error).__name__, finished_utc=utc())
        write_private(output/'deidentification_report.json', record)
        raise
    return record


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument('--config', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True, help='Fresh Git-ignored folder for working copies')
    parser.add_argument('--private-dir', type=Path, required=True, help='Separate fresh Git-ignored folder for the private mapping')
    parser.add_argument('--group-map', type=Path, help='Reuse an existing private mapping for stable aliases; never overwritten')
    args = parser.parse_args(argv)
    try:
        record = run(args.config.expanduser().resolve(), args.output_dir.expanduser().absolute(),
                     args.private_dir.expanduser().absolute(), args.group_map.expanduser().resolve() if args.group_map else None)
        print('Created five pseudonymised working copies; original inputs unchanged; full pipeline validation pending')
        print('Preserved formula/cache cells: '+str(sum(v['preserved_formula_cells'] for v in record['workbooks'].values())))
        return 0
    except Exception as error:
        print('Deidentification failed ('+type(error).__name__+'); existing evidence preserved; patient values omitted', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
