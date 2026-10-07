"""Workflow-specific artifact contracts; checks never display clinical rows."""
import csv
import json
import math
from pathlib import Path
import struct
import zipfile


def validate_files(output, required):
    output = Path(output)
    for relative, headers in required.items():
        path = output / relative
        if path.is_symlink() or not path.is_file() or path.stat().st_size == 0:
            raise ValueError(f'Missing or empty required artifact: {relative}')
        if path.suffix == '.csv':
            with path.open(newline='', encoding='utf-8-sig') as stream:
                reader = csv.DictReader(stream)
                fields = reader.fieldnames or []
                if len(fields) != len(set(fields)) or not set(headers).issubset(fields):
                    raise ValueError(f'Invalid table headers: {relative}')
        elif path.suffix == '.json':
            try:
                value = json.loads(path.read_text())
            except (ValueError, UnicodeError):
                raise ValueError(f'Invalid JSON artifact: {relative}') from None
            if not isinstance(value, dict):
                raise ValueError(f'Invalid JSON structure: {relative}')
        elif path.suffix == '.png':
            with path.open('rb') as stream:
                header = stream.read(24)
            if len(header) < 24 or header[:8] != b'\x89PNG\r\n\x1a\n' or not all(struct.unpack('>II', header[16:24])):
                raise ValueError(f'Invalid PNG artifact: {relative}')
        elif path.suffix == '.pdf':
            with path.open('rb') as stream:
                if stream.read(5) != b'%PDF-':
                    raise ValueError(f'Invalid PDF artifact: {relative}')
        elif path.suffix == '.xlsx':
            try:
                with zipfile.ZipFile(path) as book:
                    if 'xl/workbook.xml' not in book.namelist() or book.testzip():
                        raise ValueError
            except (ValueError, zipfile.BadZipFile):
                raise ValueError(f'Invalid workbook artifact: {relative}') from None


def rows(path):
    with Path(path).open(newline='', encoding='utf-8-sig') as stream:
        return list(csv.DictReader(stream))


