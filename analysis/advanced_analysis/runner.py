"""Independent Layer 3 diagnosis associations with whole-cohort integrity gates."""
import argparse
import json
import os
from pathlib import Path
import re
from types import SimpleNamespace

import pandas as pd

from analysis import association_methods as engine
from analysis.data_integrity.checks import load_rules
from analysis.source_state import capture_sources, sources, verify_source_states
from analysis.provenance import ROOT, digest, envelope, utc_now, verify_inputs, write_json
from analysis.retrospective_controls import inspect_with_controls
from .preparation import load_definitions, prepare
from .reporting import workbook, validate_workbook, figures
from .statistics import analyze, clean
from .schema import observation_columns, with_comparison_switches


def arguments(argv=None):
    p = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    p.add_argument('--pdf-output', action=argparse.BooleanOptionalAction, default=True, help='Save PDF figures alongside PNGs (default: enabled)')
    p.add_argument('--workflow', choices=['advanced_analysis'], default='advanced_analysis')
    for field in ('inventory', 'circall', 'donors', 'output-dir'):
        p.add_argument('--'+field, type=Path)
    p.add_argument('--cohort', choices=['all', 'retrospective', 'circall'], default='all')
    p.add_argument('--include-controls', action=argparse.BooleanOptionalAction, default=True, help='Controls integrity only; donors must be explicitly selected')
    p.add_argument('--rules', type=Path, default=ROOT/'configs/definitions/data_integrity.json')
    p.add_argument('--definitions', type=Path, default=ROOT/'configs/definitions/advanced_analysis.json')
    p.add_argument('--pool-cohorts', action=argparse.BooleanOptionalAction, default=True, help='Compatible pooled descriptions; no pooled inference')
    p.add_argument('--retrospective-wbc-unit', choices=['unknown', 'x10^9/L'], default='unknown')
    p.add_argument('--validate-only', action='store_true')
    p.add_argument('--comparison-switches', type=json.loads,
                   help='JSON comparison matrix; the master profile supplies these switches')
    p.add_argument('--sample-selection-seed', type=int, default=123, help='Reproducible selection of one numeric diagnosis sample per patient')
    definitions = load_definitions(ROOT/'configs/definitions/advanced_analysis.json')
    p.add_argument('--spearman-sensitivity', action=argparse.BooleanOptionalAction, default=True,
                   help='Secondary unadjusted peripheral-blast Spearman for each selected outcome')
    p.add_argument('--predictors', nargs='+', choices=['requested', *definitions['predictors']], default=['requested'],
                   help='Test all requested pairs, or restrict testing to these predictors within the requested matrix')
    a = p.parse_args(argv)
    if a.comparison_switches is not None:
        try:
            with_comparison_switches(load_definitions(a.definitions), a.comparison_switches)
        except ValueError as error:
            p.error(str(error))
    if a.sample_selection_seed < 0:
        p.error('Sample selection seed must be nonnegative')
    if len(set(a.predictors)) != len(a.predictors) or ('requested' in a.predictors and len(a.predictors) != 1):
        p.error('Predictors must be a nonempty unique selection')
    for cohort, field in [('retrospective', 'inventory'), ('circall', 'circall')]:
        if a.cohort in ('all', cohort) and getattr(a, field) is None:
            p.error(f'Selected {cohort} requires --{field}')
    for field in ('inventory', 'circall', 'donors', 'rules', 'definitions', 'output_dir'):
        if getattr(a, field) is not None:
            setattr(a, field, getattr(a, field).expanduser().absolute())
    return a


def preflight(args):
    rules = load_rules(args.rules)
    definitions = with_comparison_switches(load_definitions(args.definitions),
                                          getattr(args, 'comparison_switches', None))
    definitions['rules']['sample_selection_seed'] = args.sample_selection_seed
    inputs, states = capture_sources(args)
    inputs['definitions'] = args.definitions
    settings = {k: str(v) if isinstance(v, Path) else v for k, v in vars(args).items() if k not in ('output_dir', 'validate_only')}
    settings.update(rules_definition=rules, association_definition=definitions)
    record = envelope('advanced_analysis', settings, inputs, [ROOT/'run.py', *sorted((ROOT/'analysis').rglob('*.py'))], ROOT/'environments/conda-linux-64.lock')
    previews = {}
    for cohort, path in sources(args).items():
        try:
            frame, counts, _, issues = prepare(path, cohort, definitions, sample_selection_seed=args.sample_selection_seed)
            previews[cohort] = dict(counts=counts, preparation_issues=len(issues), status='blocked' if issues else 'prepared')
        except Exception as error:
            previews[cohort] = dict(status='unavailable', error_code=type(error).__name__)
    record.update(source_states=states, preparation_preview=previews, status='complete', finished_utc=utc_now())
    verify_inputs(record['inputs'])
    verify_source_states(states)
    return record


