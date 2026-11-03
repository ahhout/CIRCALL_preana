"""Read-only Layer 4 execution with cohort gates and aggregate-only evidence."""
import argparse
import json
from pathlib import Path
import re
from types import SimpleNamespace

from analysis.data_integrity.checks import load_rules
from analysis.provenance import ROOT, digest, envelope, utc_now, verify_inputs, write_json
from analysis.retrospective_controls import inspect_with_controls
from analysis.sample_io import SourceReadError
from .common import ClinicalError, clean, load_definitions
from . import counts, mrd, reporting


def arguments(argv=None):
    p = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    p.add_argument('--pdf-output', action=argparse.BooleanOptionalAction, default=True, help='Save PDF figures alongside PNGs (default: enabled)')
    p.add_argument('--workflow', choices=['disease_modeling'], default='disease_modeling')
    for field in ('inventory', 'circall', 'donors', 'blood-counts', 'retrospective-blasts', 'output-dir'):
        p.add_argument('--'+field, type=Path)
    p.add_argument('--cohort', choices=['all', 'retrospective', 'circall'], default='all')
    p.add_argument('--analysis', choices=['all', 'mrd', 'counts'], default='all')
    p.add_argument('--include-controls', action=argparse.BooleanOptionalAction, default=True)
    p.add_argument('--pool-mrd', action=argparse.BooleanOptionalAction, default=True)
    p.add_argument('--rules', type=Path, default=ROOT/'configs/definitions/data_integrity.json')
    p.add_argument('--definitions', type=Path, default=ROOT/'configs/definitions/disease_modeling.json')
    # Defaults come from a versioned local definition, never an old helper profile.
    selector = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    selector.add_argument('--definitions', type=Path, default=ROOT/'configs/definitions/disease_modeling.json')
    known, _ = selector.parse_known_args(argv)
    try:
        d = load_definitions(known.definitions.expanduser().absolute())
    except ValueError:
        p.error('Unsupported disease-tracking definitions')
    p.add_argument('--blood-count-unit', choices=['x10^9/L'])
    p.add_argument('--retrospective-blast-unit', choices=['x10^9/L'])
    p.add_argument('--baseline-day-max', type=int, default=d['counts']['default_baseline_day_max'])
    p.add_argument('--baseline-selection', choices=['latest', 'all'], default=d['counts']['default_baseline_selection'])
    p.add_argument('--overlay-max-day', type=int, default=d['counts']['default_overlay_max_day'])
    p.add_argument('--kinetics-y-scale', choices=['log', 'linear'], default=d['counts']['default_y_scale'])
    for name, status in [('mrd-negative-level', 'negative'), ('mrd-unknown-level', 'unknown_significance'), ('mrd-positive-nq-level', 'positive_nonquantifiable')]:
        p.add_argument('--'+name, type=float, default=d['mrd']['default_display_levels'][status])
    p.add_argument('--retrospective-mrd-duplicate-policy', choices=['worst', 'error'], default=d['mrd']['default_duplicate_policy'])
    p.add_argument('--jitter-seed', type=int, default=d['default_jitter_seed'])
    p.add_argument('--validate-only', action='store_true', help='Inspect sources and gates without fitting or publishing')
    a = p.parse_args(argv)
    for cohort, inventory, count_source, unit in [('retrospective', 'inventory', 'retrospective_blasts', 'retrospective_blast_unit'),
                                                  ('circall', 'circall', 'blood_counts', 'blood_count_unit')]:
        if a.cohort in ('all', cohort):
            if getattr(a, inventory) is None:
                p.error(f'Selected {cohort} requires --{inventory}')
            if a.analysis != 'mrd' and (getattr(a, count_source) is None or getattr(a, unit) is None):
                p.error(f'Selected {cohort} counts require an explicit source and confirmed unit')
    if a.overlay_max_day < a.baseline_day_max or a.jitter_seed < 0:
        p.error('Overlay day must follow diagnostic baseline; jitter seed must be nonnegative')
    import math
    if any(not math.isfinite(v) or not 0 < v <= 1 for v in (a.mrd_negative_level, a.mrd_unknown_level, a.mrd_positive_nq_level)):
        p.error('MRD display levels must be finite fractions in (0, 1]')
    for name, value in vars(a).items():
        if isinstance(value, Path):
            setattr(a, name, value.expanduser().absolute())
    return a


def selected_cohorts(args):
    return ['retrospective', 'circall'] if args.cohort == 'all' else [args.cohort]