def canonical(output, args):
    from .outputs import engine_directory
    output = engine_directory(output, 'canonical')
    from analysis.sample_analysis.runner import selection
    cohorts, tasks, _ = selection(args)
    required = {'analysis_status.csv': ['analysis', 'cohort', 'status', 'reason'],
                'prepared/inventory.csv': ['record_id', 'cohort', 'patient_key', 'dna_ng_per_mL_plasma'],
                'prepared/pooled_controls.csv': ['patient_key', 'control_source'],
                'prepared/discrepancies.csv': ['record_id', 'reason'],
                'prepared/summary.json': [], 'prepared/reconciliation.json': [],
                'prepared/source_headers.json': [], 'prepared/source_mappings.json': [],
                'prepared/extraction_protocols.json': [],
                'prepared/measurement_availability.csv': ['record_id', 'measurement', 'status']}
    for scope in ('circall', 'retrospective', 'combined'):
        required[f'spreadsheet/{scope}_statistics.xlsx'] = []
    if 'inventory' in tasks:
        required['inventory/availability.csv'] = ['cohort', 'compartment', 'timepoint']
        if 'circall' in cohorts:
            required['inventory/missing_samples_list.csv'] = ['circall_id', 'timepoint', 'compartment']
            for dimension in ('compartment', 'timepoint'):
                required[f'inventory/missing_samples_by_hospital_{dimension}.csv'] = ['hospital']
    if 'volumes' in tasks:
        required['volumes/summary.csv'] = ['cohort', 'measurement', 'measured_records']
        if 'circall' in cohorts:
            required['volumes/circall_csf_by_site.csv'] = ['hospital']
            required['volumes/circall_csf_by_site.png'] = []
    if 'yield' in tasks:
        required['yield/summary.csv'] = ['cohort', 'measurement']
        required['yield/blood_pellet_summary.csv'] = ['cohort', 'measurement']
        required['yield/correlations.csv'] = ['cohort', 'status', 'paired_sample_count']
        required['yield/cohort_comparison.csv'] = ['timepoint', 'comparison_status']
        from analysis.sample_analysis.policies import PAIRS, correlation_pairs
        for metric in ('dna_concentration_ng_per_uL', 'dna_total_ng', 'dna_ng_per_mL_plasma'):
            required[f'yield/{metric}.png'] = []
            if len(cohorts) > 1:
                required[f'yield/{metric}_pooled.png'] = []
        for x, y in PAIRS:
            if any((x, y) in correlation_pairs(cohort) for cohort in cohorts):
                required[f'yield/{x}_vs_{y}.png'] = []
    if 'longitudinal' in tasks:
        for name in ('boxplots', 'trajectories'):
            required[f'longitudinal/{name}.png'] = []
            if len(cohorts) > 1:
                required[f'longitudinal/{name}_pooled.png'] = []
    native_manifest = output / 'run_manifest.json'
    if 'longitudinal' in tasks and native_manifest.is_file():
        metadata = json.loads(native_manifest.read_text())
        if 'longitudinal_trends' in metadata.get('plot_settings', {}):
            required['longitudinal/trendlines.png'] = []
            required['longitudinal/trendline_summary.csv'] = ['cohort', 'plot_timepoint', 'n_patients', 'median', 'ci95_low', 'ci95_high']
            required['longitudinal/trendline_settings.json'] = []
            for cohort in cohorts:
                required[f'longitudinal/{cohort}/trendlines.png'] = []
    if 'longitudinal' in tasks and args.pool_cohorts and len(cohorts) == 2:
        required['longitudinal/trendlines_pooled.png'] = []
        required['longitudinal/pooled_trendline_summary.csv'] = ['plot_timepoint', 'n_patients', 'median', 'ci95_low', 'ci95_high']
        required['longitudinal/pooled_trendline_settings.json'] = []
    if args.pool_cohorts and len(cohorts) == 2 and {'longitudinal', 'kinetics'}.issubset(tasks):
        required['longitudinal/yield_wbc_panels.png'] = []
        required['longitudinal/yield_wbc_panels.pdf'] = []
        required['longitudinal/yield_wbc_panel_settings.json'] = []
    if 'kinetics' in tasks:
        if 'circall' in cohorts:
            required['kinetics/circall_blood_count_observations.csv'] = ['patient_key', 'day']
            required['kinetics/circall_blood_count_summary.csv'] = ['measurement']
            required['kinetics/plot_settings.json'] = []
            for name in ('circall_blast_trajectories.png', 'circall_wbc_trajectories.png', 'circall_blast_wbc_trajectories.png',
                         'circall_blast_wbc_trajectories.pdf', 'circall_blast_wbc_overlay.png', 'circall_blast_wbc_overlay.pdf'):
                required['kinetics/' + name] = []
        if getattr(args, 'retrospective_blasts', None) is not None:
            required['kinetics/blood_count_summary.csv'] = ['cohort', 'measurement', 'measurements']
            required['kinetics/retrospective_plot_settings.json'] = []
            required['kinetics/retrospective_blast_trajectories.png'] = []
            if 'circall' in cohorts:
                for name in ('blast_trajectories_by_cohort.png', 'blast_cohort_overlay.png', 'blast_cohort_overlay.pdf'):
                    required['kinetics/' + name] = []
    if 'mrd' in tasks and 'retrospective' in cohorts:
        required['kinetics/mrd/retrospective_mrd_summary.csv'] = ['timepoint', 'patients_with_result', 'positive_nonquantifiable']
        required['kinetics/mrd/retrospective_mrd_trajectories.png'] = []
        required['kinetics/mrd/retrospective_plot_settings.json'] = []
    if 'mrd' in tasks and 'circall' in cohorts:
        required['kinetics/mrd/circall_mrd_summary.csv'] = ['timepoint', 'patients_with_result']
        required['kinetics/mrd/circall_mrd_observations.csv'] = ['patient_key', 'timepoint']
        required['kinetics/mrd/circall_mrd_trajectories.png'] = []
        required['kinetics/mrd/plot_settings.json'] = []
    validate_files(output, required)
    from openpyxl import load_workbook
    for scope in ('circall', 'retrospective', 'combined'):
        book = load_workbook(Path(output) / f'spreadsheet/{scope}_statistics.xlsx', read_only=True)
        try:
            if not {'README', 'contents'}.issubset(book.sheetnames):
                raise ValueError('Statistics workbook is missing contents or method notes')
        finally:
            book.close()
    events = rows(Path(output) / 'analysis_status.csv')
    if any(e['status'] == 'failed' for e in events):
        raise ValueError('Analysis status reports a failed analysis')
    for cohort in cohorts:
        if any(e['analysis'] == 'longitudinal' and e['cohort'] == cohort and e['status'] == 'complete' for e in events):
            validate_longitudinal(output, 'longitudinal/' + cohort, events, cohort)
    if any(e['analysis'] == 'pooled' and e['status'] == 'complete' for e in events):
        pooled = {'pooled/methods.csv': ['setting', 'value']}
        for task in ('volumes', 'yield', 'correlations'):
            if task in tasks or (task == 'correlations' and 'yield' in tasks):
                pooled[f'pooled/{task}.csv'] = ['cohort']
        validate_files(output, pooled)
        if 'longitudinal' in tasks and (Path(output) / 'pooled/timepoint_counts.csv').exists():
            validate_longitudinal(output, 'pooled', events, 'combined')
    return events