def run(args):
    record = preflight(args)
    output = Path(args.output_dir)
    output.mkdir(parents=True, exist_ok=False)
    os.environ.setdefault('MPLCONFIGDIR', str(output/'.cache/matplotlib'))
    record.update(status='running', started_utc=utc_now(), finished_utc=None, cohorts=[], artifacts=[])
    write_json(output/'run_manifest.json', record)
    d = record['resolved_settings']['association_definition']
    rules = record['resolved_settings']['rules_definition']
    successful = {}

    def publish_scope(scope, frame, result, models, evidence, residuals):
        native = output/scope
        native.mkdir(exist_ok=True)
        write_json(native/'associations.json', result)
        if result['status'] == 'complete':
            write_json(native/'observations.json', clean(frame.to_dict(orient='records')))
            write_json(native/'source_observations.json', evidence)
            write_json(native/'model_diagnostics.json', residuals)
            if residuals:
                pd.DataFrame(residuals).to_csv(native/'model_diagnostics.csv', index=False)
            for variable, model in models.items():
                if model is not None:
                    diagnostics = native/'diagnostics'/variable
                    diagnostics.mkdir(parents=True)
                    outcome = variable.split('/')[0]
                    engine.plot_assumptions(model, diagnostics, outcome_label=d['outcomes'][outcome]['label'], cohort=scope)
            figures(native/'figures', frame, result, models, args, d)
        workbook(native/'associations.xlsx', result, d)
        validate_workbook(native/'associations.xlsx', result, d)
        record['cohorts'].append(dict(cohort=scope, report_status='complete', association_status=result['status'],
                                      integrity_reviews=result['summary'].get('integrity_reviews', 0)))
        for path in sorted(native.rglob('*')):
            if path.is_file():
                record['artifacts'].append(dict(path=str(path.relative_to(output)), sha256=digest(path)))

    for cohort, path in sources(args).items():
        frame = pd.DataFrame()
        counts, evidence, issues = {}, [], []
        try:
            integrity = inspect_with_controls(path, cohort, args.include_controls, rules, args.donors)
            (output/cohort).mkdir()
            write_json(output/cohort/'integrity_findings.json', integrity)
            counts.update(integrity_errors=integrity['summary']['errors'], integrity_reviews=integrity['summary']['reviews'])
            if integrity['summary']['errors']:
                issues = [dict(reason='layer1_errors', field=g['field'], sheet=g['sheet'], rule=g['rule'], occurrences=g['count'])
                          for g in integrity['groups'] if g['severity'] == 'error']
            else:
                frame, preparation_counts, evidence, issues = prepare(path, cohort, d, sample_selection_seed=args.sample_selection_seed)
                counts.update(preparation_counts)
            status = 'blocked' if issues else 'complete'
            result, models, residuals = analyze(frame, cohort, args, d, status=status, counts=counts, blocking=issues)
            publish_scope(cohort, frame, result, models, evidence, residuals)
            if status == 'complete':
                successful[cohort] = frame
        except Exception as error:
            # Library messages may contain clinical values; persist only the type.
            result, _, _ = analyze(pd.DataFrame(), cohort, args, d, status='execution_failed', counts=counts,
                                   blocking=[dict(reason=type(error).__name__)])
            try:
                publish_scope(cohort, pd.DataFrame(), result, {}, [], [])
            except Exception as report_error:
                record['cohorts'].append(dict(cohort=cohort, report_status='failed', association_status='execution_failed', error_code=type(report_error).__name__))
        write_json(output/'run_manifest.json', record)
    if args.pool_cohorts and args.cohort == 'all':
        ready = set(successful) == {'retrospective', 'circall'}
        frame = pd.concat(list(successful.values()), ignore_index=True) if ready else pd.DataFrame()
        try:
            result, models, residuals = analyze(frame, 'pooled', args, d, status='complete' if ready else 'blocked',
                                               counts={'eligible_patients': len(frame)}, cohorts=successful,
                                               blocking=[] if ready else [dict(reason='Both independent patient cohorts must complete')])
            publish_scope('pooled', frame, result, models, [], residuals)
        except Exception as error:
            result, _, _ = analyze(pd.DataFrame(), 'pooled', args, d, status='execution_failed', blocking=[dict(reason=type(error).__name__)])
            try:
                publish_scope('pooled', pd.DataFrame(), result, {}, [], [])
            except Exception as report_error:
                record['cohorts'].append(dict(cohort='pooled', report_status='failed', association_status='execution_failed', error_code=type(report_error).__name__))
    try:
        verify_inputs(record['inputs'])
        verify_source_states(record['source_states'])
    except (ValueError, OSError):
        record.update(status='failed', error_code='SourceChanged', finished_utc=utc_now())
        write_json(output/'run_manifest.json', record)
        return 1
    record.update(status='complete' if any(c['report_status'] == 'complete' for c in record['cohorts']) else 'failed',
                  quality_status='errors_found' if any(c['association_status'] != 'complete' for c in record['cohorts']) else 'review_needed' if any(c.get('integrity_reviews', 0) for c in record['cohorts']) else 'no_issues_detected',
                  report_generation_status='complete' if all(c['report_status'] == 'complete' for c in record['cohorts']) else 'partial', finished_utc=utc_now())
    write_json(output/'run_manifest.json', record)
    # Publication readiness is distinct from quality: the wrapper publishes then
    # returns nonzero on quality failures, as for Layers 1 and 2.
    return 0 if record['status'] == 'complete' else 1