def selected_sources(args):
    result = {'rules': args.rules, 'definitions': args.definitions,
              'method_provenance': ROOT/'analysis/disease_modeling/method_provenance.json'}
    for cohort in selected_cohorts(args):
        result[cohort] = args.inventory if cohort == 'retrospective' else args.circall
        if args.analysis != 'mrd':
            result[cohort+'_counts'] = args.retrospective_blasts if cohort == 'retrospective' else args.blood_counts
    if args.include_controls and 'retrospective' in selected_cohorts(args) and args.donors is not None:
        result['retrospective_controls'] = args.donors
    return result


def verify_source_states(states):
    for record in states.values():
        try:
            current = digest(record['path'])
        except OSError:
            current = None
        if current != record['sha256']:
            raise ValueError('A selected disease source changed during execution')


def settings(args):
    return {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items() if k not in ('output_dir', 'validate_only')}


def code_files():
    """Only this workflow and retained infrastructure belong to its method evidence."""
    shared = ['run.py', 'analysis/__init__.py', 'analysis/cli.py', 'analysis/pipeline.py', 'analysis/worker.py',
              'analysis/configuration.py', 'analysis/layer_configuration.py', 'analysis/outputs.py', 'analysis/provenance.py', 'analysis/sample_io.py', 'analysis/sample_definitions.py', 'analysis/figure_layout.py', 'analysis/plot_style.py',
              'analysis/retrospective_controls.py', 'analysis/data_integrity/__init__.py', 'analysis/data_integrity/checks.py']
    return [ROOT/p for p in shared]+sorted((ROOT/'analysis/disease_modeling').glob('*.py'))


def base_result(scope, status='complete', blocking=None):
    return dict(scope=scope, status=status, summary={'population_basis': 'Modality-specific populations; no count/MRD linkage'},
                blocking=blocking or [], tables=dict(Coverage=[], MRD=[], Counts=[],
                Models=[dict(status='disabled', reason='Descriptive first release; normalized modeling is a later opt-in increment')],
                Diagnostics=[dict(status='descriptive', note='Source integrity, clinical annotation and count validation; no hypothesis tests')]))


def evaluate(cohort, args, d, rules):
    result = base_result(cohort)
    prepared = dict(mrd=[], counts=[])
    inventory = args.inventory if cohort == 'retrospective' else args.circall
    stage = 'inventory_integrity'
    integrity = None
    try:
        integrity = inspect_with_controls(inventory, cohort, args.include_controls, rules, args.donors)
        result['summary'].update(integrity_errors=integrity['summary']['errors'], integrity_reviews=integrity['summary']['reviews'])
        if integrity['summary']['errors']:
            result.update(status='blocked', blocking=[dict(reason='layer1_error', sheet=g['sheet'], field=g['field'], rule=g['rule'], occurrences=g['count'])
                                                     for g in integrity['groups'] if g['severity'] == 'error'])
            return clean(result), prepared, integrity
        if args.analysis != 'counts':
            stage = 'mrd'
            prepared['mrd'], coverage = mrd.prepare(inventory, cohort, d, duplicate_policy=args.retrospective_mrd_duplicate_policy)
            result['summary']['mrd_retained_patients'] = coverage['retained_patients']
            result['tables']['Coverage'].append(dict(analysis='mrd', **coverage,
                                                    status='available' if any(r['status'] not in ('missing', 'normalized_baseline') for r in prepared['mrd']) else 'unavailable',
                                                    reason='Source-specific MRD population; no receipt or cfDNA eligibility filter'))
            result['tables']['MRD'] = mrd.summary(prepared['mrd'], d['pooled_visits'] if cohort == 'circall' else d['visits'])
        else:
            result['tables']['Coverage'].append(dict(analysis='mrd', status='not_selected'))
        if args.analysis != 'mrd':
            stage = 'counts'
            path = args.retrospective_blasts if cohort == 'retrospective' else args.blood_counts
            prepared['counts'], availability = counts.prepare(path, cohort, d, baseline_day_max=args.baseline_day_max,
                                                               baseline_selection=args.baseline_selection, overlay_max_day=args.overlay_max_day)
            result['tables']['Coverage'].append(dict(analysis='counts', **availability,
                                                    status='available' if any(r['value'] is not None for r in prepared['counts']) else 'unavailable',
                                                    reason='Recorded source population; no inventory matching or count derivation'))
            result['tables']['Counts'] = counts.summary(prepared['counts'], d['counts'][cohort]['sheets'], overlay_max_day=args.overlay_max_day)
            if cohort == 'retrospective':
                result['tables']['Coverage'].append(dict(analysis='wbc', status='unavailable', reason='No retrospective longitudinal WBC source; not reconstructed'))
            result['summary']['count_identity_basis'] = d['counts'][cohort]['identity_rule']
        else:
            result['tables']['Coverage'].append(dict(analysis='counts', status='not_selected'))
        result['summary']['clinical_cache_unavailable'] = sum(v for c in result['tables']['Coverage'] for k, v in c.items() if k.endswith('cache_unavailable'))
        if result['summary']['clinical_cache_unavailable']:
            result['tables']['Diagnostics'].append(dict(status='review', note='Clinical formula caches unavailable; counts/annotations remain unavailable rather than zero'))
        return clean(result), prepared, integrity
    except ClinicalError as error:
        result.update(status='blocked', blocking=[dict(analysis=stage, **error.finding)])
    except SourceReadError as error:
        result.update(status='blocked', blocking=[dict(reason=error.code, analysis=stage)])
    except Exception as error:
        # Even external library exception messages can contain identifiers.
        result.update(status='execution_failed', blocking=[dict(reason=type(error).__name__)])
    result['tables']['MRD'] = []
    result['tables']['Counts'] = []
    return clean(result), dict(mrd=[], counts=[]), integrity