def validate_longitudinal(output, relative, events, cohort):
    required = {f'{relative}/{name}.csv': ['cohort'] for name in
                ('paired_counts', 'timepoint_counts', 'planned_comparisons')}
    unavailable = any(e['analysis'] == 'mixed_model' and e['cohort'] == cohort and e['status'] == 'unavailable' for e in events)
    if not unavailable:
        required[f'{relative}/mixed_contrasts.csv'] = ['delta_log10', 'p_adj']
        required[f'{relative}/primary_contrasts.csv'] = ['primary_family']
        required[f'{relative}/model_diagnostics.csv'] = ['converged', 'random_intercept_variance', 'residual_variance', 'numerical_warnings']
        required[f'{relative}/test_plots/mixed_contrasts.png'] = []
        required[f'{relative}/diagnostics/mixedlm/mixedlm_resid_qq.png'] = []
        required[f'{relative}/diagnostics/mixedlm/mixedlm_resid_vs_fitted.png'] = []
    validate_files(output, required)
    if not unavailable:
        for row in rows(Path(output) / relative / 'mixed_contrasts.csv'):
            if not all(math.isfinite(float(row[key])) for key in ('delta_log10', 'p_adj')):
                raise ValueError('Mixed contrasts contain nonfinite required results')


def associations(output, predictors, descriptive_predictors=(), *, scopes=None):
    from .outputs import engine_directory
    native = engine_directory(output, 'cfdna_associations')
    if native != Path(output):
        output = native / 'cfdna_associations'
    if scopes is not None:
        from types import SimpleNamespace
        validate_files(output, {'diagnosis_availability.csv': ['cohort', 'predictor', 'n', 'status', 'reason'],
                                'diagnosis_settings.json': []})
        unavailable = []
        for scope in scopes:
            if scope['relative_dir'] not in ('retrospective', 'circall', 'pooled'):
                raise ValueError('Invalid diagnosis cohort output scope')
            events = associations(Path(output)/scope['relative_dir'],
                [SimpleNamespace(**p) for p in scope['predictors']],
                [SimpleNamespace(**p) for p in scope['descriptive_predictors']])
            unavailable.extend(dict(event, cohort=scope['name']) for event in events)
        unavailable.extend(dict(analysis=r['predictor'],cohort=r['cohort'],status='unavailable',reason=r['reason'])
            for r in rows(Path(output)/'diagnosis_availability.csv') if r['status']=='skipped')
        return unavailable
    required = {'cohort_summary.csv': ['metric', 'count'],
                'predictor_descriptions.csv': ['predictor', 'n', 'summary_variable']}
    validate_files(output, required)
    unavailable = []
    for predictor in predictors:
        directory = predictor.output_name
        figure_name = getattr(predictor, 'figure_name', '') or f'log10_cfDNA_vs_{predictor.variable}.png'
        required = {f'{directory}/analysis_data.csv': ['observation', 'log10_cfDNA', predictor.variable],
                    f'{directory}/results.csv': ['status', 'reason', 'predictor', 'n'],
                    f'{directory}/assumptions/diagnostics.csv': ['status', 'note']}
        validate_files(output, required)
        result = rows(Path(output) / directory / 'results.csv')
        statuses = {r['status'] for r in result}
        if statuses == {'fit'}:
            validate_files(output, {f'{directory}/{name}': [] for name in
                (figure_name, 'assumptions/residuals_vs_fitted.png', 'assumptions/qq_plot.png', 'assumptions/scale_location.png')})
        elif statuses == {'skipped'}:
            unavailable.append({'analysis': predictor.variable, 'status': 'unavailable', 'reason': result[0]['reason']})
        else:
            raise ValueError('Predictor result status is invalid')
    for predictor in descriptive_predictors:
        directory = predictor.output_name
        figure_name = getattr(predictor, 'figure_name', '') or f'log10_cfDNA_vs_{predictor.variable}.png'
        validate_files(output, {f'{directory}/analysis_data.csv': ['observation', 'log10_cfDNA', predictor.variable],
            f'{directory}/descriptive_summary.csv': ['predictor', 'n', 'status', 'reason'],
            f'{directory}/{figure_name}': []})
        for row in rows(Path(output)/directory/'descriptive_summary.csv'):
            if row['status'] == 'unavailable':
                unavailable.append(dict(analysis=predictor.variable, status='unavailable', reason=row['reason']))
    return unavailable


def kinetics(output, config):
    from .outputs import engine_directory
    output = engine_directory(output, 'blast_kinetics')
    required = {name: [] for name in ('cohort_summary.json', 'resolved_config.yml', 'run_metadata.json', 'run.log')}
    if config['plots']['scatter']['enabled']:
        required['scatter.png'] = []
    if config['analysis']['model']['enabled']:
        required['model_summary.txt'] = []
        if config['plots']['model']['enabled']:
            required['mixed_model.png'] = []
    validate_files(output, required)
    summary = json.loads((Path(output) / 'cohort_summary.json').read_text())
    if not all(type(summary.get(k)) is int and summary[k] > 0 for k in ('analysis_rows', 'analysis_subjects')):
        raise ValueError('Invalid cohort summary counts')