def validate_results(output, record):
    output = Path(output)
    settings = record['resolved_settings']
    d = settings['association_definition']
    args = SimpleNamespace(**settings)
    frames = {}
    for item in record['artifacts']:
        path = Path(item['path'])
        if path.is_absolute() or '..' in path.parts or digest(output/path) != item['sha256']:
            raise ValueError('Layer 3 artifact mismatch')
        if path.suffix == '.png':
            from PIL import Image
            with Image.open(output/path) as im:
                im.verify()
        if path.suffix == '.pdf':
            payload = (output/path).read_bytes()
            xref = re.search(rb'startxref\s+(\d+)\s+%%EOF\s*$', payload)
            if (not payload.startswith(b'%PDF-') or b'/Type /Page' not in payload or not xref
                    or payload[int(xref[1]):int(xref[1])+4] != b'xref'):
                raise ValueError('Invalid Layer 3 PDF structure')
    for cohort in record['cohorts']:
        if cohort['report_status'] != 'complete':
            continue
        native = output/cohort['cohort']
        result = json.loads((native/'associations.json').read_text())
        validate_workbook(native/'associations.xlsx', result, d)
        if result['status'] == 'complete':
            rows = json.loads((native/'observations.json').read_text())
            columns = observation_columns(d)
            frame = pd.DataFrame(rows, columns=columns)
            if any(set(r) != set(columns) for r in rows):
                raise ValueError('Unexpected Layer 3 row-export columns')
            if result['scope'] != 'pooled':
                path = args.inventory if result['scope'] == 'retrospective' else args.circall
                source_frame, source_counts, source_rows, issues = prepare(path, result['scope'], d)
                if (issues or clean(source_frame.to_dict(orient='records')) != rows
                        or source_rows != json.loads((native/'source_observations.json').read_text())
                        or any(result['summary'].get(k) != v for k, v in source_counts.items())):
                    raise ValueError('Layer 3 audit observations do not reconcile with selected sources')
            recalculated, _, residuals = analyze(frame, result['scope'], args, d, counts=result['summary'],
                                                cohorts=frames if result['scope'] == 'pooled' else None)
            if recalculated != result or residuals != json.loads((native/'model_diagnostics.json').read_text()):
                raise ValueError('Layer 3 results do not reconcile with audit observations')
            if result['scope'] != 'pooled':
                frames[result['scope']] = frame
    verify_inputs(record['inputs'])
    verify_source_states(record['source_states'])
