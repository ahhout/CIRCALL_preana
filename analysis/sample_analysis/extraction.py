"""Attach confirmed plasma workflow metadata without inferring sample handling."""
import json
import math
from pathlib import Path

import pandas as pd


def load_protocols(path):
    path = Path(path)
    with path.open() as stream:
        config = json.load(stream)
    if config.get('version') != 1 or not config.get('provenance'):
        raise ValueError('Extraction protocol configuration requires version 1 and provenance')
    protocols = config.get('protocols', {})
    if set(protocols) != {'circall', 'retrospective'}:
        raise ValueError('Extraction protocols must specify circall and retrospective')
    for cohort, protocol in protocols.items():
        for field in ('workflow', 'handling', 'unresolved'):
            if not isinstance(protocol.get(field), str) or not protocol[field].strip():
                raise ValueError(f'Extraction protocol {cohort}: missing {field}')
        capacity = protocol.get('max_plasma_per_well_ml')
        options = protocol.get('per_well_elution_options_uL')
        if not isinstance(options, list):
            raise ValueError(f'Extraction protocol {cohort}: elution options must be a list')
        for value in ([capacity] if capacity is not None else []) + options:
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                raise ValueError(f'Extraction protocol {cohort}: volumes must be finite positive numbers')
    return config


def annotate(frame, config):
    """Preserve source extraction_method and all measurements; add a separate protocol label."""
    result = frame.copy()
    result['confirmed_plasma_workflow'] = 'not applicable'
    plasma = result.compartment.eq('plasma')
    result.loc[plasma, 'confirmed_plasma_workflow'] = 'unconfirmed'
    for cohort, protocol in config['protocols'].items():
        mask = plasma & result.cohort.eq(cohort) & ~result.is_control
        result.loc[mask, 'confirmed_plasma_workflow'] = protocol['workflow']
    return result


def summary(config):
    rows = []
    for cohort, protocol in config['protocols'].items():
        rows.append(dict(cohort=cohort, compartment='plasma', workflow=protocol['workflow'],
            max_plasma_per_well_ml=protocol['max_plasma_per_well_ml'],
            per_well_elution_options_uL='; '.join(str(v) for v in protocol['per_well_elution_options_uL']) or 'not applicable',
            handling=protocol['handling'], unresolved=protocol['unresolved'], provenance=config['provenance'],
            interpretation='Recorded elution volume is not interpreted as a per-well setting. Extraction methods are cohort-specific; no pooled extraction-method effect is estimated.'))
    return pd.DataFrame(rows)
