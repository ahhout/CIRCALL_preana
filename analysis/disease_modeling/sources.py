"""Disease source selection and immutable source checks."""
from pathlib import Path
from analysis.provenance import digest


def selected_cohorts(args):
    return ['retrospective', 'circall'] if args.cohort == 'all' else [args.cohort]

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
