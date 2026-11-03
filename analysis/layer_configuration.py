"""Master layered settings and small profile references; no scientific preparation."""
import json
from pathlib import Path

from analysis.configuration import unique_object

LAYERS = ('data_integrity', 'sample_statistics', 'advanced_analysis', 'disease_modeling')
SOURCES = {'inventory', 'circall', 'donors', 'blood-counts', 'retrospective-blasts'}
DEFAULTS = {'cohort', 'include-controls', 'rules', 'pdf-output'}


def layer_selection(value):
    if (not isinstance(value, list) or not value
            or any(type(n) is not int or n not in (1, 2, 3, 4) for n in value)
            or len(set(value)) != len(value) or set(value) != {1, 2, 3, 4}):
        raise ValueError('All four layers are required; partial layer selection is retired')
    return [1, 2, 3, 4]


def read_profile(path, trail=()):
    """Return document, its owning path, selections and every configuration input."""
    path = Path(path).expanduser().resolve()
    configs = Path(__file__).resolve().parents[1] / 'configs'
    retired = {'pipeline_all.json', 'pipeline_longitudinal.json', 'pipeline_kinetics.json',
               'pipeline_mrd.json', 'pipeline_cfdna_spearman.json'}
    retired |= {'pipeline_integrity.json', 'pipeline_sample_statistics.json',
                'pipeline_advanced_analysis.json', 'pipeline_disease_modeling.json'}
    if path.name in retired and path.parent in (configs, configs / 'compatibility'):
        raise ValueError('Retired profile: older workflows are archived; use configs/pipeline_layers.json for current layers')
    if path in trail or len(trail) >= 16:
        raise ValueError('Cyclic or excessively nested profile reference')
    try:
        document = json.loads(path.read_text(), object_pairs_hook=unique_object,
                              parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (ValueError, UnicodeError, OSError):
        raise ValueError('Pipeline configuration must exist and contain valid JSON with unique keys and finite numbers') from None
    if not isinstance(document, dict) or type(document.get('schema_version')) is not int:
        raise ValueError('Pipeline configuration requires an integer schema_version')
    if document['schema_version'] == 2 and 'profile' in document:
        if (set(document) - {'schema_version', 'profile', 'layers'}
                or not isinstance(document['profile'], str) or not document['profile'].strip()):
            raise ValueError('Profile references accept only profile and optional layers')
        selected = [layer_selection(document['layers'])] if 'layers' in document else []
        resolved, owner, selections, inputs = read_profile(path.parent / document['profile'], (*trail, path))
        return resolved, owner, selections + selected, [path, *inputs]
    return document, path, [], [path]


def expand_layers(document, allowed):
    """Resolve one master into the existing engine option format."""
    required = {'schema_version', 'sources', 'defaults', 'layers'}
    if not required <= document.keys() or document.keys() - required - {'output-dir', 'validate-only'}:
        raise ValueError('Layered master requires sources, defaults and layers')
    sources, defaults, layers = (document[k] for k in ('sources', 'defaults', 'layers'))
    if not isinstance(sources, dict) or sources.keys() - SOURCES:
        raise ValueError('Unknown master source')
    if any(not isinstance(v, str) or not v.strip() for v in sources.values()):
        raise ValueError('Master sources must be nonempty paths')
    if not isinstance(defaults, dict) or defaults.keys() - DEFAULTS:
        raise ValueError('Unknown shared layered option')
    if not isinstance(layers, dict) or set(layers) != set(LAYERS):
        raise ValueError('The master must declare all four layer option blocks')
    entries = []
    for name in LAYERS:
        layer = layers[name]
        if (not isinstance(layer, dict) or 'options' not in layer or set(layer) - {'enabled', 'options'}
                or ('enabled' in layer and layer['enabled'] is not True) or not isinstance(layer['options'], dict)
                or layer['options'].keys() - allowed[name]):
            raise ValueError(f'Invalid {name} selection or options')
        if layer['options'].keys() & SOURCES:
            raise ValueError('Select workbook paths once under master sources')
        options = {k: v for k, v in {**sources, **defaults}.items() if k in allowed[name]}
        options.update(layer['options'])
        entries.append({'name': name, 'options': options})
    return {'schema_version': 1, 'workflows': entries,
            **{k: document[k] for k in ('output-dir', 'validate-only') if k in document}}


def select_layers(config, selection):
    """Accept only a legacy explicit full-layer selection."""
    layer_selection(selection)
    entries = config['workflows']
    if len(entries) != len(LAYERS) or {e['name'] for e in entries} != set(LAYERS):
        raise ValueError('All four layers are required; partial layer execution is retired')
    by_name = {entry['name']: entry for entry in entries}
    return {**config, 'workflows': [by_name[name] for name in LAYERS]}