def combined_results(evaluated, args, d):
    results = {}
    clean_cohorts = {c: p for c, (r, p, _) in evaluated.items() if r['status'] == 'complete'}
    if args.pool_mrd and args.analysis != 'counts' and args.cohort == 'all':
        blocked = len(clean_cohorts) != 2
        ready = not blocked and all(p['mrd'] for p in clean_cohorts.values())
        status = 'blocked' if blocked else 'complete' if ready else 'unavailable'
        r = base_result('pooled', status, [] if ready else [dict(reason='Both cohorts need retained MRD populations and completed gates')])
        prepared = dict(mrd=mrd.pool({c: p['mrd'] for c, p in clean_cohorts.items()}, d) if ready else [], counts=[])
        r['tables']['Coverage'] = [dict(analysis='mrd', status='available' if ready else status,
                                         reason='Fixed union of source-specific retained MRD populations; descriptive only')]
        r['tables']['MRD'] = mrd.summary(prepared['mrd'], d['pooled_visits'], fixed=True) if ready else []
        r['summary']['retained_mrd_patients'] = len({(row['cohort'], row['subject_hash']) for row in prepared['mrd']}) if ready else None
        results['pooled'] = clean(r), prepared
    if args.analysis != 'mrd' and args.cohort == 'all':
        ready = len(clean_cohorts) == 2 and all(any(r['measurement'] == 'blast' and r['value'] is not None for r in p['counts']) for p in clean_cohorts.values())
        r = base_result('comparisons', 'complete' if ready else 'unavailable', [] if ready else [dict(reason='Both cohorts need recorded blast counts and completed gates')])
        prepared = dict(mrd=[], counts=[r for p in clean_cohorts.values() for r in p['counts']] if ready else [])
        r['tables']['Counts'] = [dict(cohort=c, **row) for c, (result, _, _) in evaluated.items() if ready for row in result['tables']['Counts'] if row['measurement'] == 'blast']
        r['tables']['Coverage'] = [dict(analysis='blast_cohort_comparison', status='available' if ready else 'unavailable', reason='Separate cohort populations and trajectories; no pooled counts or fit')]
        results['comparisons'] = clean(r), prepared
    return results


def preflight(args):
    d = load_definitions(args.definitions)
    rules = load_rules(args.rules)
    states, inputs = {}, {}
    for role, path in selected_sources(args).items():
        try:
            hashed = digest(path)
            inputs[role] = path
        except OSError:
            hashed = None
        states[role] = dict(path=str(path), sha256=hashed, availability='readable' if hashed else 'unavailable')
    record = envelope('disease_modeling', dict(arguments=settings(args), disease_definition=d, rules_definition=rules), inputs,
                      code_files(), ROOT/'environments/conda-linux-64.lock')
    evaluated = {c: evaluate(c, args, d, rules) for c in selected_cohorts(args)}
    # Only aggregate evidence crosses the worker protocol; never patient records.
    previews = {c: r for c, (r, _, _) in evaluated.items()}
    record.update(status='complete', finished_utc=utc_now(), source_states=states, cohort_preflight=previews,
                  validation_quality='errors_found' if any(r['status'] != 'complete' for r in previews.values()) else 'review_needed' if any(r['summary'].get('integrity_reviews') or r['summary'].get('clinical_cache_unavailable') for r in previews.values()) else 'no_issues_detected')
    verify_inputs(record['inputs'])
    verify_source_states(states)
    return record


