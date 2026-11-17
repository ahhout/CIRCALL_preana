"""Independently reconcile completed native results."""
from analysis.disease_modeling.sources import selected_cohorts, settings, verify_source_states
from analysis.disease_modeling.step_02_combine import combined_results
from analysis.disease_modeling.step_01_evaluate import evaluate
import json
from pathlib import Path
import re
from types import SimpleNamespace
from analysis.provenance import digest, verify_inputs
from analysis.disease_modeling import step_03_report as reporting


def validate_results(output, record):
    output = Path(output)
    d = record['resolved_settings']['disease_definition']
    rules = record['resolved_settings']['rules_definition']
    args = SimpleNamespace(**record['resolved_settings']['arguments'])
    evaluated = {c: evaluate(c, args, d, rules) for c in selected_cohorts(args)}
    expected = {c: r for c, (r, _, _) in evaluated.items()}
    expected.update({c: r for c, (r, _) in combined_results(evaluated, args, d).items()})
    for artifact in record['artifacts']:
        path = Path(artifact['path'])
        if path.is_absolute() or '..' in path.parts or (output/path).is_symlink() or digest(output/path) != artifact['sha256']:
            raise ValueError('Disease artifact mismatch')
        if path.suffix == '.png':
            from PIL import Image
            with Image.open(output/path) as im:
                im.verify()
        if path.suffix == '.pdf':
            payload = (output/path).read_bytes()
            xref = re.search(rb'startxref\s+(\d+)\s+%%EOF\s*$', payload)
            if not payload.startswith(b'%PDF-') or b'/Type /Page' not in payload or not xref or payload[int(xref[1]):int(xref[1])+4] != b'xref':
                raise ValueError('Invalid disease PDF structure')
    for scope in record['cohorts']:
        if scope['report_status'] != 'complete':
            continue
        native = output/scope['cohort']
        result = json.loads((native/'disease_modeling.json').read_text())
        reporting.validate_workbook(native/'disease_modeling.xlsx', result, d, settings(args))
        if result['status'] != 'execution_failed' and result != expected[scope['cohort']]:
            raise ValueError('Disease aggregate reports differ from reconstructed sources')
        if result['status'] == 'execution_failed' and (not result['blocking'] or scope['disease_status'] != 'execution_failed'):
            raise ValueError('Invalid execution failure evidence')
    verify_inputs(record['inputs'])
    verify_source_states(record['source_states'])
