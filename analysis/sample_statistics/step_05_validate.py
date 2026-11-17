"""Independently reconcile completed native results."""
import json
from pathlib import Path
from analysis.provenance import digest, verify_inputs
from analysis.utils.source_state import verify_source_states
from analysis.sample_statistics.step_01_prepare import aggregate
from analysis.sample_statistics.step_04_report import validate_workbook
from analysis.sample_statistics.step_03_compare import compare
from analysis.sample_statistics.calendar_volumes import calendar_coverage, validate_calendar_dates


def validate_results(output,record):
    output=Path(output)
    d=record['resolved_settings']['statistics_definition']
    for item in record['artifacts']:
        path=Path(item['path'])
        if path.is_absolute() or '..' in path.parts or digest(output/path)!=item['sha256']:raise ValueError('Statistics artifact mismatch')
        if path.suffix=='.png':
            from PIL import Image
            with Image.open(output/path) as im:im.verify()
        if path.suffix=='.pdf' and not (output/path).read_bytes().startswith(b'%PDF-'):raise ValueError('Invalid PDF')
    for cohort in record['cohorts']:
        if cohort['report_status']=='complete':
            native=output/cohort['cohort']
            result=json.loads((native/'statistics.json').read_text())
            validate_workbook(native/'statistics.xlsx',result,d)
            if result['status']=='complete':
                rows=json.loads((native/'observations.json').read_text())
                if cohort['cohort'] == 'circall':
                    validate_calendar_dates(rows, d, record['source_states']['circall']['path'])
                expected_calendar = calendar_coverage(rows, d) if cohort['cohort'] != 'pooled' else []
                if result.get('calendar_volume_coverage', []) != expected_calendar:
                    raise ValueError('Calendar volume coverage does not reconcile with audit observations')
                if aggregate([r for r in rows if not r['control']],d,pooled=cohort['cohort']=='pooled') != result['tables']:
                    raise ValueError('Statistics tables do not reconcile with audit observations')
                if 'controls' in result and aggregate([r for r in rows if r['control']],d)!=result['controls']:
                    raise ValueError('Control tables do not reconcile')
                comparison_rows=rows
                if cohort['cohort']=='pooled':
                    comparison_rows=[r for name in ('circall','retrospective')
                                     for r in json.loads((output/name/'observations.json').read_text())]
                if compare(comparison_rows,d,cohort['cohort'])!=result.get('comparisons'):
                    raise ValueError('Comparison results do not reconcile')
    verify_inputs(record['inputs']);verify_source_states(record['source_states'])