def run(args):
    record = preflight(args)
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=False)
    record.update(status='running', started_utc=utc_now(), finished_utc=None, cohorts=[], artifacts=[], analysis_status=[])
    write_json(output/'run_manifest.json', record)
    d = record['resolved_settings']['disease_definition']
    rules = record['resolved_settings']['rules_definition']
    evaluated = {c: evaluate(c, args, d, rules) for c in selected_cohorts(args)}

    def publish_scope(scope, result, prepared, integrity=None):
        native = output/scope
        native.mkdir(exist_ok=True)
        write_json(native/'disease_modeling.json', result)
        if integrity is not None:
            write_json(native/'integrity_findings.json', integrity)
        if result['status'] == 'complete':
            if scope == 'comparisons':
                for early in (False, True):
                    fig = reporting.count_figure(prepared['counts'], 'blast', args, d, early=early, comparison=True)
                    if fig is not None:
                        reporting.save(fig, native/'figures/blood_counts'/f'blast_{"early_window" if early else "full_range"}', pdf_output=getattr(args, 'pdf_output', True))
            else:
                reporting.figures(native/'figures', scope, prepared, result, args, d)
        reporting.workbook(native/'disease_modeling.xlsx', result, d, settings(args))
        reporting.validate_workbook(native/'disease_modeling.xlsx', result, d, settings(args))
        record['cohorts'].append(dict(cohort=scope, report_status='complete', disease_status=result['status']))
        for row in result['tables']['Coverage']:
            if row.get('status') == 'unavailable':
                record['analysis_status'].append(dict(cohort=scope, analysis=row['analysis'], status='unavailable', reason=row.get('reason', 'No eligible observations')))
        for path in sorted(native.rglob('*')):
            if path.is_file():
                record['artifacts'].append(dict(path=str(path.relative_to(output)), sha256=digest(path)))

    scopes = {c: (r, p, integrity) for c, (r, p, integrity) in evaluated.items()}
    scopes.update({c: (r, p, None) for c, (r, p) in combined_results(evaluated, args, d).items()})
    for scope, (result, prepared, integrity) in scopes.items():
        try:
            publish_scope(scope, result, prepared, integrity)
        except Exception as error:
            failure = base_result(scope, 'execution_failed', [dict(reason=type(error).__name__)])
            try:
                publish_scope(scope, failure, dict(mrd=[], counts=[]), integrity)
            except Exception as report_error:
                record['cohorts'].append(dict(cohort=scope, report_status='failed', disease_status='execution_failed', error_code=type(report_error).__name__))
        write_json(output/'run_manifest.json', record)
    try:
        verify_inputs(record['inputs'])
        verify_source_states(record['source_states'])
    except (OSError, ValueError):
        record.update(status='failed', error_code='SourceChanged', finished_utc=utc_now())
        write_json(output/'run_manifest.json', record)
        return 1
    record.update(status='complete' if any(c['report_status'] == 'complete' for c in record['cohorts']) else 'failed',
                  quality_status='errors_found' if any(c['disease_status'] in ('blocked', 'execution_failed') for c in record['cohorts']) else record['validation_quality'],
                  report_generation_status='complete' if all(c['report_status'] == 'complete' for c in record['cohorts']) else 'partial', finished_utc=utc_now())
    write_json(output/'run_manifest.json', record)
    return 0 if record['status'] == 'complete' else 1


def validate_results(output, record):
    output = Path(output)
    d = record['resolved_settings']['disease_definition']
    rules = record['resolved_settings']['rules_definition']
    args = SimpleNamespace(**record['resolved_settings']['arguments'])
    evaluated = {c: evaluate(c, args, d, rules) for c in selected_cohorts(args)}
    expected = {c: r for c, (r, _, _) in evaluated.items()}
    expected.update({c: r for c, (r, _) in combined_results(evaluated, args, d).items()})
    for artifact in record['artifacts']:
        path = Path(artifact['path'])
        if path.is_absolute() or '..' in path.parts or (output/path).is_symlink() or digest(output/path) != artifact['sha256']:
            raise ValueError('Disease artifact mismatch')
        if path.suffix == '.png':
            from PIL import Image
            with Image.open(output/path) as im:
                im.verify()
        if path.suffix == '.pdf':
            payload = (output/path).read_bytes()
            xref = re.search(rb'startxref\s+(\d+)\s+%%EOF\s*$', payload)
            if not payload.startswith(b'%PDF-') or b'/Type /Page' not in payload or not xref or payload[int(xref[1]):int(xref[1])+4] != b'xref':
                raise ValueError('Invalid disease PDF structure')
    for scope in record['cohorts']:
        if scope['report_status'] != 'complete':
            continue
        native = output/scope['cohort']
        result = json.loads((native/'disease_modeling.json').read_text())
        reporting.validate_workbook(native/'disease_modeling.xlsx', result, d, settings(args))
        if result['status'] != 'execution_failed' and result != expected[scope['cohort']]:
            raise ValueError('Disease aggregate reports differ from reconstructed sources')
        if result['status'] == 'execution_failed' and (not result['blocking'] or scope['disease_status'] != 'execution_failed'):
            raise ValueError('Invalid execution failure evidence')
    verify_inputs(record['inputs'])
    verify_source_states(record['source_states'])
