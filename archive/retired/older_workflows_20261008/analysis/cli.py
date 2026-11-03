"""Public runner interface for the active scientific workflows."""
import argparse
from datetime import datetime, timezone
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]


def arguments(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    selector = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
    selector.add_argument('--workflow')
    selector.add_argument('--config')
    selected, remaining = selector.parse_known_args(argv)
    integrated_flags = {'--layers', '--pdf-output', '--no-pdf-output', '--output-dir', '--validate-only', '--no-validate-only', '--help', '-h'}
    default_pipeline = selected.workflow is None and all(
        token.split('=', 1)[0] in integrated_flags
        for token in remaining if token.startswith('-'))
    if selected.config is not None or default_pipeline:
        from analysis.pipeline import arguments as pipeline_arguments
        return pipeline_arguments(argv)
    if selected.workflow == 'disease_modeling':
        from analysis.disease_modeling.runner import arguments as disease_arguments
        return disease_arguments(argv)
    if selected.workflow == 'advanced_analysis':
        from analysis.advanced_analysis.runner import arguments as advanced_arguments
        return advanced_arguments(argv)
    if selected.workflow == 'sample_statistics':
        from analysis.sample_statistics.runner import arguments as statistics_arguments
        return statistics_arguments(argv)
    if selected.workflow == 'data_integrity':
        from analysis.data_integrity.runner import arguments as integrity_arguments
        return integrity_arguments(argv)
    if selected.workflow == 'cfdna_associations':
        from analysis.cfdna_associations.runner import arguments as association_arguments
        return association_arguments(argv)
    parser=argparse.ArgumentParser(description='Compatibility sample analysis; use plain run.py for the layered pipeline', allow_abbrev=False)
    parser.epilog = 'Layered pipeline: python run.py [--validate-only]. Older combined workflow: python run.py --config configs/pipeline_all.json'
    parser.add_argument('--workflow',choices=['canonical','cfdna_associations'],default='canonical',
                        help='Use --workflow cfdna_associations --help for association options')
    parser.add_argument('--cohort',choices=['all','retrospective','circall'])
    parser.add_argument('--analysis',choices=['all','inventory','volumes','yield','longitudinal','mrd','kinetics'])
    for flag in ('inventory','donors','circall','output-dir'):
        parser.add_argument('--'+flag,type=Path)
    parser.add_argument('--mixed-random-slope-sensitivity',action='store_true')
    parser.add_argument('--extraction-protocols', type=Path, default=ROOT/'configs/sample_analysis/extraction_protocols.json',
                        help='Confirmed plasma workflow metadata; does not infer wells or alter measurements')
    parser.add_argument('--pool-cohorts', action=argparse.BooleanOptionalAction, default=False,
                        help='Explicitly enable exploratory pooled plasma analyses (default: disabled)')
    parser.add_argument('--longitudinal-followups', nargs='+', default=['tp1', 'tp2'],
                        choices=['d4', 'd8', 'd15', 'tp0,5', 'tp1', 'tp2'],
                        help='Planned diagnosis-to-follow-up contrasts; BH within each cohort')
    parser.add_argument('--longitudinal-descriptive-visits', nargs='*', default=['circall:tp2'],
                        choices=['circall:tp2'], help='Visits retained descriptively and omitted from the model')
    parser.add_argument('--pooled-timepoints', nargs='+', default=['diag', 'tp1', 'tp2'],
                        choices=['diag', 'tp1', 'tp2'], help='Shared canonical timepoints for pooled analyses (default: diag tp1 tp2)')
    parser.add_argument('--mixed-outlier-drop-n',type=int,default=0)
    parser.add_argument('--trend-bootstrap-resamples', type=int, default=10000, help='Whole-patient resamples for descriptive longitudinal CIs (default: 10000)')
    parser.add_argument('--trend-bootstrap-seed', type=int, default=42, help='Longitudinal bootstrap seed (default: 42)')
    parser.add_argument('--trend-bootstrap-method', choices=['percentile'], default='percentile', help='Approved pointwise 95%% interval method')
    parser.add_argument('--retrospective-mrd-duplicate-policy', choices=['worst', 'error'], default='worst',
                        help='Retrospective MRD repeats: numeric > pos NQ > negative (default: worst) or stop on conflicts')
    parser.add_argument('--retrospective-mrd-tissue', default='Moelle', help='Retrospective MRD tissue selection (default: Moelle)')
    parser.add_argument('--pool-mrd', action=argparse.BooleanOptionalAction, default=False,
                        help='Add descriptive pooled MRD trajectories and fixed-denominator status bars')
    parser.add_argument('--mrd-unknown-level', type=float, help='Assigned display fraction for unknown-significance MRD (canonical default: 1e-6)')
    parser.add_argument('--mrd-positive-nq-level', type=float, default=1e-6, help='Assigned pooled positive-nonquantifiable MRD display fraction (default: 1e-6)')
    parser.add_argument('--mrd-negative-level', type=float, help='Assigned display fraction for negative MRD (canonical default: 1e-8)')
    parser.add_argument('--blood-counts', type=Path, default=ROOT/'input/CIRCALL_wbc_blast_count_01102026.xlsx')
    parser.add_argument('--retrospective-blasts', type=Path, help='Explicit retrospective blast-sheet workbook for descriptive kinetics')
    parser.add_argument('--retrospective-blast-unit', choices=['x10^9/L'], help='Confirmed retrospective blast-count unit; required with --retrospective-blasts')
    parser.add_argument('--baseline-day-max', type=int, default=1, help='Confirmed diagnostic blood-count baseline: days <=1')
    parser.add_argument('--baseline-selection', choices=['latest', 'all'], default='latest', help='Diagnostic blood-count repeats: latest day (confirmed default) or all')
    parser.add_argument('--kinetics-y-scale', choices=['linear', 'log'], default='log', help='Blood-count y-axis; log shows zeros in a separate strip')
    parser.add_argument('--overlay-max-day', type=int, default=8, help='Final day shown in blast/WBC overlay only (default: 8)')
    parser.add_argument('--plot-diagnosis-as-d1', action=argparse.BooleanOptionalAction, default=None, help='Display diagnosis as D1 in canonical plots (default: enabled); does not change model timepoints')
    args=parser.parse_args(argv)
    if not 0 < args.mrd_positive_nq_level <= 1:
        parser.error('--mrd-positive-nq-level must be in (0, 1]')
    if not args.retrospective_mrd_tissue.strip():
        parser.error('--retrospective-mrd-tissue must be nonempty')
    if len(set(args.longitudinal_followups)) != len(args.longitudinal_followups):
        parser.error('--longitudinal-followups must contain unique visits')
    if args.mixed_outlier_drop_n<0:parser.error('--mixed-outlier-drop-n must be nonnegative')
    if args.trend_bootstrap_resamples < 1 or args.trend_bootstrap_seed < 0:
        parser.error('Trend bootstrap resamples must be positive and seed nonnegative')
    if args.workflow=='canonical':
        if args.overlay_max_day < args.baseline_day_max:
            parser.error('--overlay-max-day must be at or after --baseline-day-max')
        if args.plot_diagnosis_as_d1 is None: args.plot_diagnosis_as_d1=True
        args.cohort=args.cohort or 'all';args.analysis=args.analysis or 'all'
        if (args.retrospective_blasts is None) != (args.retrospective_blast_unit is None):
            parser.error('--retrospective-blasts and --retrospective-blast-unit must be supplied together')
        if args.retrospective_blasts is not None and (args.cohort == 'circall' or args.analysis not in ('all', 'kinetics')):
            parser.error('Retrospective blasts require --cohort all or retrospective and --analysis all or kinetics')
        if args.analysis=='kinetics' and args.cohort=='retrospective' and args.retrospective_blasts is None:
            parser.error('Retrospective kinetics requires --retrospective-blasts and its confirmed unit')
        args.mrd_unknown_level=1e-6 if args.mrd_unknown_level is None else args.mrd_unknown_level
        args.mrd_negative_level=1e-8 if args.mrd_negative_level is None else args.mrd_negative_level
        if not (0 < args.mrd_unknown_level <= 1 and 0 < args.mrd_negative_level <= 1):
            parser.error('MRD display levels must be finite fractions greater than zero and at most 1')
        if args.analysis not in ('all','longitudinal') and (args.mixed_random_slope_sensitivity or args.mixed_outlier_drop_n):
            parser.error('Sensitivity options require --analysis all or longitudinal')
        args.inventory=args.inventory or ROOT/'input/cfDNA_inventaire_retrospective.xlsx'
        if args.circall is None:
            parser.error('--circall PATH is required for canonical runs, including retrospective runs using CIRCALL controls')
        args.donors=args.donors or ROOT/'input/cfDNA_donors.xlsx'
        args.output_dir=args.output_dir or ROOT/'output'/datetime.now(timezone.utc).strftime('run_%Y-%m-%d_%H-%M-%S.%f_UTC')
    for name,value in vars(args).items():
        if isinstance(value,Path):
            setattr(args, name, value.expanduser().absolute() if name == 'output_dir' else value.expanduser().resolve())
    return args


def main(argv=None):
    args = arguments(argv)
    if hasattr(args, 'config'):
        from .pipeline import main as pipeline_main
        return pipeline_main(argv)
    if args.workflow == 'disease_modeling':
        from analysis.disease_modeling.runner import main as disease_main
        return disease_main(argv)
    if args.workflow == 'advanced_analysis':
        from analysis.advanced_analysis.runner import main as advanced_main
        return advanced_main(argv)
    if args.workflow == 'sample_statistics':
        from analysis.sample_statistics.runner import main as statistics_main
        return statistics_main(argv)
    if args.workflow == 'data_integrity':
        from analysis.data_integrity.runner import main as integrity_main
        return integrity_main(argv)
    from .pipeline import CANONICAL, ASSOCIATIONS
    from .outputs import run_standalone
    from .worker import completion
    from copy import copy
    name = args.workflow
    allowed = {'canonical': CANONICAL, 'cfdna_associations': ASSOCIATIONS}[name]
    options = {key: (str(value) if isinstance(value, Path) else value)
               for key in allowed if (value := getattr(args, key.replace('-', '_'), None)) is not None}
    entry = {'name': name, 'options': options}
    destination = args.output_dir
    if name == 'canonical':
        from .sample_analysis.runner import run
    else:
        from .cfdna_associations.runner import run
    def execute(output):
        native = copy(args)
        native.output_dir = output
        return run(native)
    try:
        return run_standalone(name, destination, {'workflow': name, 'options': options}, execute,
                              lambda output: completion(entry, output))
    except (ValueError, OSError) as error:
        print(f'Error: {error}', file=sys.stderr)
        return 1
