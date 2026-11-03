"""Conda worker for the preserved engine; logs no source records or identities."""
import argparse
from contextlib import redirect_stderr, redirect_stdout
from dataclasses import asdict
import importlib.metadata
import json
import logging
import os
from pathlib import Path
import sys
import warnings


def run(settings_path):
    output = settings_path.parent
    details = {'status': 'running', 'python': sys.version, 'executable': sys.executable}
    stage = 'environment'
    try:
        details['packages'] = {name: importlib.metadata.version(name) for name in (
            'numpy', 'pandas', 'scipy', 'statsmodels', 'matplotlib', 'openpyxl')}
        from analysis.cfdna_associations import analyze_blast_cfdna as engine
        settings = json.loads(settings_path.read_text())
        logging.basicConfig(level=settings['log_level'], format='%(levelname)s: %(message)s')
        config = engine.CohortConfig(**{name: settings[name] for name in (
            'phase', 'blood_tissue', 'marrow_tissue', 'nucleic_acid', 'tube')})
        details['cohort_config'] = asdict(config)
        selected = engine.select_predictors(settings.get('predictors'))
        details['predictors'] = [asdict(predictor) for predictor in selected]
        descriptive = [p for p in engine.PREDICTORS if p.variable not in {s.variable for s in selected}]
        details['descriptive_predictors'] = [asdict(p) for p in descriptive]
        # Library warnings/exceptions can embed raw cell contents. Expose only safe failures below.
        with open(os.devnull, 'w') as quiet, redirect_stdout(quiet), redirect_stderr(quiet), warnings.catch_warnings():
            warnings.simplefilter('ignore')
            stage = 'input'
            data = engine.load_dataset(Path(settings['inventory']), settings['sheet'], config.patient_columns)
            stage = 'preparation'
            cohort, counts = engine.prepare_cohort(data, config)
            details['filtering_counts'] = counts
            stage = 'analysis'
            if settings.get('circall'):
                from . import diagnosis
                scopes, availability, circall_counts = diagnosis.write(output/'cfdna_associations',cohort,counts,
                    Path(settings['circall']),predictors=[p.variable for p in selected],pool=settings.get('pool_cohorts',True), spearman_enabled=settings.get('spearman_sensitivity', True),
                    retrospective_wbc_unit=settings.get('retrospective_wbc_unit', 'unknown'))
                details.update(scopes=scopes, diagnosis_availability=availability, circall_filtering_counts=circall_counts)
            else:
                engine.write_outputs(output / 'cfdna_associations', cohort, counts, overwrite=False,
                                     predictors=[p.variable for p in selected], spearman_enabled=settings.get('spearman_sensitivity', True))
            from analysis.artifacts import associations
            details['analysis_status'] = associations(output / 'cfdna_associations', selected, descriptive,
                                                       scopes=details.get('scopes'))
        logging.info('Filtering counts: %s', json.dumps(counts, sort_keys=True))
        details['status'] = 'complete'
    except Exception as error:
        message = str(error)
        safe_prefixes = ('Input is missing required columns:', 'Numeric cytology and cytospin_% values must',
                         'No diagnostic blood cfDNA patients remain', 'Unsupported input format.')
        if not message.startswith(safe_prefixes):
            message = f'{stage} failed ({type(error).__name__}); check input format, sheet, unique headers, numeric values and environment. Raw values omitted.'
        details.update(status='failed', error=message, stage=stage)
    (output / 'workflow_details.json').write_text(json.dumps(details, indent=2) + '\n')
    return 0 if details['status'] == 'complete' else 1


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--settings', type=Path, required=True)
    args = parser.parse_args(argv)
    return run(args.settings)


if __name__ == '__main__':
    raise SystemExit(main())
