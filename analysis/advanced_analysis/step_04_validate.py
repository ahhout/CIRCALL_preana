"""Independently reconcile completed native results."""
import json
from pathlib import Path
import re
from types import SimpleNamespace
import pandas as pd
from analysis.utils.source_state import verify_source_states
from analysis.provenance import digest, verify_inputs
from analysis.advanced_analysis.step_01_prepare import prepare
from analysis.advanced_analysis.step_03_report import validate_workbook
from analysis.advanced_analysis.step_02_analyze import analyze, clean
from analysis.advanced_analysis.schema import observation_columns


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
