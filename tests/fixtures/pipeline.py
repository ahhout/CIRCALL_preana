"""Complete synthetic pipeline profiles for public execution tests."""
import json
from pathlib import Path

from analysis.layer_configuration import LAYERS
from analysis.provenance import ROOT
from tests.fixtures.advanced_analysis import sources as association_sources
from tests.disease_modeling.fixtures import sources as disease_sources


def full_entries(root, entries=()):
    root = Path(root)
    support = root/'pipeline_support'
    association = support/'associations'
    disease = support/'disease'
    if not support.exists():
        association.mkdir(parents=True)
        disease.mkdir()
        association_sources(association)
        disease_sources(disease)
    common = dict(inventory=str(association/'retrospective.xlsx'),
                  circall=str(association/'circall.xlsx'), cohort='all',
                  **{'include-controls': False})
    d = json.loads((ROOT/'configs/definitions/advanced_analysis.json').read_text())
    switches = {c: {o: dict.fromkeys(v, False) for o, v in outcomes.items()}
                for c, outcomes in d['comparisons'].items()}
    options = {
        'data_integrity': common,
        'sample_statistics': {**common, 'assessment-time': '2026-10-20T12:00:00+00:00', 'pdf-output': False},
        'advanced_analysis': {**common, 'comparison-switches': switches, 'pdf-output': False},
        'disease_modeling': dict(inventory=str(disease/'inventory.xlsx'), circall=str(disease/'circall.xlsx'),
                                **{'blood-counts': str(disease/'blood_counts.xlsx'),
                                   'retrospective-blasts': str(disease/'retrospective_blasts.xlsx'),
                                   'blood-count-unit': 'x10^9/L', 'retrospective-blast-unit': 'x10^9/L',
                                   'pdf-output': False, 'include-controls': False}),
    }
    overrides = {entry['name']: entry for entry in entries}
    return [overrides.get(name, dict(name=name, options=options[name])) for name in LAYERS]
