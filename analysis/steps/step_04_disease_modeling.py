"""Read-only Layer 4 execution with cohort gates and aggregate-only evidence."""
from analysis.disease_modeling.step_04_validate import validate_results
from analysis.disease_modeling.sources import selected_cohorts, settings, verify_source_states
from analysis.disease_modeling.step_02_combine import combined_results
from analysis.disease_modeling.step_01_evaluate import base_result, evaluate
import argparse
from pathlib import Path

from analysis.data_integrity.step_01_inspect import load_rules
from analysis.provenance import ROOT, digest, envelope, utc_now, verify_inputs, write_json
from analysis.disease_modeling.common import load_definitions
from analysis.disease_modeling import mrd, step_03_report as reporting


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


def code_files():
    """Only this workflow and retained infrastructure belong to its method evidence."""
    shared = ['analysis/steps/__init__.py', 'analysis/steps/step_04_disease_modeling.py', 'analysis/utils/__init__.py', 'analysis/data_integrity/formula_checks.py', 'run.py', 'analysis/__init__.py', 'analysis/cli.py', 'analysis/pipeline.py', 'analysis/worker.py',
              'analysis/configuration.py', 'analysis/layer_configuration.py', 'analysis/outputs.py', 'analysis/provenance.py', 'analysis/utils/sample_io.py', 'analysis/utils/sample_definitions.py', 'analysis/utils/figure_layout.py', 'analysis/utils/plot_style.py',
              'analysis/utils/retrospective_controls.py', 'analysis/data_integrity/__init__.py', 'analysis/data_integrity/step_01_inspect.py']
    return [ROOT/p for p in shared]+sorted((ROOT/'analysis/disease_modeling').rglob('*.py'))


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
