"""Layer 3 comparison scope; legacy association settings remain independent."""
from analysis.association_methods import PredictorConfig


def predictors(definitions):
    return tuple(PredictorConfig(name, spec['label'], spec['kind'], name,
                                 robust_se=spec['kind'] == 'continuous')
                 for name, spec in definitions['predictors'].items())


def comparisons(definitions, scope, *, enabled_only=True):
    if scope != 'pooled':
        return [(outcome, variable) for outcome, variables in definitions['comparisons'][scope].items()
                for variable, enabled in variables.items() if not enabled_only or enabled is True]
    # Only explicitly requested pairs shared by both cohorts may be pooled.
    retro = set(comparisons(definitions, 'retrospective', enabled_only=enabled_only))
    return [pair for pair in comparisons(definitions, 'circall', enabled_only=enabled_only) if pair in retro]


def comparison_shape(definitions):
    """Validate JSON switches and ignore only their values for contract comparison."""
    matrix = definitions['comparisons']
    if not isinstance(matrix, dict) or set(matrix) != set(definitions['cohorts']):
        raise ValueError()
    normalized = {}
    for scope, outcomes in matrix.items():
        if not isinstance(outcomes, dict) or set(outcomes) != set(definitions['outcomes']):
            raise ValueError()
        normalized[scope] = {}
        for outcome, switches in outcomes.items():
            if (not isinstance(switches, dict)
                    or set(switches) - definitions['cohorts'][scope]['sources'].keys()
                    or any(type(enabled) is not bool for enabled in switches.values())):
                raise ValueError()
            normalized[scope][outcome] = dict.fromkeys(switches, True)
    return normalized


def observation_columns(definitions):
    return ['subject_hash', 'cohort', 'center', 'cfdna_ng_per_ml', 'outcome_sample_n',
            'eligible_sample_n', 'available_outcome_sample_n',
            *definitions['outcomes'], *definitions['predictors'],
            *[name+'_sample_n' for name in definitions['predictors']]]


def outcome_frame(frame, outcome):
    """Adapt the selected sample's endpoint to the unchanged fitting engine."""
    result = frame.copy()
    result['cfdna_ng_per_ml'] = result[outcome].astype(float)
    result['outcome_sample_n'] = result[outcome].notna().astype(int)
    return result


def with_comparison_switches(definitions, switches):
    """Override selection only; preserve the approved cohort/outcome/predictor matrix."""
    if switches is None:
        return definitions
    candidate = {**definitions, 'comparisons': switches}
    try:
        if comparison_shape(candidate) != comparison_shape(definitions):
            raise ValueError()
    except (ValueError, TypeError, KeyError, AttributeError):
        raise ValueError('Comparison switches must preserve the approved matrix and use JSON true/false') from None
    return candidate
